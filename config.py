"""
Configuración del sistema de monitoreo de Google Trends.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# FASE 1 (MVP): Configuración básica
# =============================================================================

# Términos a monitorear
# Fase 1: Solo "apk"
# Fase 2: Todos los términos
TERMS_MVP = ["apk"]

TERMS_FULL = [
    "apk",
    "download apk",
    "android apk",
    "apk games",
    "app download",
    "latest apk version",
    "obb file download"
]

# Regiones a monitorear
# Fase 1: Solo India
# Fase 3: Múltiples países
REGIONS_MVP = {"IN": "India"}

REGIONS_FULL = {
    "IN": "India",
    "US": "United States",
    "BR": "Brazil",
    "ID": "Indonesia",
    "MX": "Mexico",
    "GB": "United Kingdom",
    "AU": "Australia",
    "VN": "Vietnam",
    "DE": "Germany",
    "RU": "Russia"
}

# =============================================================================
# Configuración de Google Trends
# =============================================================================

# Timeframe: últimas 24 horas
TIMEFRAME = "now 1-d"

# Rate limiting: segundos entre requests
RATE_LIMIT_SECONDS = 90

# Reintentos en caso de error
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 30

# =============================================================================
# Configuración de Google Sheets
# =============================================================================

# ID del Google Sheet (extraer de la URL del sheet)
# Ejemplo: https://docs.google.com/spreadsheets/d/SHEET_ID/edit
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

# Ruta al archivo de credenciales de servicio
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")

# Nombres de las pestañas
SHEET_NAMES = {
    "topics_top": "Related_Topics_Top",
    "topics_rising": "Related_Topics_Rising",
    "queries_top": "Related_Queries_Top",
    "queries_rising": "Related_Queries_Rising"
}

# =============================================================================
# Configuración de Logging
# =============================================================================

LOG_DIR = "logs"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_LEVEL = "INFO"

# =============================================================================
# Configuración actual según fase
# =============================================================================

# Fase 2: Todos los términos y regiones
CURRENT_TERMS = TERMS_FULL
CURRENT_REGIONS = REGIONS_FULL
