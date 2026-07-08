"""
Módulo de base de datos usando Turso (SQLite cloud).

Proporciona persistencia entre runs de GitHub Actions para:
- Historial completo de tendencias
- Detección de novedades (apps nuevas vs conocidas)
- Velocidad de tendencias (acelerando/estable/decayendo)
- Métricas de ejecución
"""
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import config

logger = logging.getLogger(__name__)


class TrendsDatabase:
    """
    Base de datos Turso para el sistema de monitoreo de tendencias.

    Usa embedded replica: copia local que se sincroniza con Turso cloud.
    En GitHub Actions el archivo local es efímero, pero los datos persisten en la nube.
    """

    def __init__(self, remote_only: bool = False):
        self.conn = None
        self._connected = False
        self._remote_only = remote_only

    def connect(self, remote_only: Optional[bool] = None) -> bool:
        """
        Conecta a Turso usando credenciales de config/env.

        Args:
            remote_only: Si True, usa conexión remota directa (sin replica local
                ni sync). Ideal para flujos de solo lectura como digest/weekly:
                el embedded replica descarga la BD completa en cada sync y agota
                la cuota mensual del plan free de Turso (~107k filas × 11 syncs/día).

        Returns:
            True si la conexión fue exitosa
        """
        if remote_only is not None:
            self._remote_only = remote_only

        try:
            import libsql

            turso_url = config.TURSO_DATABASE_URL
            turso_token = config.TURSO_AUTH_TOKEN

            if not turso_url or not turso_token:
                logger.warning("Turso no configurado (TURSO_DATABASE_URL o TURSO_AUTH_TOKEN vacíos)")
                return False

            if self._remote_only:
                # Conexión remota directa: sin replica local, sin sync().
                # Cada query viaja a Turso, pero no se descarga la BD entera.
                self.conn = libsql.connect(turso_url, auth_token=turso_token)
                self._connected = True
                logger.info("✓ Conectado a Turso (modo remoto, sin replica local)")
                return True

            # Embedded replica: archivo local temporal + sync con Turso cloud
            local_db = os.path.join(os.path.dirname(__file__), "data", "local_replica.db")
            os.makedirs(os.path.dirname(local_db), exist_ok=True)

            self.conn = libsql.connect(local_db, sync_url=turso_url, auth_token=turso_token)
            self.conn.sync()

            self._create_tables()
            self._connected = True
            logger.info("✓ Conectado a Turso")
            return True

        except ImportError:
            logger.warning("libsql no instalado. Ejecuta: pip install libsql")
            return False
        except Exception as e:
            logger.error(f"Error conectando a Turso: {e}")
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected and self.conn is not None

    def _sync(self):
        """Sincroniza la replica local con Turso (no-op en modo remoto)."""
        if not self._remote_only and self.conn is not None:
            self.conn.sync()

    def _create_tables(self):
        """Crea las tablas si no existen."""
        # Tabla principal de tendencias
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                term TEXT NOT NULL,
                country_code TEXT NOT NULL,
                country_name TEXT NOT NULL,
                data_type TEXT NOT NULL,
                title TEXT NOT NULL,
                value TEXT,
                link TEXT,
                run_group TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Tabla de apps vistas (para novelty detection)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS apps_seen (
                title_normalized TEXT PRIMARY KEY,
                display_name TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                times_seen INTEGER DEFAULT 1,
                countries_json TEXT DEFAULT '[]'
            )
        """)

        # Tabla de métricas por ejecución
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS run_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                group_name TEXT,
                duration_seconds INTEGER,
                total_combinations INTEGER,
                successful_requests INTEGER,
                failed_requests INTEGER,
                success_rate REAL,
                total_scraped INTEGER,
                total_exported INTEGER,
                apps_detected INTEGER,
                watchlist_detected INTEGER,
                errors_json TEXT DEFAULT '{}',
                export_json TEXT DEFAULT '{}'
            )
        """)

        # Índices para consultas frecuentes
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trends_country_ts
            ON trends(country_code, timestamp)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trends_title
            ON trends(title)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trends_ts_type
            ON trends(timestamp, data_type)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_apps_seen_last
            ON apps_seen(last_seen)
        """)

        self.conn.commit()
        self._sync()

    # =========================================================================
    # Inserción de datos
    # =========================================================================

    def insert_trends(self, trend_data_list: list, run_group: Optional[str] = None):
        """
        Inserta datos de tendencias y actualiza apps_seen.

        Args:
            trend_data_list: Lista de TrendData del scraper
            run_group: Nombre del grupo (group_1, etc.)
        """
        if not self.is_connected or not trend_data_list:
            return

        now_iso = datetime.now(timezone.utc).isoformat()

        for item in trend_data_list:
            # Insertar en trends
            self.conn.execute(
                """INSERT INTO trends
                   (timestamp, term, country_code, country_name, data_type, title, value, link, run_group)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item.timestamp, item.term, item.country_code, item.country_name,
                 item.data_type, item.title, str(item.value), item.link, run_group)
            )

            # Actualizar apps_seen — excluye trending_rss: son búsquedas
            # generales (deportes, noticias), no candidatas a app, y
            # contaminarían la detección de novedades
            if item.data_type == 'trending_rss':
                continue
            normalized = self._normalize_title(item.title)
            if normalized and len(normalized) > 2:
                self._upsert_app_seen(normalized, item.title, item.country_code, now_iso)

        self.conn.commit()
        self._sync()
        logger.info(f"  Turso: {len(trend_data_list)} registros insertados")

    def _upsert_app_seen(self, normalized: str, display_name: str, country_code: str, now_iso: str):
        """Actualiza o inserta en apps_seen."""
        row = self.conn.execute(
            "SELECT countries_json, times_seen FROM apps_seen WHERE title_normalized = ?",
            (normalized,)
        ).fetchone()

        if row:
            countries = json.loads(row[0]) if row[0] else []
            if country_code not in countries:
                countries.append(country_code)
            self.conn.execute(
                """UPDATE apps_seen
                   SET last_seen = ?, times_seen = times_seen + 1, countries_json = ?
                   WHERE title_normalized = ?""",
                (now_iso, json.dumps(countries), normalized)
            )
        else:
            self.conn.execute(
                """INSERT INTO apps_seen
                   (title_normalized, display_name, first_seen, last_seen, times_seen, countries_json)
                   VALUES (?, ?, ?, ?, 1, ?)""",
                (normalized, display_name, now_iso, now_iso, json.dumps([country_code]))
            )

    def insert_run_metrics(self, metrics: dict):
        """Inserta métricas de una ejecución."""
        if not self.is_connected:
            return

        self.conn.execute(
            """INSERT INTO run_metrics
               (timestamp, group_name, duration_seconds, total_combinations,
                successful_requests, failed_requests, success_rate,
                total_scraped, total_exported, apps_detected, watchlist_detected,
                errors_json, export_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                metrics.get("timestamp", datetime.now(timezone.utc).isoformat()),
                metrics.get("group"),
                metrics.get("duration_seconds", 0),
                metrics.get("total_combinations", 0),
                metrics.get("successful_requests", 0),
                metrics.get("failed_requests", 0),
                metrics.get("success_rate", 0),
                metrics.get("total_scraped", 0),
                metrics.get("total_exported", 0),
                metrics.get("apps_detected", 0),
                metrics.get("watchlist_detected", 0),
                json.dumps(metrics.get("errors_by_type", {}), default=str),
                json.dumps(metrics.get("export_by_sheet", {})),
            )
        )
        self.conn.commit()
        self._sync()

    # =========================================================================
    # Novelty Detection
    # =========================================================================

    def get_novelty_status(self, title: str) -> Tuple[str, Optional[str]]:
        """
        Determina si un título es nuevo, resurgente o conocido.

        Args:
            title: Título a verificar

        Returns:
            Tuple de (status, first_seen_date)
            status: 'nueva' | 'resurgente' | 'conocida'
        """
        if not self.is_connected:
            return ('desconocido', None)

        normalized = self._normalize_title(title)
        if not normalized:
            return ('desconocido', None)

        row = self.conn.execute(
            "SELECT first_seen, last_seen FROM apps_seen WHERE title_normalized = ?",
            (normalized,)
        ).fetchone()

        if not row:
            return ('nueva', None)

        first_seen = row[0]
        last_seen = row[1]

        # Resurgente si no se veía en >7 días
        try:
            last_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            days_since = (now - last_dt).days
            if days_since > 7:
                return ('resurgente', first_seen)
        except (ValueError, TypeError):
            pass

        return ('conocida', first_seen)

    def get_batch_novelty(self, titles: List[str]) -> dict:
        """
        Obtiene el status de novedad para múltiples títulos de una vez.

        Args:
            titles: Lista de títulos

        Returns:
            Dict de {title_normalized: (status, first_seen)}
        """
        if not self.is_connected:
            return {}

        results = {}
        for title in titles:
            normalized = self._normalize_title(title)
            if normalized:
                results[normalized] = self.get_novelty_status(title)
        return results

    # =========================================================================
    # Trend Velocity
    # =========================================================================

    def get_velocity(self, title: str) -> dict:
        """
        Calcula la velocidad de una tendencia comparando apariciones recientes.

        Args:
            title: Título a analizar

        Returns:
            Dict con velocity info:
            {
                'last_24h': int,      # apariciones en últimas 24h
                'prev_24h': int,      # apariciones en 24h anteriores
                'last_7d': int,       # apariciones en últimos 7 días
                'prev_7d': int,       # apariciones en 7 días anteriores
                'trend': str,         # 'acelerando' | 'estable' | 'decayendo'
                'change_24h': float   # porcentaje de cambio 24h
            }
        """
        if not self.is_connected:
            return {'trend': 'desconocido', 'last_24h': 0, 'prev_24h': 0,
                    'last_7d': 0, 'prev_7d': 0, 'change_24h': 0.0}

        normalized = self._normalize_title(title)
        if not normalized:
            return {'trend': 'desconocido', 'last_24h': 0, 'prev_24h': 0,
                    'last_7d': 0, 'prev_7d': 0, 'change_24h': 0.0}

        # Buscar por título normalizado en trends (que almacena títulos raw).
        # Usamos dos patrones: prefix ("capcut%") y word-boundary ("% capcut%")
        # para capturar tanto "capcut pro apk" como "download capcut".
        # El espacio en el segundo patrón evita falsos positivos como "instacapcut".
        like_prefix = f"{normalized}%"
        like_word = f"% {normalized}%"

        # trending_rss excluido: la velocidad mide señal de queries, no RSS
        velocity_where = ("(lower(title) LIKE ? OR lower(title) LIKE ?) "
                          "AND data_type != 'trending_rss'")

        # Apariciones últimas 24h
        last_24h = self.conn.execute(
            f"""SELECT COUNT(*) FROM trends
               WHERE {velocity_where}
               AND timestamp >= datetime('now', '-1 day')""",
            (like_prefix, like_word)
        ).fetchone()[0]

        # Apariciones 24-48h atrás
        prev_24h = self.conn.execute(
            f"""SELECT COUNT(*) FROM trends
               WHERE {velocity_where}
               AND timestamp >= datetime('now', '-2 days')
               AND timestamp < datetime('now', '-1 day')""",
            (like_prefix, like_word)
        ).fetchone()[0]

        # Apariciones últimos 7 días
        last_7d = self.conn.execute(
            f"""SELECT COUNT(*) FROM trends
               WHERE {velocity_where}
               AND timestamp >= datetime('now', '-7 days')""",
            (like_prefix, like_word)
        ).fetchone()[0]

        # Apariciones 7-14 días atrás
        prev_7d = self.conn.execute(
            f"""SELECT COUNT(*) FROM trends
               WHERE {velocity_where}
               AND timestamp >= datetime('now', '-14 days')
               AND timestamp < datetime('now', '-7 days')""",
            (like_prefix, like_word)
        ).fetchone()[0]

        # Calcular tendencia
        if prev_24h > 0:
            change_24h = ((last_24h - prev_24h) / prev_24h) * 100
        elif last_24h > 0:
            change_24h = 100.0  # De 0 a algo = crecimiento
        else:
            change_24h = 0.0

        if change_24h > 20:
            trend = 'acelerando'
        elif change_24h < -20:
            trend = 'decayendo'
        else:
            trend = 'estable'

        return {
            'last_24h': last_24h,
            'prev_24h': prev_24h,
            'last_7d': last_7d,
            'prev_7d': prev_7d,
            'trend': trend,
            'change_24h': round(change_24h, 1)
        }

    # =========================================================================
    # Consultas para digest diario
    # =========================================================================

    @staticmethod
    def _day_bounds(date: str) -> Tuple[str, str]:
        """
        Devuelve los límites [date 00:00, date+1 00:00) para una fecha YYYY-MM-DD.

        Funciona por comparación de strings tanto para timestamps
        "YYYY-MM-DD HH:MM:SS" (tabla trends) como ISO "YYYY-MM-DDTHH:MM:SS+00:00"
        (apps_seen.first_seen).
        """
        start = datetime.strptime(date, "%Y-%m-%d")
        end = start + timedelta(days=1)
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    def get_today_top_apps(self, limit: int = 10, date: Optional[str] = None) -> list:
        """
        Obtiene las apps más frecuentes del día.

        Args:
            limit: Máximo de apps a devolver
            date: Fecha YYYY-MM-DD para usar el día calendario [00:00, 24:00) UTC.
                  Si es None, usa ventana móvil de últimas 24h (comportamiento previo).

        Returns:
            Lista de dicts con {title, count, countries, data_types}
        """
        if not self.is_connected:
            return []

        if date:
            start, end = self._day_bounds(date)
            where = "timestamp >= ? AND timestamp < ?"
            params = (start, end, limit)
        else:
            where = "timestamp >= datetime('now', '-1 day')"
            params = (limit,)

        rows = self.conn.execute(
            f"""SELECT title, COUNT(*) as cnt,
                      GROUP_CONCAT(DISTINCT country_code) as countries,
                      GROUP_CONCAT(DISTINCT data_type) as types
               FROM trends
               WHERE {where}
               AND data_type != 'trending_rss'
               GROUP BY lower(title)
               ORDER BY cnt DESC
               LIMIT ?""",
            params
        ).fetchall()

        return [
            {
                'title': row[0],
                'count': row[1],
                'countries': row[2].split(',') if row[2] else [],
                'data_types': row[3].split(',') if row[3] else [],
            }
            for row in rows
        ]

    def get_today_new_apps(self, date: Optional[str] = None) -> list:
        """
        Obtiene apps vistas por primera vez hoy.

        Args:
            date: Fecha YYYY-MM-DD (día calendario UTC). None = últimas 24h móviles.

        Returns:
            Lista de dicts con {title, countries, first_seen}
        """
        if not self.is_connected:
            return []

        if date:
            start, end = self._day_bounds(date)
            rows = self.conn.execute(
                """SELECT title_normalized, display_name, first_seen, countries_json
                   FROM apps_seen
                   WHERE first_seen >= ? AND first_seen < ?
                   ORDER BY first_seen DESC""",
                (start, end)
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT title_normalized, display_name, first_seen, countries_json
                   FROM apps_seen
                   WHERE first_seen >= datetime('now', '-1 day')
                   ORDER BY first_seen DESC"""
            ).fetchall()

        return [
            {
                'title_normalized': row[0],
                'display_name': row[1],
                'first_seen': row[2],
                'countries': json.loads(row[3]) if row[3] else [],
            }
            for row in rows
        ]

    def get_region_activity(self, date: Optional[str] = None) -> list:
        """
        Obtiene actividad por región.

        Args:
            date: Fecha YYYY-MM-DD (día calendario UTC). None = últimas 24h móviles.

        Returns:
            Lista de dicts con {country_code, count}
        """
        if not self.is_connected:
            return []

        if date:
            start, end = self._day_bounds(date)
            where = "timestamp >= ? AND timestamp < ?"
            params = (start, end)
        else:
            where = "timestamp >= datetime('now', '-1 day')"
            params = ()

        rows = self.conn.execute(
            f"""SELECT country_code, COUNT(*) as cnt
               FROM trends
               WHERE {where}
               AND data_type != 'trending_rss'
               GROUP BY country_code
               ORDER BY cnt DESC""",
            params
        ).fetchall()

        return [{'country_code': row[0], 'count': row[1]} for row in rows]

    def get_daily_comparison(self, date: Optional[str] = None) -> dict:
        """
        Compara volumen de hoy vs ayer.

        Args:
            date: Fecha YYYY-MM-DD. "Hoy" = [date, date+1), "ayer" = [date-1, date).
                  None = ventanas móviles de 24h (comportamiento previo).

        Returns:
            Dict con {today, yesterday, change_pct}
        """
        if not self.is_connected:
            return {'today': 0, 'yesterday': 0, 'change_pct': 0.0}

        if date:
            start, end = self._day_bounds(date)
            prev_start = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

            # trending_rss excluido para que el volumen sea comparable
            # con el histórico (que solo contiene queries)
            today = self.conn.execute(
                """SELECT COUNT(*) FROM trends WHERE timestamp >= ? AND timestamp < ?
                   AND data_type != 'trending_rss'""",
                (start, end)
            ).fetchone()[0]

            yesterday = self.conn.execute(
                """SELECT COUNT(*) FROM trends WHERE timestamp >= ? AND timestamp < ?
                   AND data_type != 'trending_rss'""",
                (prev_start, start)
            ).fetchone()[0]
        else:
            today = self.conn.execute(
                """SELECT COUNT(*) FROM trends WHERE timestamp >= datetime('now', '-1 day')
                   AND data_type != 'trending_rss'"""
            ).fetchone()[0]

            yesterday = self.conn.execute(
                """SELECT COUNT(*) FROM trends
                   WHERE timestamp >= datetime('now', '-2 days')
                   AND timestamp < datetime('now', '-1 day')
                   AND data_type != 'trending_rss'"""
            ).fetchone()[0]

        change = ((today - yesterday) / yesterday * 100) if yesterday > 0 else 0.0

        return {
            'today': today,
            'yesterday': yesterday,
            'change_pct': round(change, 1)
        }

    # =========================================================================
    # Consultas para informe semanal
    # =========================================================================

    def get_weekly_top_by_country(self, days: int = 7, limit: int = 10) -> dict:
        """
        Top apps por país en los últimos N días.

        Returns:
            Dict de {country_code: [{title, count, data_types}]}
        """
        if not self.is_connected:
            return {}

        rows = self.conn.execute(
            """SELECT country_code, title, COUNT(*) as cnt,
                      GROUP_CONCAT(DISTINCT data_type) as types
               FROM trends
               WHERE timestamp >= datetime('now', ? || ' days')
               GROUP BY country_code, lower(title)
               ORDER BY country_code, cnt DESC""",
            (str(-days),)
        ).fetchall()

        result = {}
        for row in rows:
            cc = row[0]
            if cc not in result:
                result[cc] = []
            if len(result[cc]) < limit:
                result[cc].append({
                    'title': row[1],
                    'count': row[2],
                    'data_types': row[3].split(',') if row[3] else [],
                })
        return result

    def get_weekly_new_apps(self, days: int = 7) -> list:
        """
        Apps vistas por primera vez en los últimos N días.

        Returns:
            Lista de dicts con {title_normalized, display_name, first_seen, countries}
        """
        if not self.is_connected:
            return []

        rows = self.conn.execute(
            """SELECT title_normalized, display_name, first_seen, countries_json
               FROM apps_seen
               WHERE first_seen >= datetime('now', ? || ' days')
               ORDER BY first_seen DESC""",
            (str(-days),)
        ).fetchall()

        return [
            {
                'title_normalized': row[0],
                'display_name': row[1],
                'first_seen': row[2],
                'countries': json.loads(row[3]) if row[3] else [],
            }
            for row in rows
        ]

    def get_weekly_cross_market(self, days: int = 7, min_countries: int = 3) -> list:
        """
        Apps que aparecieron en 3+ países en los últimos N días.

        Returns:
            Lista de dicts con {title, countries, count, data_types}
        """
        if not self.is_connected:
            return []

        rows = self.conn.execute(
            """SELECT title, COUNT(*) as cnt,
                      GROUP_CONCAT(DISTINCT country_code) as countries,
                      GROUP_CONCAT(DISTINCT data_type) as types,
                      COUNT(DISTINCT country_code) as n_countries
               FROM trends
               WHERE timestamp >= datetime('now', ? || ' days')
               GROUP BY lower(title)
               HAVING n_countries >= ?
               ORDER BY n_countries DESC, cnt DESC""",
            (str(-days), min_countries)
        ).fetchall()

        return [
            {
                'title': row[0],
                'count': row[1],
                'countries': row[2].split(',') if row[2] else [],
                'data_types': row[3].split(',') if row[3] else [],
                'n_countries': row[4],
            }
            for row in rows
        ]

    def get_weekly_comparison(self) -> dict:
        """
        Compara volumen de esta semana vs la anterior.

        Returns:
            Dict con {this_week, last_week, change_pct, this_week_new, last_week_new,
                       region_activity: [{country_code, this_week, last_week}]}
        """
        if not self.is_connected:
            return {'this_week': 0, 'last_week': 0, 'change_pct': 0.0,
                    'this_week_new': 0, 'last_week_new': 0, 'region_activity': []}

        this_week = self.conn.execute(
            "SELECT COUNT(*) FROM trends WHERE timestamp >= datetime('now', '-7 days')"
        ).fetchone()[0]

        last_week = self.conn.execute(
            """SELECT COUNT(*) FROM trends
               WHERE timestamp >= datetime('now', '-14 days')
               AND timestamp < datetime('now', '-7 days')"""
        ).fetchone()[0]

        this_week_new = self.conn.execute(
            "SELECT COUNT(*) FROM apps_seen WHERE first_seen >= datetime('now', '-7 days')"
        ).fetchone()[0]

        last_week_new = self.conn.execute(
            """SELECT COUNT(*) FROM apps_seen
               WHERE first_seen >= datetime('now', '-14 days')
               AND first_seen < datetime('now', '-7 days')"""
        ).fetchone()[0]

        # Actividad por región comparada
        region_rows = self.conn.execute(
            """SELECT country_code,
                      SUM(CASE WHEN timestamp >= datetime('now', '-7 days') THEN 1 ELSE 0 END) as tw,
                      SUM(CASE WHEN timestamp >= datetime('now', '-14 days')
                                AND timestamp < datetime('now', '-7 days') THEN 1 ELSE 0 END) as lw
               FROM trends
               WHERE timestamp >= datetime('now', '-14 days')
               GROUP BY country_code
               ORDER BY tw DESC"""
        ).fetchall()

        change = ((this_week - last_week) / last_week * 100) if last_week > 0 else 0.0

        return {
            'this_week': this_week,
            'last_week': last_week,
            'change_pct': round(change, 1),
            'this_week_new': this_week_new,
            'last_week_new': last_week_new,
            'region_activity': [
                {'country_code': r[0], 'this_week': r[1], 'last_week': r[2]}
                for r in region_rows
            ],
        }

    # =========================================================================
    # Retención de datos
    # =========================================================================

    def purge_old_trends(self, days: int = 365) -> int:
        """
        Elimina registros de trends con más de N días de antigüedad.

        Acota el tamaño de la BD (y por tanto el egress de sync de las
        replicas embebidas), evitando agotar la cuota mensual de Turso.

        Args:
            days: Días de retención (default: 365)

        Returns:
            Número de filas eliminadas
        """
        if not self.is_connected:
            return 0

        try:
            cutoff = f"-{int(days)} days"
            to_delete = self.conn.execute(
                "SELECT COUNT(*) FROM trends WHERE timestamp < datetime('now', ?)",
                (cutoff,)
            ).fetchone()[0]

            if to_delete > 0:
                self.conn.execute(
                    "DELETE FROM trends WHERE timestamp < datetime('now', ?)",
                    (cutoff,)
                )
                self.conn.commit()
                self._sync()

            logger.info(f"Retención: {to_delete} filas eliminadas de trends (>{days} días)")
            return to_delete
        except Exception as e:
            logger.warning(f"Error en purge_old_trends: {e}")
            return 0

    # =========================================================================
    # Utilidades
    # =========================================================================

    @staticmethod
    def _normalize_title(title: str) -> str:
        """
        Normaliza un título para comparación en apps_seen.
        Consistente con la normalización de report_generator.
        """
        if not title:
            return ""

        normalized = title.lower().strip()

        # Remover acentos/diacríticos
        normalized = unicodedata.normalize('NFKD', normalized)
        normalized = ''.join(c for c in normalized if not unicodedata.combining(c))

        # Remover sufijos genéricos
        suffixes = [' apk', ' app', ' download', ' android', ' ios', ' for android', ' for ios']
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()

        # Remover versiones del final
        normalized = re.sub(r'\s+\d+[\d.\s]*$', '', normalized)
        normalized = re.sub(r'\s+v\d+[\d.]*$', '', normalized)

        # Limpiar espacios
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    def close(self):
        """Cierra la conexión."""
        if self.conn:
            try:
                self._sync()
                self.conn.close()
            except Exception:
                pass
            self._connected = False
