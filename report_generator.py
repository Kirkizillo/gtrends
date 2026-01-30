"""
Generador de informes para el equipo de contenidos.

Procesa los datos extraídos de Google Trends y genera informes
accionables clasificando las apps/términos detectados.
"""
import logging
import re
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

    def __post_init__(self):
        # Asegurar que las listas no tengan duplicados
        self.original_titles = list(set(self.original_titles))
        self.countries = list(set(self.countries))
        self.links = list(set(self.links))
        self.versions = list(set(self.versions))


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

    # Estadísticas
    total_items_processed: int = 0
    total_unique_terms: int = 0


class ReportGenerator:
    """
    Genera informes procesados a partir de datos de Google Trends.
    """

    def __init__(self):
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
            most_common = name_counts.most_common(1)[0][0]

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

    def generate(self, data: List[TrendData], group: Optional[str] = None) -> ContentReport:
        """
        Genera un informe a partir de los datos extraídos.

        Args:
            data: Lista de TrendData del scraper
            group: Nombre del grupo ejecutado (opcional)

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

        # Primera pasada: agrupar por nombre BASE de app (sin versión)
        # Esto permite agrupar "terraria 1.4.5" y "terraria 1.4 5" bajo "terraria"
        base_grouped: Dict[str, Dict] = {}

        for item in data:
            # Obtener nombre base sin versión
            base_name = self._get_base_app_name(item.title)
            normalized = self._normalize_term(base_name)

            # Extraer versión si existe
            version = self._extract_version(item.title)

            if normalized not in base_grouped:
                base_grouped[normalized] = {
                    'original_titles': [],
                    'data_types': set(),
                    'countries': [],
                    'values': [],
                    'links': [],
                    'is_rising': False,
                    'versions': set(),
                }

            base_grouped[normalized]['original_titles'].append(item.title)
            base_grouped[normalized]['data_types'].add(item.data_type)
            base_grouped[normalized]['countries'].append(item.country_name)
            base_grouped[normalized]['values'].append(item.value)
            base_grouped[normalized]['links'].append(item.link)

            if version:
                base_grouped[normalized]['versions'].add(version)

            if 'rising' in item.data_type:
                base_grouped[normalized]['is_rising'] = True

        # Clasificar cada término
        potential_apps: List[ReportItem] = []
        watchlist_apps: List[ReportItem] = []
        generic_terms: List[ReportItem] = []
        technical_terms: List[ReportItem] = []

        for normalized, info in base_grouped.items():
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
                review_reason=review_reason
            )

            # Clasificar en la categoría apropiada
            if self._is_technical_term(normalized):
                technical_terms.append(report_item)
            elif self._is_generic_term(normalized):
                generic_terms.append(report_item)
            elif needs_review:
                watchlist_apps.append(report_item)
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

        return ContentReport(
            timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            group=group,
            regions=regions,
            potential_apps=potential_apps,
            watchlist_apps=watchlist_apps,
            generic_terms=generic_terms,
            technical_terms=technical_terms,
            total_items_processed=len(data),
            total_unique_terms=len(base_grouped)
        )

    def _format_app_line(self, item: ReportItem, include_versions: bool = True) -> str:
        """Formatea una línea de app para Slack."""
        # Emoji según tipo
        if item.is_rising:
            emoji = "🔥"
            type_label = "Rising"
        else:
            emoji = "📈"
            type_label = "Top"

        # Países (abreviar si son muchos)
        countries_unique = list(set(item.countries))
        if len(countries_unique) > 3:
            countries_str = f"{', '.join(countries_unique[:3])}..."
        else:
            countries_str = ', '.join(countries_unique)

        # Valor formateado
        if 'breakout' in str(item.max_value).lower():
            value_str = "🚀 Breakout"
        elif str(item.max_value).startswith('+'):
            value_str = item.max_value
        else:
            value_str = f"Score: {item.max_value}"

        line = f"• {emoji} *{item.name}* - {type_label} ({countries_str}) [{value_str}]"

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

        # Si no hay nada
        if not report.potential_apps and not report.watchlist_apps:
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
                countries_str = ', '.join(item.countries)
                lines.append(f"  {rising_mark} {item.name}")
                lines.append(f"      Países: {countries_str}")
                lines.append(f"      Valor: {item.max_value}")
                if item.links:
                    lines.append(f"      Link: {item.links[0]}")
                lines.append("")
        else:
            lines.append("No se detectaron apps/términos relevantes")
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

        # Sección de apps detectadas
        if report.potential_apps:
            rows.append([f"🎯 APPS DETECTADAS ({len(report.potential_apps)})", "", "", "", "", ""])
            rows.append(["App", "Tipo", "Países", "Score", "Versiones", "Link"])

            for item in report.potential_apps:
                tipo = "🔥 Rising" if item.is_rising else "📈 Top"
                countries = ', '.join(list(set(item.countries))[:5])
                if len(set(item.countries)) > 5:
                    countries += "..."
                versions = ', '.join(item.versions[:3]) if item.versions else ""
                link = item.links[0] if item.links else ""

                rows.append([item.name, tipo, countries, item.max_value, versions, link])

            rows.append(["", "", "", "", "", ""])  # Línea vacía

        # Sección de watchlist (apps que requieren revisión)
        if report.watchlist_apps:
            rows.append([f"⚠️ REQUIEREN REVISIÓN ({len(report.watchlist_apps)})", "", "", "", "", ""])
            rows.append(["App", "Tipo", "Países", "Score", "Razón", "Link"])

            for item in report.watchlist_apps:
                tipo = "🔥 Rising" if item.is_rising else "📈 Top"
                countries = ', '.join(list(set(item.countries))[:3])
                link = item.links[0] if item.links else ""

                rows.append([item.name, tipo, countries, item.max_value, item.review_reason, link])

            rows.append(["", "", "", "", "", ""])

        # Resumen
        rows.append(["─" * 30, "", "", "", "", ""])
        rows.append([f"Total procesado: {report.total_items_processed} items → {report.total_unique_terms} únicos", "", "", "", "", ""])

        if report.generic_terms:
            generic_names = [item.name for item in report.generic_terms[:8]]
            rows.append([f"Genéricos filtrados ({len(report.generic_terms)}): {', '.join(generic_names)}", "", "", "", "", ""])

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
