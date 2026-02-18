"""
Configuración del sistema de monitoreo de Google Trends.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# Términos a monitorear
# =============================================================================

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

# =============================================================================
# Regiones a monitorear
# =============================================================================

REGIONS_MVP = {"IN": "India"}

REGIONS_FULL = {
    "WW": "Worldwide",
    "IN": "India",
    "US": "United States",
    "BR": "Brazil",
    "ID": "Indonesia",
    "MX": "Mexico",
    "GB": "United Kingdom",
    "PH": "Philippines",
    "AU": "Australia",
    "VN": "Vietnam",
    "DE": "Germany",
    "RU": "Russia",
    "TH": "Thailand",
    "FR": "France",
    "IT": "Italy",
    "CN": "China",
    "JP": "Japan",
    "TR": "Turkey",
    "RO": "Romania",
    "NG": "Nigeria"
}

# =============================================================================
# Configuración de Google Trends
# =============================================================================

# Timeframe: últimas 4 horas
TIMEFRAME = "now 4-H"

# Rate limiting: segundos entre requests
RATE_LIMIT_SECONDS = 200

# Reintentos en caso de error
# Basado en análisis de logs: si 2 intentos fallan, el 3ro también fallará
MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 30

# Límite máximo de backoff para 429 (en segundos)
# Basado en análisis: esperas >180s no mejoran la recuperación
MAX_BACKOFF_SECONDS = 180

# Proxies rotativos (opcional)
# Formato: ["http://ip:port", "http://user:pass@ip:port", ...]
# Dejar vacío para no usar proxies
PROXIES = os.getenv("PROXIES", "").split(",") if os.getenv("PROXIES") else []

# Distribución de requests
# Divide los países en grupos para ejecutar en diferentes horarios
# 20 regiones / 5 grupos = 4 regiones por grupo
# Base: 3 términos × 4 regiones × 200s = 40 min (timeout 90 min)
# Con COUNTRY_EXTRA_TERMS: 13-16 requests por grupo = 43-53 min
COUNTRY_GROUPS = {
    "group_1": ["WW", "IN", "US", "BR"],  # 00:00, 12:00 UTC — Global + Americas
    "group_2": ["ID", "MX", "PH", "GB"],  # 02:25, 14:25 UTC — SE Asia + Americas + Europe
    "group_3": ["AU", "VN", "DE", "RU"],  # 04:50, 16:50 UTC — Asia-Pacific + Europe
    "group_4": ["TH", "FR", "IT", "CN"],  # 07:15, 19:15 UTC — Asia + Europe
    "group_5": ["JP", "TR", "RO", "NG"]   # 09:40, 21:40 UTC — Asia + Europe + Africa
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
# Configuración actual
# =============================================================================

# Términos reducidos para caber en el timeout de GitHub Actions
# 3 términos × 4 regiones/grupo × 200s = ~40 min por grupo (timeout 90 min)
TERMS_REDUCED = [
    "apk",
    "download apk",
    "app download"
]

# Términos extra por país (se SUMAN a CURRENT_TERMS, no los reemplazan)
# Países sin entrada (WW, IN, US, GB, PH, AU, VN, NG) usan solo los 3 base
COUNTRY_EXTRA_TERMS = {
    "BR": ["baixar apk"],           # Portugués
    "MX": ["descargar apk"],        # Español
    "ID": ["unduh apk"],            # Bahasa Indonesia
    "DE": ["apk herunterladen"],    # Alemán
    "RU": ["скачать apk"],          # Ruso
    "TH": ["ดาวน์โหลด apk"],       # Tailandés
    "FR": ["télécharger apk"],      # Francés
    "IT": ["scaricare apk"],        # Italiano
    "TR": ["apk indir"],            # Turco
    "JP": ["apkダウンロード"],       # Japonés
    "CN": ["下载apk"],              # Chino
    "RO": ["descărcare apk"],       # Rumano
}

CURRENT_TERMS = TERMS_REDUCED
CURRENT_REGIONS = REGIONS_FULL
