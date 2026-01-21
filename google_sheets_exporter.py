"""
Exportador de datos a Google Sheets usando gspread.
"""
import logging
from typing import List, Dict, Optional

import gspread
from google.oauth2.service_account import Credentials

import config
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
        return mapping.get(data_type, 'Unknown')

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

            except Exception as e:
                logger.error(f"Error exportando a '{sheet_name}': {e}")
                export_counts[sheet_name] = 0

        return export_counts

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
