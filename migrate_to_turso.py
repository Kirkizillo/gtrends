"""
Script de migración one-time: Google Sheets → Turso.

Estrategia optimizada (3 fases):
- Fase 1: INSERT directo en tabla trends (sin upsert apps_seen, sin sync intermedio)
- Fase 2: Construir apps_seen en memoria y hacer INSERT OR REPLACE de golpe
- Fase 3: Un solo sync() al final

Uso:
    python migrate_to_turso.py
    python migrate_to_turso.py --dry-run
"""
import argparse
import json
import logging
import re
import sys
import unicodedata

import gspread
from google.oauth2.service_account import Credentials

import config
from database import TrendsDatabase
from trends_scraper import TrendData

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]

SHEETS_TO_MIGRATE = ["Related_Queries_Top", "Related_Queries_Rising"]
BATCH_SIZE = 5000


def connect_sheets():
    creds = Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
    )
    client = gspread.authorize(creds)
    return client.open_by_key(config.GOOGLE_SHEET_ID)


def read_sheet_data(spreadsheet, sheet_name: str) -> list:
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        logger.warning(f"Hoja '{sheet_name}' no encontrada, saltando")
        return []

    all_values = worksheet.get_all_values()
    if not all_values:
        return []

    rows = all_values[1:]
    logger.info(f"  {sheet_name}: {len(rows)} filas encontradas")

    data_type = "queries_rising" if "rising" in sheet_name.lower() else "queries_top"
    data = []
    for row in rows:
        if len(row) < 6:
            continue
        try:
            data.append(TrendData(
                timestamp=row[0], term=row[1], country_code=row[2],
                country_name=row[3], data_type=data_type, title=row[4],
                value=row[5], link=row[6] if len(row) > 6 else ""
            ))
        except Exception as e:
            logger.warning(f"  Fila ignorada: {e}")

    return data


def _normalize_title(title: str) -> str:
    if not title:
        return ""
    normalized = title.lower().strip()
    normalized = unicodedata.normalize('NFKD', normalized)
    normalized = ''.join(c for c in normalized if not unicodedata.combining(c))
    for suffix in [' apk', ' app', ' download', ' android', ' ios', ' for android', ' for ios']:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)].strip()
    normalized = re.sub(r'\s+\d+[\d.\s]*$', '', normalized)
    normalized = re.sub(r'\s+v\d+[\d.]*$', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def migrate(dry_run: bool = False):
    logger.info("=== Migración Google Sheets → Turso ===\n")

    logger.info("Conectando a Google Sheets...")
    spreadsheet = connect_sheets()
    logger.info("✓ Conectado a Sheets\n")

    logger.info("Leyendo datos...")
    all_data = []
    for sheet_name in SHEETS_TO_MIGRATE:
        all_data.extend(read_sheet_data(spreadsheet, sheet_name))

    logger.info(f"\nTotal: {len(all_data)} registros para migrar\n")

    if dry_run:
        logger.info("[DRY RUN] No se insertaron datos.")
        return

    if not all_data:
        logger.info("No hay datos para migrar.")
        return

    logger.info("Conectando a Turso...")
    db = TrendsDatabase()
    if not db.connect():
        logger.error("No se pudo conectar a Turso")
        sys.exit(1)
    logger.info("✓ Conectado a Turso\n")

    # Fase 1: INSERT directo en trends (sin apps_seen, sin sync entre lotes)
    logger.info(f"Fase 1/3: Insertando {len(all_data)} filas en trends...")
    total = 0
    for i in range(0, len(all_data), BATCH_SIZE):
        batch = all_data[i:i + BATCH_SIZE]
        for item in batch:
            db.conn.execute(
                """INSERT INTO trends
                   (timestamp, term, country_code, country_name, data_type, title, value, link, run_group)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item.timestamp, item.term, item.country_code, item.country_name,
                 item.data_type, item.title, str(item.value), item.link, "migration")
            )
        db.conn.commit()
        total += len(batch)
        logger.info(f"  {total}/{len(all_data)} ({total * 100 // len(all_data)}%)")

    # Fase 2: Construir apps_seen en memoria e insertar de golpe
    logger.info(f"\nFase 2/3: Construyendo apps_seen...")
    apps_map = {}
    for item in all_data:
        normalized = _normalize_title(item.title)
        if not normalized or len(normalized) <= 2:
            continue
        if normalized not in apps_map:
            apps_map[normalized] = {
                'display_name': item.title,
                'first_seen': item.timestamp,
                'last_seen': item.timestamp,
                'times_seen': 0,
                'countries': set()
            }
        entry = apps_map[normalized]
        entry['times_seen'] += 1
        entry['countries'].add(item.country_code)
        if item.timestamp < entry['first_seen']:
            entry['first_seen'] = item.timestamp
        if item.timestamp > entry['last_seen']:
            entry['last_seen'] = item.timestamp

    logger.info(f"  {len(apps_map)} apps únicas")
    count = 0
    for normalized, info in apps_map.items():
        db.conn.execute(
            """INSERT OR REPLACE INTO apps_seen
               (title_normalized, display_name, first_seen, last_seen, times_seen, countries_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (normalized, info['display_name'], info['first_seen'], info['last_seen'],
             info['times_seen'], json.dumps(sorted(info['countries'])))
        )
        count += 1
        if count % 1000 == 0:
            db.conn.commit()
    db.conn.commit()
    logger.info(f"  {count} apps insertadas")

    # Fase 3: Un solo sync
    logger.info(f"\nFase 3/3: Sincronizando con Turso cloud...")
    db.conn.sync()
    logger.info("✓ Sync completado")

    db.close()
    logger.info(f"\n=== Migración completada: {total} trends, {len(apps_map)} apps ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
