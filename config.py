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

# Timeframe: últimas 4 horas
TIMEFRAME = "now 4-H"

# Rate limiting: segundos entre requests
RATE_LIMIT_SECONDS = 90

# Reintentos en caso de error
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 30

# Proxies rotativos (opcional)
# Formato: ["http://ip:port", "http://user:pass@ip:port", ...]
# Dejar vacío para no usar proxies
PROXIES = os.getenv("PROXIES", "").split(",") if os.getenv("PROXIES") else []

# Distribución de requests
# Divide los países en grupos para ejecutar en diferentes horarios
COUNTRY_GROUPS = {
    "group_1": ["IN", "US", "BR"],      # Horario: 00:00, 12:00
    "group_2": ["ID", "MX", "GB"],      # Horario: 04:00, 16:00
    "group_3": ["AU", "VN", "DE", "RU"] # Horario: 08:00, 20:00
}

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
    "queries_rising": "Related_Queries_Rising",
    "interest_over_time": "Interest_Over_Time"
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

# Términos reducidos para caber en el timeout de GitHub Actions
# Con 4 términos × 3 países × 2 llamadas × 90s = ~36 min
TERMS_REDUCED = [
    "apk",
    "download apk",
    "app download",
    "apk games"
]

CURRENT_TERMS = TERMS_REDUCED
CURRENT_REGIONS = REGIONS_FULL
