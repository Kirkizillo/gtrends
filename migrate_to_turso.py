"""
Script de migración one-time: Google Sheets → Turso.

Lee todos los datos existentes de las hojas Related_Queries_Top y
Related_Queries_Rising y los importa a Turso para poblar el historial.

Uso:
    python migrate_to_turso.py
    python migrate_to_turso.py --dry-run    # Solo muestra cuántos registros se migrarían
"""
import argparse
import json
import logging
import os
import sys

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
BATCH_SIZE = 500  # Insertar en lotes para no sobrecargar


def connect_sheets():
    """Conecta a Google Sheets en modo lectura."""
    creds = Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_PATH, scopes=SCOPES
    )
    client = gspread.authorize(creds)
    return client.open_by_key(config.GOOGLE_SHEET_ID)


def read_sheet_data(spreadsheet, sheet_name: str) -> list:
    """Lee todos los datos de una hoja."""
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        logger.warning(f"Hoja '{sheet_name}' no encontrada, saltando")
        return []

    all_values = worksheet.get_all_values()
    if not all_values:
        return []

    # Primera fila son headers
    headers = all_values[0]
    rows = all_values[1:]

    logger.info(f"  {sheet_name}: {len(rows)} filas encontradas")

    # Mapear columnas
    data = []
    for row in rows:
        if len(row) < 7:
            continue
        try:
            item = TrendData(
                timestamp=row[0],
                term=row[1],
                country_code=row[2],
                country_name=row[3],
                title=row[4],
                value=row[5],
                link=row[6] if len(row) > 6 else ""
            )
            # Inferir data_type del nombre de la hoja
            if "rising" in sheet_name.lower():
                item.data_type = "queries_rising"
            else:
                item.data_type = "queries_top"
            data.append(item)
        except Exception as e:
            logger.debug(f"  Fila ignorada: {e}")

    return data


def migrate(dry_run: bool = False):
    """Ejecuta la migración completa."""
    logger.info("=== Migración Google Sheets → Turso ===\n")

    # 1. Conectar a Sheets
    logger.info("Conectando a Google Sheets...")
    spreadsheet = connect_sheets()
    logger.info("✓ Conectado a Sheets\n")

    # 2. Leer datos
    logger.info("Leyendo datos de Google Sheets...")
    all_data = []
    for sheet_name in SHEETS_TO_MIGRATE:
        sheet_data = read_sheet_data(spreadsheet, sheet_name)
        all_data.extend(sheet_data)

    logger.info(f"\nTotal: {len(all_data)} registros para migrar\n")

    if dry_run:
        logger.info("[DRY RUN] No se insertaron datos. Usa sin --dry-run para migrar.")
        return

    if not all_data:
        logger.info("No hay datos para migrar.")
        return

    # 3. Conectar a Turso
    logger.info("Conectando a Turso...")
    db = TrendsDatabase()
    if not db.connect():
        logger.error("No se pudo conectar a Turso. Verifica TURSO_DATABASE_URL y TURSO_AUTH_TOKEN")
        sys.exit(1)
    logger.info("✓ Conectado a Turso\n")

    # 4. Insertar en lotes
    logger.info(f"Insertando en lotes de {BATCH_SIZE}...")
    total_inserted = 0
    for i in range(0, len(all_data), BATCH_SIZE):
        batch = all_data[i:i + BATCH_SIZE]
        try:
            db.insert_trends(batch, run_group="migration")
            total_inserted += len(batch)
            logger.info(f"  Insertados: {total_inserted}/{len(all_data)} ({total_inserted * 100 // len(all_data)}%)")
        except Exception as e:
            logger.error(f"  Error en lote {i}-{i + len(batch)}: {e}")

    # 5. Resumen
    db.close()
    logger.info(f"\n=== Migración completada ===")
    logger.info(f"Total insertados: {total_inserted}")
    logger.info(f"Total apps únicas en apps_seen: consultar en Turso dashboard")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrar datos de Google Sheets a Turso")
    parser.add_argument('--dry-run', action='store_true', help="Solo mostrar cuántos registros se migrarían")
    args = parser.parse_args()

    migrate(dry_run=args.dry_run)
