"""
Exportador de datos a Google Sheets usando gspread.
"""
import logging
from typing import List, Dict, Optional

import gspread
from google.oauth2.service_account import Credentials

import config
from datetime import datetime, timedelta
from trends_scraper import TrendData

logger = logging.getLogger(__name__)

# Scopes necesarios para Google Sheets API
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Headers para cada tipo de pestaña
HEADERS = ['timestamp', 'term', 'country_code', 'country_name', 'title', 'value', 'link']


class GoogleSheetsExporter:
    """
    Exportador de datos a Google Sheets con modo append.
    """

    def __init__(self, credentials_path: str = None, sheet_id: str = None):
        """
        Inicializa el exportador.

        Args:
            credentials_path: Ruta al archivo JSON de credenciales
            sheet_id: ID del Google Sheet
        """
        self.credentials_path = credentials_path or config.GOOGLE_CREDENTIALS_PATH
        self.sheet_id = sheet_id or config.GOOGLE_SHEET_ID
        self.client = None
        self.spreadsheet = None

    def connect(self) -> bool:
        """
        Establece conexión con Google Sheets.

        Returns:
            True si la conexión fue exitosa
        """
        try:
            credentials = Credentials.from_service_account_file(
                self.credentials_path,
                scopes=SCOPES
            )
            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open_by_key(self.sheet_id)
            logger.info(f"Conectado a Google Sheet: {self.spreadsheet.title}")
            return True

        except FileNotFoundError:
            logger.error(f"Archivo de credenciales no encontrado: {self.credentials_path}")
            return False
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(f"Google Sheet no encontrado con ID: {self.sheet_id}")
            return False
        except Exception as e:
            logger.error(f"Error conectando a Google Sheets: {e}")
            return False

    def _ensure_worksheet_exists(self, sheet_name: str) -> gspread.Worksheet:
        """
        Asegura que existe una pestaña con el nombre dado.
        Si no existe, la crea con los headers.

        Args:
            sheet_name: Nombre de la pestaña

        Returns:
            Worksheet object
        """
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            logger.debug(f"Pestaña '{sheet_name}' encontrada")
        except gspread.exceptions.WorksheetNotFound:
            logger.info(f"Creando pestaña '{sheet_name}'...")
            worksheet = self.spreadsheet.add_worksheet(
                title=sheet_name,
                rows=1000,
                cols=len(HEADERS)
            )
            # Agregar headers
            worksheet.append_row(HEADERS)
            logger.info(f"Pestaña '{sheet_name}' creada con headers")

        return worksheet

    def _get_sheet_name_for_type(self, data_type: str) -> str:
        """
        Obtiene el nombre de la pestaña según el tipo de dato.

        Args:
            data_type: Tipo de dato ('queries_top', 'queries_rising', etc.)

        Returns:
            Nombre de la pestaña
        """
        mapping = {
            'queries_top': config.SHEET_NAMES['queries_top'],
            'queries_rising': config.SHEET_NAMES['queries_rising'],
            'topics_top': config.SHEET_NAMES['topics_top'],
            'topics_rising': config.SHEET_NAMES['topics_rising'],
            'interest_over_time': config.SHEET_NAMES['interest_over_time']
        }
        # Fallback: cualquier tipo definido en config.SHEET_NAMES (ej: trending_rss)
        return mapping.get(data_type, config.SHEET_NAMES.get(data_type, 'Unknown'))

    def _trend_data_to_row(self, data: TrendData) -> List[str]:
        """
        Convierte TrendData a una fila para el sheet.

        Args:
            data: Objeto TrendData

        Returns:
            Lista de valores para la fila
        """
        return [
            data.timestamp,
            data.term,
            data.country_code,
            data.country_name,
            data.title,
            data.value,
            data.link
        ]

    def export(self, data: List[TrendData]) -> Dict[str, int]:
        """
        Exporta datos a Google Sheets en modo append.

        Args:
            data: Lista de TrendData a exportar

        Returns:
            Dict con conteo de filas exportadas por pestaña
        """
        if not self.spreadsheet:
            if not self.connect():
                raise ConnectionError("No se pudo conectar a Google Sheets")

        # Agrupar datos por tipo
        grouped_data: Dict[str, List[TrendData]] = {}
        for item in data:
            if item.data_type not in grouped_data:
                grouped_data[item.data_type] = []
            grouped_data[item.data_type].append(item)

        export_counts = {}

        for data_type, items in grouped_data.items():
            sheet_name = self._get_sheet_name_for_type(data_type)

            if sheet_name == 'Unknown':
                logger.warning(f"Tipo de dato desconocido: {data_type}")
                continue

            try:
                worksheet = self._ensure_worksheet_exists(sheet_name)

                # Preparar filas para append
                rows = [self._trend_data_to_row(item) for item in items]

                # Append en batch para mejor rendimiento
                if rows:
                    worksheet.append_rows(rows, value_input_option='RAW')
                    export_counts[sheet_name] = len(rows)
                    logger.info(f"Exportadas {len(rows)} filas a '{sheet_name}'")
                    self._check_capacity(worksheet, sheet_name)

            except Exception as e:
                logger.error(f"Error exportando a '{sheet_name}': {e}")
                export_counts[sheet_name] = 0

        return export_counts

    # Umbral de aviso: ~300k filas × 7 columnas ≈ 2.1M celdas por pestaña.
    # El límite duro de Google Sheets es 10M de celdas por spreadsheet.
    # Política: Turso es el archivo primario; a fin de año renombrar las
    # pestañas a *_2026 y dejar que el exporter cree pestañas nuevas.
    CAPACITY_WARN_ROWS = 300_000

    def _check_capacity(self, worksheet: gspread.Worksheet, sheet_name: str):
        """Avisa (log ruidoso) si una pestaña se acerca al límite de celdas."""
        try:
            if worksheet.row_count > self.CAPACITY_WARN_ROWS:
                logger.warning(
                    f"CAPACIDAD: la pestaña '{sheet_name}' supera "
                    f"{self.CAPACITY_WARN_ROWS} filas ({worksheet.row_count}). "
                    f"Rotar a '{sheet_name}_{datetime.now().year}' pronto — "
                    f"Turso conserva el histórico completo."
                )
        except Exception:
            pass

    def setup_sheets(self):
        """
        Configura todas las pestañas necesarias en el Google Sheet.
        Útil para inicialización.
        """
        if not self.spreadsheet:
            if not self.connect():
                raise ConnectionError("No se pudo conectar a Google Sheets")

        for key, sheet_name in config.SHEET_NAMES.items():
            self._ensure_worksheet_exists(sheet_name)

        logger.info("Todas las pestañas configuradas correctamente")

    def get_row_counts(self) -> Dict[str, int]:
        """
        Obtiene el número de filas en cada pestaña.

        Returns:
            Dict con conteo de filas por pestaña
        """
        if not self.spreadsheet:
            if not self.connect():
                raise ConnectionError("No se pudo conectar a Google Sheets")

        counts = {}
        for key, sheet_name in config.SHEET_NAMES.items():
            try:
                worksheet = self.spreadsheet.worksheet(sheet_name)
                # Obtener todas las filas y contar (excluyendo header)
                counts[sheet_name] = len(worksheet.get_all_values()) - 1
            except gspread.exceptions.WorksheetNotFound:
                counts[sheet_name] = 0

        return counts

    def export_report_to_sheet(self, headers: List[str], rows: List[List[str]],
                                timestamp: datetime = None) -> Optional[str]:
        """
        Exporta un informe a una pestaña diaria (una pestaña por día).

        Si la pestaña del día no existe, se crea. Si ya existe (runs
        posteriores del mismo día), el informe se agrega debajo del contenido
        existente, precedido por una fila separadora con la hora del run.

        Args:
            headers: Lista de headers para la pestaña
            rows: Lista de filas de datos
            timestamp: Timestamp para el nombre y la hora del run (default: ahora)

        Returns:
            Nombre de la pestaña usada o None si hay error
        """
        if not self.spreadsheet:
            if not self.connect():
                raise ConnectionError("No se pudo conectar a Google Sheets")

        if timestamp is None:
            timestamp = datetime.now()

        # Formato diario: Inf_2026-01-29 (una pestaña por día, no por run)
        sheet_name = timestamp.strftime("Inf_%Y-%m-%d")

        try:
            # Determinar número de columnas (de headers o de la primera fila)
            num_cols = len(headers) if headers else (len(rows[0]) if rows else 6)

            try:
                # Pestaña del día ya existe → append debajo del contenido
                worksheet = self.spreadsheet.worksheet(sheet_name)

                # Separador con la hora del run para distinguir cada bloque
                separator = timestamp.strftime("═══ Run %H:%M UTC ═══")
                block = [[""], [separator]]
                if headers:
                    block.append(headers)
                block.extend(rows)

                # append_rows agrega debajo de la última fila con datos
                worksheet.append_rows(block, value_input_option='RAW')
                logger.info(
                    f"Informe agregado a pestaña existente '{sheet_name}' "
                    f"({len(rows)} filas, separador {timestamp.strftime('%H:%M')} UTC)"
                )

            except gspread.exceptions.WorksheetNotFound:
                # Primera vez hoy → crear pestaña nueva
                worksheet = self.spreadsheet.add_worksheet(
                    title=sheet_name,
                    rows=max(len(rows) + 10, 100),
                    cols=num_cols
                )

                # Agregar headers solo si existen
                if headers:
                    worksheet.append_row(headers)

                # Agregar datos
                if rows:
                    worksheet.append_rows(rows, value_input_option='RAW')

                # Mover pestaña a posición 2 (después de Related_Queries_Rising)
                # para que los informes más recientes aparezcan primero
                worksheet.update_index(2)

                logger.info(f"Informe exportado a pestaña nueva '{sheet_name}' ({len(rows)} filas)")

            # Limpiar pestañas de informe antiguas
            self._cleanup_old_report_tabs()

            return sheet_name

        except Exception as e:
            logger.error(f"Error exportando pestaña de informe: {e}")
            return None

    @staticmethod
    def _parse_report_tab_date(title: str) -> Optional[str]:
        """
        Extrae la fecha (YYYY-MM-DD) de una pestaña de informe.
        Acepta ambos formatos:
          - Nuevo: Inf_YYYY-MM-DD
          - Legacy: Inf_YYYY-MM-DD_HH:MM
        Retorna None si el título no es una pestaña de informe válida.
        """
        if not title.startswith("Inf_") or len(title) < 14:
            return None
        tab_date = title[4:14]  # Extraer YYYY-MM-DD
        try:
            datetime.strptime(tab_date, "%Y-%m-%d")
        except ValueError:
            return None
        return tab_date

    def _cleanup_old_report_tabs(self, keep_days: int = 7):
        """
        Elimina pestañas de informe (Inf_*) con más de keep_days días.
        Acepta el formato nuevo (Inf_YYYY-MM-DD) y el legacy
        (Inf_YYYY-MM-DD_HH:MM) para que las pestañas antiguas también
        se limpien al envejecer.
        """
        cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
        deleted = 0

        try:
            for ws in self.spreadsheet.worksheets():
                tab_date = self._parse_report_tab_date(ws.title)
                if tab_date is not None and tab_date < cutoff:
                    self.spreadsheet.del_worksheet(ws)
                    deleted += 1

            if deleted:
                logger.info(f"Cleanup: {deleted} pestañas de informe antiguas eliminadas (>{keep_days} días)")
        except Exception as e:
            logger.warning(f"Error en cleanup de pestañas: {e}")


# Para pruebas directas
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=config.LOG_FORMAT
    )

    # Verificar configuración
    if not config.GOOGLE_SHEET_ID:
        print("ERROR: GOOGLE_SHEET_ID no configurado en .env")
        print("Por favor, configura las variables de entorno antes de ejecutar.")
        exit(1)

    exporter = GoogleSheetsExporter()

    if exporter.connect():
        print("Conexión exitosa!")
        exporter.setup_sheets()

        counts = exporter.get_row_counts()
        print("\nFilas por pestaña:")
        for sheet, count in counts.items():
            print(f"  {sheet}: {count}")
    else:
        print("Error en la conexión")
