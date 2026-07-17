"""
Generador de informes para el equipo de contenidos.

Procesa los datos extraídos de Google Trends y genera informes
accionables clasificando las apps/términos detectados.
"""
import logging
import re
import unicodedata
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

from trends_scraper import TrendData

logger = logging.getLogger(__name__)


# =============================================================================
# Configuración de filtrado
# =============================================================================

# Términos genéricos que no son apps específicas (ignorar en informes)
# IMPORTANTE: Solo términos COMPLETOS, no palabras que pueden ser parte de nombres de apps
GENERIC_TERMS = {
    # Términos de búsqueda genéricos sobre APKs
    "apk", "apk download", "download apk", "free apk", "apk free",
    "android apk", "apk android", "app download", "download app",
    "mod apk", "apk mod", "premium apk", "pro apk",
    "latest apk", "new apk", "update apk", "apk update",
    "apk games", "games apk", "free games", "android games",
    "app store", "play store", "apk store", "google play",
    "google play store", "play store apk", "ch play", "chplay",
    "obb file", "obb download", "apk obb",
    "old version", "latest version", "new version",
    # Palabras sueltas que NO son apps
    "download", "free", "app", "apps", "game", "games",
    "android", "ios", "mobile", "online", "offline",
    "mod", "hack", "update", "install", "best",
    # Stores de APKs (competidores, no apps para el catálogo)
    "apkpure", "apk pure", "apkmirror", "apk mirror",
    "apkcombo", "apk combo", "apkmody", "apk mody",
    "happymod", "happy mod", "aptoide",
    # Términos en otros idiomas comunes
    "descargar", "descargar apk", "baixar", "baixar apk",
    "télécharger", "скачать", "indir", "unduh",
    "تحميل", "ダウンロード", "下载",
}

# Patrones que indican términos técnicos o no accionables
TECHNICAL_PATTERNS = [
    r"^com\.\w+\.",  # Package names (com.google.android...)
    r"version\s+\d+\.\d+",  # Versiones específicas con "version"
    r"arm64|armeabi|x86",  # Arquitecturas de CPU
]

# Apps que requieren revisión especial (pueden ser problemáticas)
# - Descargadores de contenido protegido
# - Apps de gambling/apuestas
# - Emuladores de consolas recientes
#
# NOTA: Cada patrón tiene ejemplos de qué detecta para facilitar mantenimiento
WATCHLIST_PATTERNS = [
    # --- Descargadores de YouTube/redes sociales ---
    # Detecta: "y2mate", "y2mate apk", "snaptube pro", "vidmate download"
    r"y2mate|y2meta|snaptube|vidmate|tubemate|savefrom",

    # Detecta: "youtube downloader", "tiktok video saver", "facebook download"
    r"(youtube|tiktok|instagram|facebook).*(downloader|download|saver)",

    # Detecta: "downloader for youtube", "video saver instagram"
    r"(downloader|saver).*(youtube|tiktok|instagram|facebook)",

    # --- Gambling / Apuestas / Casinos ---
    # Detecta: "casino slots", "poker online", "bet365", "apuestas deportivas"
    r"(casino|slot|poker|bet|betting|apuesta)",

    # Detecta: "winclub", "sun.win", "789bet", "888casino"
    r"(win|sun|789|888)\.?(club|win|bet|casino)",

    # --- Mods de juegos online (posibles cheats) ---
    # Detecta: "free fire mod apk", "pubg hack", "cod mobile cheat"
    r"(free fire|pubg|cod|call of duty).*(mod|hack|cheat)",

    # --- Apps de streaming pirata ---
    # Detecta: "pelisplus apk", "cuevana 3", "stremio addon", "popcorn time"
    r"(pelisplus|cuevana|stremio|popcorn)",
]

# Patrones regex para detectar términos genéricos
GENERIC_PATTERNS = [
    r"^(how to|como|cómo|what is|que es|qué es)",  # Preguntas
    r"(free download|download free|gratis)$",
    r"^(best|top|new|latest|old)\s+(app|apps|game|games|apk)s?$",  # "best apps", "top games"
    r"^(mod|hack|crack|cheat|unlimited)\s*(apk|money|coins|gems)?$",  # Solo si es el término completo
    r"^\d+(\.\d+)*$",  # Solo números de versión
]

# =============================================================================
# Casino / Betting (sección propia, fuera de apps detectadas)
# =============================================================================

# Patrones de apps de casino/apuestas. Cuidado con falsos positivos:
# "roblox", "minecraft" o un número suelto NO deben coincidir.
CASINO_PATTERNS = re.compile(
    r"(?:"
    r"\bbet(?:s|ting)?\b"                     # bet, bets, betting (no "alphabet")
    r"|\bcasino\b|\bjackpots?\b|\bbingo\b"
    r"|\bslots?\b|\brummy\b"
    r"|\bteen\s?patti\b|\baviator\b"
    r"|\bjeet\w*\b"                           # jeet, jeetwin, jeetbuzz, "365 jeet"
    r"|\blott(?:ery|o)\b"
    r"|\bfire\s?kirin\b|\borion\s?stars?\b"
    r"|\bgame\s?vault\b|\bjuwa\b|\bmilky\s?way\b"
    r"|\bwinzo\b|\bcash\s?game\b"
    r"|\b(?:\d+xbet|4rabet|melbet|betway|parimatch|dafabet|linebet|mostbet)\b"
    # Nombres estilo gambling con prefijo numérico: "789 jackpots", "777win",
    # "91 club", "bg 678 game", "789bingo". Un número solo no coincide.
    r"|\b\d{2,4}\s?(?:win|bet|club|game|jackpot|bingo|casino|lotto)s?\b"
    r"|\bbet\s?\d{2,4}\b"                     # bet365, bet 999
    r")",
    re.IGNORECASE
)

# =============================================================================
# Detector estricto de apps (evita "Ocular Migraine", "Come", etc.)
# =============================================================================

# Tokens que indican intención de app/descarga en el título de la query
# (el texto se compara ya sin diacríticos: aplicación→aplicacion, télécharger→telecharger)
APP_TOKEN_PATTERN = re.compile(
    r"\b(?:apk|apps?|download|insta?ll?|aplicacion(?:es)?|aplikasi|indir|"
    r"baixar|descargar|unduh|telecharger|mod|скачать)\b"
    r"|pro\s+version",
    re.IGNORECASE
)

# Tokens no latinos que se comprueban por substring sobre el título crudo
# (el tailandés pierde marcas combinantes al quitar diacríticos)
APP_TOKEN_SUBSTRINGS = ("ดาวน์โหลด",)

# Stoplist explícita: términos que nunca son apps aunque pasen otros filtros
APP_STOPWORDS = {
    "come", "lite", "ocular migraine", "news", "weather",
    "today", "tomorrow", "near me", "meaning",
}


@dataclass
class ReportItem:
    """Elemento individual del informe."""
    name: str  # Nombre normalizado de la app/término
    original_titles: List[str]  # Títulos originales encontrados
    data_type: str  # 'queries_top', 'queries_rising', etc.
    countries: List[str]  # Países donde apareció
    max_value: str  # Valor máximo (score o porcentaje)
    is_rising: bool  # Si es trending/rising
    links: List[str]  # Links a Google Trends
    versions: List[str] = field(default_factory=list)  # Versiones específicas detectadas
    needs_review: bool = False  # Si requiere revisión especial (watchlist)
    review_reason: str = ""  # Razón por la que necesita revisión
    # Categoría: 'app' (normal) o 'casino' (casino/apuestas, sección propia)
    category: str = 'app'
    # Señal RSS: True si el término también aparece en Trending Now de Google
    rss_trending: bool = False
    # Novelty detection
    novelty: str = ""  # 'nueva' | 'resurgente' | 'conocida' | ''
    first_seen: Optional[str] = None  # Fecha primera vez vista
    # Trend velocity
    velocity: str = ""  # 'acelerando' | 'estable' | 'decayendo' | ''
    velocity_change: float = 0.0  # % cambio 24h
    # Cross-region
    spread_score: int = 0  # Número de países únicos

    def __post_init__(self):
        # Asegurar que las listas no tengan duplicados
        self.original_titles = list(set(self.original_titles))
        self.countries = list(set(self.countries))
        self.links = list(set(self.links))
        self.versions = list(set(self.versions))
        self.spread_score = len(self.countries)


@dataclass
class ContentReport:
    """Informe completo para el equipo de contenidos."""
    timestamp: str
    group: Optional[str]
    regions: List[str]

    # Items clasificados
    potential_apps: List[ReportItem] = field(default_factory=list)  # Apps normales
    watchlist_apps: List[ReportItem] = field(default_factory=list)  # Apps que requieren revisión
    generic_terms: List[ReportItem] = field(default_factory=list)  # Términos genéricos ignorados
    technical_terms: List[ReportItem] = field(default_factory=list)  # Términos técnicos ignorados
    casino_apps: List[ReportItem] = field(default_factory=list)  # Casino/apuestas (sección propia)
    no_app_terms: List[ReportItem] = field(default_factory=list)  # Sin señal de app (filtrados)

    # Nuevas secciones
    new_apps: List[ReportItem] = field(default_factory=list)  # Apps nunca vistas antes
    global_trends: List[ReportItem] = field(default_factory=list)  # Apps en 3+ países
    accelerating: List[ReportItem] = field(default_factory=list)  # Apps acelerando

    # Resumen ejecutivo
    executive_summary: List[str] = field(default_factory=list)

    # Estadísticas
    total_items_processed: int = 0
    total_unique_terms: int = 0


class ReportGenerator:
    """
    Genera informes procesados a partir de datos de Google Trends.
    """

    def __init__(self, db=None):
        """
        Args:
            db: TrendsDatabase instance (opcional). Si se proporciona, habilita
                novelty detection, trend velocity y enriquecimiento de datos.
        """
        self.db = db
        self.generic_terms = GENERIC_TERMS
        self.generic_patterns = [re.compile(p, re.IGNORECASE) for p in GENERIC_PATTERNS]
        self.technical_patterns = [re.compile(p, re.IGNORECASE) for p in TECHNICAL_PATTERNS]
        self.watchlist_patterns = [re.compile(p, re.IGNORECASE) for p in WATCHLIST_PATTERNS]

    def _check_watchlist(self, title: str) -> Tuple[bool, str]:
        """
        Verifica si un término está en la watchlist (requiere revisión).

        Args:
            title: Título a evaluar

        Returns:
            Tuple de (needs_review, reason)
        """
        normalized = title.lower().strip()

        watchlist_reasons = {
            0: "Descargador de contenido",
            1: "Descargador de contenido",
            2: "Descargador de contenido",
            3: "Gambling/Apuestas",
            4: "Gambling/Apuestas",
            5: "Posible cheat/hack",
            6: "Streaming no oficial",
        }

        for i, pattern in enumerate(self.watchlist_patterns):
            if pattern.search(normalized):
                reason = watchlist_reasons.get(i, "Requiere revisión")
                return (True, reason)

        return (False, "")

    def _extract_version(self, title: str) -> Optional[str]:
        """
        Extrae la versión de un título si la tiene.

        Args:
            title: Título original

        Returns:
            Versión extraída o None
        """
        # Patrones de versión comunes
        version_patterns = [
            r'(\d+\.\d+\.\d+)',  # 1.21.131
            r'(\d+\.\d+\s*\d*)',  # 1.4 5 o 1.4.5
            r'v(\d+[\d.]*)',  # v2.0
            r'patch\s*(\d+[\d.]*)',  # patch 1.21.131
        ]

        for pattern in version_patterns:
            match = re.search(pattern, title.lower())
            if match:
                return match.group(1).strip()

        return None

    def _get_base_app_name(self, title: str) -> str:
        """
        Extrae el nombre base de la app sin versión.

        Args:
            title: Título original

        Returns:
            Nombre base de la app
        """
        normalized = title.lower().strip()

        # Remover acentos/diacríticos (consistente con database._normalize_title)
        normalized = unicodedata.normalize('NFKD', normalized)
        normalized = ''.join(c for c in normalized if not unicodedata.combining(c))

        # Remover sufijos de APK primero
        suffixes = [' apk', ' app', ' download', ' android', ' ios', ' for android', ' for ios']
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()

        # Remover palabras "gratis/free" en varios idiomas al final
        free_words = [
            r'\s+miễn phí$',  # vietnamita
            r'\s+gratis$',  # español/portugués
            r'\s+free$',  # inglés
            r'\s+gratuit$',  # francés
            r'\s+бесплатно$',  # ruso
        ]
        for pattern in free_words:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

        # Remover patrones de versión
        patterns_to_remove = [
            r'\s+\d+\.\d+[\d.\s]*$',  # 1.21.131 al final
            r'\s+v\d+[\d.]*$',  # v2.0 al final
            r'\s+patch\s*\d+[\d.]*$',  # patch 1.21 al final
            r'\s+patch$',  # solo "patch" al final
            r'\s+version\s*\d+[\d.]*$',  # version 1.0 al final
            r'\s+\d+\s+\d+[\d.\s]*$',  # "1 4 5" al final (terraria 1.4 5)
        ]

        for pattern in patterns_to_remove:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

        # Limpiar espacios
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    def _normalize_term(self, title: str) -> str:
        """
        Normaliza un término para comparación y agrupación.

        Args:
            title: Título original

        Returns:
            Término normalizado (lowercase, sin espacios extra, sin sufijos genéricos)
        """
        # Lowercase y limpiar espacios
        normalized = title.lower().strip()
        normalized = re.sub(r'\s+', ' ', normalized)

        # Remover SOLO sufijos que no aportan info (apk, download, android)
        # Mantener: pro, premium, lite, etc. porque pueden ser versiones distintas
        suffixes_to_remove = [' apk', ' app', ' download', ' android', ' ios', ' for android', ' for ios']
        for suffix in suffixes_to_remove:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()

        return normalized

    def _get_display_name(self, title: str) -> str:
        """
        Obtiene el nombre para mostrar (más legible que el normalizado).

        Args:
            title: Título original

        Returns:
            Nombre formateado para mostrar
        """
        # Limpiar pero mantener modificadores importantes
        display = title.strip()
        display = re.sub(r'\s+', ' ', display)

        # Remover solo "apk", "download", "android" del final
        patterns_to_remove = [
            r'\s+apk$', r'\s+APK$', r'\s+Apk$',
            r'\s+download$', r'\s+Download$',
            r'\s+android$', r'\s+Android$',
            r'\s+for android$', r'\s+for Android$',
            r'\s+for ios$', r'\s+for iOS$',
        ]
        for pattern in patterns_to_remove:
            display = re.sub(pattern, '', display, flags=re.IGNORECASE)

        # Capitalizar apropiadamente
        words = display.split()
        capitalized = []

        for word in words:
            # Mantener mayúsculas para acrónimos cortos o palabras ya en mayúsculas
            if len(word) <= 3 and word.isupper():
                capitalized.append(word)
            elif word.isupper() and len(word) > 3:
                # Palabra larga en mayúsculas -> capitalizar normal
                capitalized.append(word.capitalize())
            else:
                capitalized.append(word.capitalize())

        return ' '.join(capitalized)

    def _is_generic_term(self, title: str) -> bool:
        """
        Determina si un término es genérico (no es una app específica).

        Args:
            title: Título a evaluar

        Returns:
            True si es genérico
        """
        normalized = title.lower().strip()

        # Verificar contra lista de términos genéricos
        if normalized in self.generic_terms:
            return True

        # Verificar contra patrones regex genéricos
        for pattern in self.generic_patterns:
            if pattern.search(normalized):
                return True

        # Verificar contra patrones técnicos (package names, versiones específicas, etc.)
        for pattern in self.technical_patterns:
            if pattern.search(normalized):
                return True

        # Términos muy cortos (1-2 caracteres) son probablemente genéricos
        if len(normalized) <= 2:
            return True

        return False

    def _extract_app_name(self, original_titles: List[str], use_base_name: bool = True) -> str:
        """
        Extrae el mejor nombre de app de una lista de títulos originales.

        Args:
            original_titles: Lista de títulos encontrados para el mismo término
            use_base_name: Si True, extrae el nombre base sin versión

        Returns:
            Nombre de app más representativo
        """
        if not original_titles:
            return "Unknown"

        # Obtener nombres base de todos los títulos
        if use_base_name:
            base_names = [self._get_base_app_name(t) for t in original_titles]
            # Usar el nombre base más común o el más largo
            from collections import Counter
            name_counts = Counter(base_names)
            # Preferir la variante con espacios ("789 bingo" sobre "789bingo"),
            # luego la más frecuente
            most_common = max(
                name_counts.items(),
                key=lambda kv: (' ' in kv[0], kv[1], len(kv[0]))
            )[0]

            # Si hay un nombre base claro, usarlo
            if most_common:
                return self._get_display_name(most_common)

        # Fallback: usar el título más representativo
        best_title = original_titles[0]
        for title in original_titles:
            if not title.isupper() and not title.islower():
                if len(title) >= len(best_title):
                    best_title = title
            elif len(title) > len(best_title):
                best_title = title

        return self._get_display_name(best_title)

    def _parse_value(self, value: str) -> Tuple[int, bool]:
        """
        Parsea el valor de un item de Trends.

        Args:
            value: Valor como string (ej: "100", "Breakout", "+500%")

        Returns:
            Tuple de (valor numérico, es_rising)
        """
        if not value:
            return (0, False)

        value_str = str(value).strip()

        # Detectar si es rising/breakout
        is_rising = False
        if 'breakout' in value_str.lower() or value_str.startswith('+'):
            is_rising = True

        # Extraer valor numérico
        numeric = re.sub(r'[^\d]', '', value_str)
        try:
            numeric_value = int(numeric) if numeric else 0
        except ValueError:
            numeric_value = 0

        # Breakout tiene valor muy alto implícito
        if 'breakout' in value_str.lower():
            numeric_value = 9999

        return (numeric_value, is_rising)

    def _is_technical_term(self, title: str) -> bool:
        """Verifica si es un término técnico (package name, arquitectura, etc.)."""
        normalized = title.lower().strip()
        for pattern in self.technical_patterns:
            if pattern.search(normalized):
                return True
        return False

    @staticmethod
    def _strip_diacritics(text: str) -> str:
        """Quita diacríticos (consistente con database._normalize_title)."""
        text = unicodedata.normalize('NFKD', text)
        return ''.join(c for c in text if not unicodedata.combining(c))

    def _title_has_app_token(self, title: str) -> bool:
        """
        Verifica si un título contiene un token de app/descarga
        (apk, download, indir, скачать, mod, etc.).
        """
        if not title:
            return False
        raw = title.lower()
        # Tokens no latinos: substring sobre el crudo (el tailandés
        # pierde marcas combinantes al normalizar)
        for token in APP_TOKEN_SUBSTRINGS:
            if token in raw:
                return True
        stripped = self._strip_diacritics(raw)
        return bool(APP_TOKEN_PATTERN.search(stripped))

    def _is_casino_term(self, norm_name: str, original_titles: List[str]) -> bool:
        """
        Clasifica como casino/apuestas usando el nombre normalizado
        Y los títulos originales de las queries.
        """
        candidates = [norm_name] + [
            self._strip_diacritics(t.lower()) for t in original_titles
        ]
        return any(CASINO_PATTERNS.search(c) for c in candidates if c)

    def _build_token_backed_titles(self, data: List[TrendData]) -> List[str]:
        """
        Recolecta los títulos normalizados del batch que SÍ tienen token de app.
        Sirven de respaldo para títulos sin token ("minecraft" sobrevive porque
        existe "minecraft son surum apk indir" en el mismo batch).
        """
        backed = set()
        for item in data:
            if self._title_has_app_token(item.title):
                normalized = self._strip_diacritics(item.title.lower().strip())
                normalized = re.sub(r'\s+', ' ', normalized)
                backed.add(normalized)
        return list(backed)

    @staticmethod
    def _is_token_backed(base_name: str, backed_titles: List[str]) -> bool:
        """
        True si el nombre base aparece en algún título con token de app del batch.
        Semántica prefix / word-boundary (igual que database.get_velocity).
        """
        if len(base_name) < 2:
            return False
        for title in backed_titles:
            if (title == base_name
                    or title.startswith(base_name + " ")
                    or f" {base_name} " in title
                    or title.endswith(" " + base_name)):
                return True
        return False

    def _passes_app_filter(self, norm_name: str, info: Dict,
                           backed_titles: List[str]) -> bool:
        """
        Detector estricto de apps: un título sin token de app solo se acepta
        si su nombre base aparece con token en otra query del mismo batch,
        o si trending en 2+ países (ante la duda, mantener).
        """
        # Stoplist explícita: nunca son apps
        if norm_name in APP_STOPWORDS:
            return False
        # Tiene token de app en alguno de sus títulos
        if any(self._title_has_app_token(t) for t in info['original_titles']):
            return True
        # Respaldado por otra query del batch con token
        if self._is_token_backed(norm_name, backed_titles):
            return True
        # Ante la duda, mantener: trending en 2+ países es señal suficiente
        if len(set(info['countries'])) >= 2:
            return True
        # Rescate por historial: si es una app ya conocida en apps_seen
        # (vista 2+ veces), un título pelado sigue siendo señal válida
        # (ej: "telegram" a secas). Degrada limpio si Turso no está.
        if self.db is not None:
            try:
                if self.db.is_known_app(norm_name):
                    return True
            except Exception:
                pass
        # Sin señal de app: filtrar (ej: "ocular migraine", "come")
        return False

    def _format_score(self, item: ReportItem) -> str:
        """
        Formatea el score con unidades para renders (no toca datos crudos):
        - "Breakout" se mantiene como "Breakout"
        - Rising con valor >= 1000 → "+39,400%"
        - Top → número plano 0-100
        """
        raw = str(item.max_value).strip()
        if 'breakout' in raw.lower():
            return "Breakout"
        numeric, _ = self._parse_value(raw)
        if item.is_rising and numeric >= 1000:
            return f"+{numeric:,}%"
        return raw

    @staticmethod
    def _sheet_tipo(item: ReportItem) -> str:
        """Columna Tipo para Sheets, con badge RSS si aplica."""
        tipo = "🔥 Rising" if item.is_rising else "📈 Top"
        if item.rss_trending:
            tipo = tipo.replace(" ", "📰 ", 1)
        return tipo

    def _match_rss_trending(self, items: List[ReportItem],
                            rss_titles: Optional[List[str]]) -> List[ReportItem]:
        """
        Marca items que también aparecen en Trending Now (RSS) de Google.
        Match: nombre base igual, prefijo, o palabra dentro del título RSS
        (misma semántica prefix / " word" que database.get_velocity).
        """
        if not rss_titles:
            return []

        normalized_rss = [self._get_base_app_name(t) for t in rss_titles if t]
        normalized_rss = [t for t in normalized_rss if t]

        matched = []
        for item in items:
            base = self._get_base_app_name(item.name)
            if len(base) < 3:  # nombres muy cortos generan falsos positivos
                continue
            for rss_title in normalized_rss:
                if (rss_title == base
                        or rss_title.startswith(base + " ")
                        or f" {base} " in f" {rss_title} "
                        or rss_title.endswith(" " + base)):
                    item.rss_trending = True
                    matched.append(item)
                    break
        return matched

    def generate(self, data: List[TrendData], group: Optional[str] = None,
                 rss_titles: Optional[List[str]] = None) -> ContentReport:
        """
        Genera un informe a partir de los datos extraídos.

        Args:
            data: Lista de TrendData del scraper
            group: Nombre del grupo ejecutado (opcional)
            rss_titles: Títulos de Trending Now (RSS) de Google para las
                regiones del grupo (opcional). Los items que coincidan se
                marcan con rss_trending=True y badge 📰 en los renders.

        Returns:
            ContentReport con items clasificados
        """
        if not data:
            return ContentReport(
                timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                group=group,
                regions=[],
                total_items_processed=0,
                total_unique_terms=0
            )

        # Extraer regiones únicas
        regions = list(set(item.country_code for item in data))

        # Títulos con token de app del batch (respaldo para el detector estricto)
        token_backed_titles = self._build_token_backed_titles(data)

        # Primera pasada: agrupar por nombre BASE de app (sin versión)
        # Esto permite agrupar "terraria 1.4.5" y "terraria 1.4 5" bajo "terraria".
        # La clave de agrupación colapsa espacios ("789 bingo" ≡ "789bingo"),
        # pero se conserva la variante CON espacios para clasificar y mostrar.
        base_grouped: Dict[str, Dict] = {}

        for item in data:
            # Obtener nombre base sin versión
            base_name = self._get_base_app_name(item.title)
            normalized = self._normalize_term(base_name)

            # Clave sin espacios: dedup "789 bingo" / "789bingo"
            key = normalized.replace(' ', '')

            # Extraer versión si existe
            version = self._extract_version(item.title)

            if key not in base_grouped:
                base_grouped[key] = {
                    'norm_name': normalized,
                    'original_titles': [],
                    'data_types': set(),
                    'countries': [],
                    'values': [],
                    'links': [],
                    'is_rising': False,
                    'versions': set(),
                }

            # Preferir la variante normalizada CON espacios para mostrar/clasificar
            if ' ' in normalized and ' ' not in base_grouped[key]['norm_name']:
                base_grouped[key]['norm_name'] = normalized

            base_grouped[key]['original_titles'].append(item.title)
            base_grouped[key]['data_types'].add(item.data_type)
            base_grouped[key]['countries'].append(item.country_name)
            base_grouped[key]['values'].append(item.value)
            base_grouped[key]['links'].append(item.link)

            if version:
                base_grouped[key]['versions'].add(version)

            if 'rising' in item.data_type:
                base_grouped[key]['is_rising'] = True

        # Clasificar cada término
        potential_apps: List[ReportItem] = []
        watchlist_apps: List[ReportItem] = []
        generic_terms: List[ReportItem] = []
        technical_terms: List[ReportItem] = []
        casino_apps: List[ReportItem] = []
        no_app_terms: List[ReportItem] = []

        for _key, info in base_grouped.items():
            normalized = info['norm_name']
            # Determinar el valor máximo y si es rising
            max_value = "0"
            is_rising = info['is_rising']

            for val in info['values']:
                parsed_val, val_rising = self._parse_value(val)
                current_max, _ = self._parse_value(max_value)
                if parsed_val > current_max:
                    max_value = val
                if val_rising:
                    is_rising = True

            # Determinar data_type principal (priorizar rising)
            data_types = info['data_types']
            if any('rising' in dt for dt in data_types):
                primary_type = [dt for dt in data_types if 'rising' in dt][0]
            else:
                primary_type = list(data_types)[0]

            # Verificar watchlist
            needs_review, review_reason = self._check_watchlist(normalized)

            # Clasificar casino/apuestas (query original Y nombre normalizado)
            is_casino = self._is_casino_term(normalized, info['original_titles'])

            report_item = ReportItem(
                name=self._extract_app_name(info['original_titles']),
                original_titles=info['original_titles'],
                data_type=primary_type,
                countries=info['countries'],
                max_value=max_value,
                is_rising=is_rising,
                links=info['links'],
                versions=list(info['versions']),
                needs_review=needs_review,
                review_reason=review_reason,
                category='casino' if is_casino else 'app'
            )

            # Clasificar en la categoría apropiada
            if self._is_technical_term(normalized):
                technical_terms.append(report_item)
            elif self._is_generic_term(normalized):
                generic_terms.append(report_item)
            elif is_casino:
                # Casino va a su propia sección (fuera de watchlist y apps)
                casino_apps.append(report_item)
            elif needs_review:
                watchlist_apps.append(report_item)
            elif not self._passes_app_filter(normalized, info, token_backed_titles):
                # Detector estricto: sin señal de app ("ocular migraine", "come")
                no_app_terms.append(report_item)
            else:
                potential_apps.append(report_item)

        # Ordenar por relevancia (rising primero, luego por valor)
        def sort_key(item: ReportItem) -> Tuple[int, int, int]:
            val, _ = self._parse_value(item.max_value)
            return (
                0 if item.is_rising else 1,  # Rising primero
                -val,  # Mayor valor primero
                -len(item.countries)  # Más países primero
            )

        potential_apps.sort(key=sort_key)
        watchlist_apps.sort(key=sort_key)
        generic_terms.sort(key=sort_key)
        technical_terms.sort(key=sort_key)
        casino_apps.sort(key=sort_key)
        no_app_terms.sort(key=sort_key)

        if no_app_terms:
            logger.info(
                f"No-app filtrados ({len(no_app_terms)}): "
                f"{', '.join(i.name for i in no_app_terms[:10])}"
            )

        # Enriquecer con datos de Turso si está disponible
        # (casino incluido: novelty/velocity también son útiles ahí)
        all_actionable = potential_apps + watchlist_apps + casino_apps
        if self.db and self.db.is_connected and all_actionable:
            self._enrich_with_db(all_actionable)
            # Recalcular spread_score post-enrich (por si el enriquecimiento modificó countries)
            for item in all_actionable:
                item.spread_score = len(set(item.countries))

        # Señal RSS: marcar items que también están en Trending Now de Google
        rss_matched = self._match_rss_trending(all_actionable, rss_titles)

        # Clasificar secciones especiales (casino excluido: solo potential_apps)
        new_apps = [item for item in potential_apps if item.novelty == 'nueva']
        global_trends = [item for item in potential_apps if item.spread_score >= 3]
        global_trends.sort(key=lambda x: -x.spread_score)
        accelerating = [item for item in potential_apps if item.velocity == 'acelerando']
        accelerating.sort(key=lambda x: -x.velocity_change)

        # Generar resumen ejecutivo (sin contar casino)
        executive_summary = self._generate_executive_summary(
            potential_apps, watchlist_apps, new_apps, global_trends, accelerating,
            rss_matched=rss_matched
        )

        return ContentReport(
            timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            group=group,
            regions=regions,
            potential_apps=potential_apps,
            watchlist_apps=watchlist_apps,
            generic_terms=generic_terms,
            technical_terms=technical_terms,
            casino_apps=casino_apps,
            no_app_terms=no_app_terms,
            new_apps=new_apps,
            global_trends=global_trends,
            accelerating=accelerating,
            executive_summary=executive_summary,
            total_items_processed=len(data),
            total_unique_terms=len(base_grouped)
        )

    def _enrich_with_db(self, items: List[ReportItem]):
        """Enriquece ReportItems con novelty y velocity desde Turso."""
        # Velocity en batch: una sola lectura de la ventana de 14 días para
        # todos los items (la versión por-item hacía 4 escaneos LIKE cada una
        # y agotó la cuota mensual de lecturas de Turso en jul-2026)
        try:
            velocities = self.db.get_velocities_batch([item.name for item in items])
        except Exception as e:
            logger.warning(f"Velocity batch falló: {e}")
            velocities = {}

        for item in items:
            try:
                # Novelty detection (lookup por clave primaria, barato)
                status, first_seen = self.db.get_novelty_status(item.name)
                item.novelty = status
                item.first_seen = first_seen

                # Trend velocity (del batch)
                velocity = velocities.get(item.name, {})
                item.velocity = velocity.get('trend', '')
                item.velocity_change = velocity.get('change_24h', 0.0)
            except Exception as e:
                logger.warning(f"Error enriqueciendo '{item.name}': {e}")

    def _generate_executive_summary(
        self,
        potential_apps: List[ReportItem],
        watchlist_apps: List[ReportItem],
        new_apps: List[ReportItem],
        global_trends: List[ReportItem],
        accelerating: List[ReportItem],
        rss_matched: Optional[List[ReportItem]] = None
    ) -> List[str]:
        """Genera 3-5 bullets de resumen ejecutivo."""
        summary = []

        # Señal RSS: item también en Trending Now de Google (casino excluido)
        rss_apps = [i for i in (rss_matched or []) if i.category != 'casino']
        if rss_apps:
            top = rss_apps[0]
            extra = f" (+{len(rss_apps) - 1} más)" if len(rss_apps) > 1 else ""
            summary.append(
                f"{top.name} también está en Trending Now de Google (señal fuerte){extra}"
            )

        # Apps nuevas
        if new_apps:
            names = [a.name for a in new_apps[:3]]
            extra = f" (+{len(new_apps) - 3} mas)" if len(new_apps) > 3 else ""
            summary.append(f"Se detectaron {len(new_apps)} apps nuevas: {', '.join(names)}{extra}")

        # Tendencias globales
        if global_trends:
            top = global_trends[0]
            summary.append(
                f"{top.name} trending en {top.spread_score} paises simultaneamente"
            )

        # Apps acelerando
        if accelerating:
            top = accelerating[0]
            summary.append(
                f"{top.name} esta acelerando ({'+' if top.velocity_change > 0 else ''}{top.velocity_change}% vs ayer)"
            )

        # Watchlist
        if watchlist_apps:
            summary.append(f"Watchlist: {len(watchlist_apps)} items requieren revision")

        # Total si no hay highlights
        if not summary:
            summary.append(f"{len(potential_apps)} apps detectadas, sin novedades destacadas")

        return summary

    def _format_app_line(self, item: ReportItem, include_versions: bool = True, show_novelty: bool = False) -> str:
        """Formatea una línea de app para Slack."""
        # Emoji según tipo
        if item.is_rising:
            emoji = "🔥"
            type_label = "Rising"
        else:
            emoji = "📈"
            type_label = "Top"

        # Badge RSS: también en Trending Now de Google
        if item.rss_trending:
            emoji += "📰"

        # Badge de novedad
        novelty_badge = ""
        if show_novelty and item.novelty == 'nueva':
            novelty_badge = "🆕 "
        elif show_novelty and item.novelty == 'resurgente':
            novelty_badge = "🔄 "

        # Países (abreviar si son muchos)
        countries_unique = list(set(item.countries))
        if len(countries_unique) > 3:
            countries_str = f"{', '.join(countries_unique[:3])}..."
        else:
            countries_str = ', '.join(countries_unique)

        # Valor formateado con unidades
        score = self._format_score(item)
        if score == "Breakout":
            value_str = "🚀 Breakout"
        elif score.startswith('+'):
            value_str = score
        else:
            value_str = f"Score: {score}"

        # Velocidad
        velocity_str = ""
        if item.velocity == 'acelerando':
            velocity_str = " ↑"
        elif item.velocity == 'decayendo':
            velocity_str = " ↓"

        line = f"• {novelty_badge}{emoji} *{item.name}* - {type_label} ({countries_str}) [{value_str}]{velocity_str}"

        # Añadir versiones si existen
        if include_versions and item.versions:
            versions_sorted = sorted(item.versions, reverse=True)[:3]
            line += f"\n    ↳ _Versiones trending: {', '.join(versions_sorted)}_"

        return line

    def format_slack(self, report: ContentReport) -> str:
        """
        Formatea el informe para Slack.

        Args:
            report: ContentReport generado

        Returns:
            String formateado para Slack
        """
        lines = []

        # Header
        header = f"📊 *INFORME TRENDS - {report.timestamp}*"
        if report.group:
            header += f"\nGrupo: `{report.group}` ({', '.join(report.regions)})"
        else:
            header += f"\nRegiones: {', '.join(report.regions)}"
        lines.append(header)
        lines.append("")

        # Resumen ejecutivo
        if report.executive_summary:
            lines.append("📋 *RESUMEN EJECUTIVO*")
            for bullet in report.executive_summary:
                lines.append(f"  • {bullet}")
            lines.append("")

        # Apps nuevas (nunca vistas)
        if report.new_apps:
            lines.append(f"✨ *APPS NUEVAS ({len(report.new_apps)})*")
            lines.append("━" * 30)
            for item in report.new_apps[:10]:
                lines.append(self._format_app_line(item, show_novelty=True))
            if len(report.new_apps) > 10:
                lines.append(f"  _...y {len(report.new_apps) - 10} más_")
            lines.append("")

        # Tendencias globales (3+ países)
        if report.global_trends:
            lines.append(f"🌍 *TENDENCIAS GLOBALES ({len(report.global_trends)})*")
            lines.append("━" * 30)
            for item in report.global_trends[:10]:
                countries_str = ', '.join(list(set(item.countries)))
                lines.append(f"• *{item.name}* - {item.spread_score} países ({countries_str})")
            lines.append("")

        # Apps acelerando
        if report.accelerating:
            lines.append(f"⚡ *ACELERANDO ({len(report.accelerating)})*")
            lines.append("━" * 30)
            for item in report.accelerating[:5]:
                sign = '+' if item.velocity_change > 0 else ''
                lines.append(f"• *{item.name}* - {sign}{item.velocity_change}% vs ayer")
            lines.append("")

        # Apps potenciales (normales)
        if report.potential_apps:
            lines.append(f"🎯 *APPS DETECTADAS ({len(report.potential_apps)})*")
            lines.append("━" * 30)

            for item in report.potential_apps[:15]:
                lines.append(self._format_app_line(item))

            if len(report.potential_apps) > 15:
                lines.append(f"  _...y {len(report.potential_apps) - 15} más_")

            lines.append("")

        # Apps en watchlist (requieren revisión)
        if report.watchlist_apps:
            lines.append(f"⚠️ *REQUIEREN REVISIÓN ({len(report.watchlist_apps)})*")
            lines.append("━" * 30)

            for item in report.watchlist_apps[:10]:
                line = self._format_app_line(item, include_versions=False)
                line += f"\n    ⚠️ _{item.review_reason}_"
                lines.append(line)

            if len(report.watchlist_apps) > 10:
                lines.append(f"  _...y {len(report.watchlist_apps) - 10} más_")

            lines.append("")

        # Casino / Betting (sección propia, al final)
        if report.casino_apps:
            lines.append(f"🎰 *CASINO / BETTING ({len(report.casino_apps)})*")
            lines.append("━" * 30)

            for item in report.casino_apps[:10]:
                lines.append(self._format_app_line(item))

            if len(report.casino_apps) > 10:
                lines.append(f"  _...y {len(report.casino_apps) - 10} más_")

            lines.append("")

        # Si no hay nada
        if not report.potential_apps and not report.watchlist_apps and not report.casino_apps:
            lines.append("ℹ️ No se detectaron apps relevantes en esta ejecución")
            lines.append("")

        # Resumen de filtrados
        lines.append("─" * 30)
        lines.append("*FILTRADOS*")

        if report.generic_terms:
            generic_names = [item.name for item in report.generic_terms[:8]]
            lines.append(f"⏭️ Genéricos ({len(report.generic_terms)}): _{', '.join(generic_names)}_")
            if len(report.generic_terms) > 8:
                lines.append(f"    _...y {len(report.generic_terms) - 8} más_")

        if report.no_app_terms:
            no_app_names = [item.name for item in report.no_app_terms[:8]]
            lines.append(f"🚫 No-app filtrados ({len(report.no_app_terms)}): _{', '.join(no_app_names)}_")
            if len(report.no_app_terms) > 8:
                lines.append(f"    _...y {len(report.no_app_terms) - 8} más_")

        if report.technical_terms:
            tech_names = [item.name for item in report.technical_terms[:5]]
            lines.append(f"🔧 Técnicos ({len(report.technical_terms)}): _{', '.join(tech_names)}_")
            if len(report.technical_terms) > 5:
                lines.append(f"    _...y {len(report.technical_terms) - 5} más_")

        # Estadísticas
        lines.append("")
        lines.append(f"📊 Total: {report.total_items_processed} items → {report.total_unique_terms} únicos")

        return '\n'.join(lines)

    def format_plain(self, report: ContentReport) -> str:
        """
        Formatea el informe en texto plano (para logs/consola).

        Args:
            report: ContentReport generado

        Returns:
            String formateado en texto plano
        """
        lines = []

        # Header
        lines.append("=" * 60)
        lines.append(f"INFORME TRENDS - {report.timestamp}")
        if report.group:
            lines.append(f"Grupo: {report.group} ({', '.join(report.regions)})")
        else:
            lines.append(f"Regiones: {', '.join(report.regions)}")
        lines.append("=" * 60)
        lines.append("")

        # Apps potenciales
        if report.potential_apps:
            lines.append(f"APPS/TÉRMINOS DETECTADOS ({len(report.potential_apps)})")
            lines.append("-" * 40)

            for item in report.potential_apps:
                rising_mark = "[RISING]" if item.is_rising else "[TOP]"
                if item.rss_trending:
                    rising_mark += " 📰"
                countries_str = ', '.join(item.countries)
                lines.append(f"  {rising_mark} {item.name}")
                lines.append(f"      Países: {countries_str}")
                lines.append(f"      Valor: {self._format_score(item)}")
                if item.links:
                    lines.append(f"      Link: {item.links[0]}")
                lines.append("")
        else:
            lines.append("No se detectaron apps/términos relevantes")
            lines.append("")

        # Casino / Betting (sección propia, al final)
        if report.casino_apps:
            lines.append(f"🎰 CASINO / BETTING ({len(report.casino_apps)})")
            lines.append("-" * 40)
            for item in report.casino_apps:
                rising_mark = "[RISING]" if item.is_rising else "[TOP]"
                if item.rss_trending:
                    rising_mark += " 📰"
                countries_str = ', '.join(item.countries)
                lines.append(f"  {rising_mark} {item.name}")
                lines.append(f"      Países: {countries_str}")
                lines.append(f"      Valor: {self._format_score(item)}")
                if item.links:
                    lines.append(f"      Link: {item.links[0]}")
                lines.append("")

        # Términos genéricos
        if report.generic_terms:
            lines.append(f"TÉRMINOS GENÉRICOS IGNORADOS ({len(report.generic_terms)})")
            lines.append("-" * 40)
            generic_names = [item.name for item in report.generic_terms[:10]]
            lines.append(f"  {', '.join(generic_names)}")
            if len(report.generic_terms) > 10:
                lines.append(f"  ...y {len(report.generic_terms) - 10} más")
            lines.append("")

        # Términos sin señal de app (detector estricto)
        if report.no_app_terms:
            lines.append(f"NO-APP FILTRADOS ({len(report.no_app_terms)})")
            lines.append("-" * 40)
            no_app_names = [item.name for item in report.no_app_terms[:10]]
            lines.append(f"  {', '.join(no_app_names)}")
            if len(report.no_app_terms) > 10:
                lines.append(f"  ...y {len(report.no_app_terms) - 10} más")
            lines.append("")

        # Estadísticas
        lines.append("-" * 40)
        lines.append(f"Total procesado: {report.total_items_processed} items")
        lines.append(f"Términos únicos: {report.total_unique_terms}")
        lines.append("=" * 60)

        return '\n'.join(lines)

    def format_sheet_rich(self, report: ContentReport) -> Tuple[List[str], List[List[str]]]:
        """
        Genera formato rico para exportar a Google Sheets (con secciones).

        Args:
            report: ContentReport generado

        Returns:
            Tuple de (headers, rows) con formato legible
        """
        rows = []

        # Header del informe
        rows.append([f"INFORME TRENDS - {report.timestamp}", "", "", "", "", ""])
        if report.group:
            rows.append([f"Grupo: {report.group} - Regiones: {', '.join(report.regions)}", "", "", "", "", ""])
        else:
            rows.append([f"Regiones: {', '.join(report.regions)}", "", "", "", "", ""])
        rows.append(["", "", "", "", "", ""])  # Línea vacía

        # Resumen ejecutivo
        if report.executive_summary:
            rows.append(["📋 RESUMEN EJECUTIVO", "", "", "", "", ""])
            for bullet in report.executive_summary:
                rows.append([f"  • {bullet}", "", "", "", "", ""])
            rows.append(["", "", "", "", "", ""])

        # Apps nuevas
        if report.new_apps:
            rows.append([f"✨ APPS NUEVAS ({len(report.new_apps)})", "", "", "", "", ""])
            rows.append(["App", "Tipo", "Países", "Score", "Novedad", "Link"])
            for item in report.new_apps:
                tipo = self._sheet_tipo(item)
                countries = ', '.join(list(set(item.countries))[:5])
                link = item.links[0] if item.links else ""
                rows.append([item.name, tipo, countries, self._format_score(item), "🆕 Nueva", link])
            rows.append(["", "", "", "", "", ""])

        # Tendencias globales
        if report.global_trends:
            rows.append([f"🌍 TENDENCIAS GLOBALES ({len(report.global_trends)})", "", "", "", "", ""])
            rows.append(["App", "Países", "Spread", "Score", "Velocidad", "Link"])
            for item in report.global_trends:
                countries = ', '.join(list(set(item.countries)))
                vel = item.velocity if item.velocity else ""
                link = item.links[0] if item.links else ""
                rows.append([item.name, countries, str(item.spread_score), self._format_score(item), vel, link])
            rows.append(["", "", "", "", "", ""])

        # Sección de apps detectadas
        if report.potential_apps:
            rows.append([f"🎯 APPS DETECTADAS ({len(report.potential_apps)})", "", "", "", "", ""])
            rows.append(["App", "Tipo", "Países", "Score", "Versiones", "Link"])

            for item in report.potential_apps:
                tipo = self._sheet_tipo(item)
                countries = ', '.join(list(set(item.countries))[:5])
                if len(set(item.countries)) > 5:
                    countries += "..."
                versions = ', '.join(item.versions[:3]) if item.versions else ""
                link = item.links[0] if item.links else ""

                rows.append([item.name, tipo, countries, self._format_score(item), versions, link])

            rows.append(["", "", "", "", "", ""])  # Línea vacía

        # Sección de watchlist (apps que requieren revisión)
        if report.watchlist_apps:
            rows.append([f"⚠️ REQUIEREN REVISIÓN ({len(report.watchlist_apps)})", "", "", "", "", ""])
            rows.append(["App", "Tipo", "Países", "Score", "Razón", "Link"])

            for item in report.watchlist_apps:
                tipo = self._sheet_tipo(item)
                countries = ', '.join(list(set(item.countries))[:3])
                link = item.links[0] if item.links else ""

                rows.append([item.name, tipo, countries, self._format_score(item), item.review_reason, link])

            rows.append(["", "", "", "", "", ""])

        # Sección de casino / betting (al final, mismas columnas que apps)
        if report.casino_apps:
            rows.append([f"🎰 CASINO / BETTING ({len(report.casino_apps)})", "", "", "", "", ""])
            rows.append(["App", "Tipo", "Países", "Score", "Versiones", "Link"])

            for item in report.casino_apps:
                tipo = self._sheet_tipo(item)
                countries = ', '.join(list(set(item.countries))[:5])
                if len(set(item.countries)) > 5:
                    countries += "..."
                versions = ', '.join(item.versions[:3]) if item.versions else ""
                link = item.links[0] if item.links else ""

                rows.append([item.name, tipo, countries, self._format_score(item), versions, link])

            rows.append(["", "", "", "", "", ""])

        # Resumen
        rows.append(["─" * 30, "", "", "", "", ""])
        rows.append([f"Total procesado: {report.total_items_processed} items → {report.total_unique_terms} únicos", "", "", "", "", ""])

        if report.generic_terms:
            generic_names = [item.name for item in report.generic_terms[:8]]
            rows.append([f"Genéricos filtrados ({len(report.generic_terms)}): {', '.join(generic_names)}", "", "", "", "", ""])

        if report.no_app_terms:
            no_app_names = [item.name for item in report.no_app_terms[:8]]
            rows.append([f"No-app filtrados ({len(report.no_app_terms)}): {', '.join(no_app_names)}", "", "", "", "", ""])

        # No retornamos headers separados porque están incluidos en las filas
        return [], rows

    def format_sheet_rows(self, report: ContentReport) -> List[List[str]]:
        """
        Genera filas para exportar a Google Sheets (formato rico).

        Args:
            report: ContentReport generado

        Returns:
            Lista de filas para el Sheet
        """
        _, rows = self.format_sheet_rich(report)
        return rows


# Headers para la pestaña de informes en Google Sheets (legacy, no se usan con formato rico)
REPORT_SHEET_HEADERS = []


# Para pruebas directas
if __name__ == "__main__":
    # Crear datos de prueba
    test_data = [
        TrendData(
            timestamp="2026-01-29 14:00:00",
            term="apk",
            country_code="IN",
            country_name="India",
            data_type="queries_rising",
            title="capcut pro apk",
            value="+500%",
            link="https://trends.google.com/..."
        ),
        TrendData(
            timestamp="2026-01-29 14:00:00",
            term="apk",
            country_code="BR",
            country_name="Brazil",
            data_type="queries_rising",
            title="CapCut Pro APK",
            value="Breakout",
            link="https://trends.google.com/..."
        ),
        TrendData(
            timestamp="2026-01-29 14:00:00",
            term="apk",
            country_code="US",
            country_name="United States",
            data_type="queries_top",
            title="whatsapp",
            value="100",
            link="https://trends.google.com/..."
        ),
        TrendData(
            timestamp="2026-01-29 14:00:00",
            term="apk",
            country_code="IN",
            country_name="India",
            data_type="queries_top",
            title="download apk",
            value="85",
            link="https://trends.google.com/..."
        ),
        TrendData(
            timestamp="2026-01-29 14:00:00",
            term="apk",
            country_code="WW",
            country_name="Worldwide",
            data_type="queries_top",
            title="mod apk",
            value="72",
            link="https://trends.google.com/..."
        ),
    ]

    generator = ReportGenerator()
    report = generator.generate(test_data, group="group_1")

    print("\n=== FORMATO SLACK ===\n")
    print(generator.format_slack(report))

    print("\n=== FORMATO PLAIN ===\n")
    print(generator.format_plain(report))
