"""
Utilidades visuales compartidas para los distintos formatos de informe
(Slack, Markdown, HTML): banderas por país, flechas de tendencia y
sparklines con caracteres Unicode. Sin dependencias externas.
"""

# Emoji de bandera por código de país (coincide con config.REGIONS_FULL).
# WW (Worldwide) no es un país real → globo terráqueo.
COUNTRY_FLAGS = {
    "WW": "🌍",
    "IN": "🇮🇳",
    "US": "🇺🇸",
    "BR": "🇧🇷",
    "ID": "🇮🇩",
    "MX": "🇲🇽",
    "GB": "🇬🇧",
    "PH": "🇵🇭",
    "AU": "🇦🇺",
    "VN": "🇻🇳",
    "DE": "🇩🇪",
    "RU": "🇷🇺",
    "TH": "🇹🇭",
    "FR": "🇫🇷",
    "IT": "🇮🇹",
    "CO": "🇨🇴",
    "JP": "🇯🇵",
    "TR": "🇹🇷",
    "RO": "🇷🇴",
    "NG": "🇳🇬",
}

# Bloques Unicode de menor a mayor altura, para sparklines de texto plano
_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


def flag(country_code: str) -> str:
    """Emoji de bandera para un código de país. Cadena vacía si no se conoce."""
    return COUNTRY_FLAGS.get(country_code, "")


def flag_or_code(country_code: str) -> str:
    """Bandera + código si existe; solo el código si no hay bandera mapeada."""
    f = flag(country_code)
    return f"{f} {country_code}" if f else country_code


def trend_arrow(change_pct: float) -> str:
    """
    Flecha de tendencia según el signo del cambio porcentual.
    Umbral de +-1% para considerar "estable" y evitar ruido en cifras pequeñas.
    """
    if change_pct > 1:
        return "▲"
    if change_pct < -1:
        return "▼"
    return "▬"


def sparkline(values: list) -> str:
    """
    Sparkline de texto a partir de una lista de números (ej. volumen por día).
    Escala cada valor al rango de 8 bloques Unicode según min/max de la serie.

    Lista vacía o de un solo valor constante → bloques al nivel mínimo.
    """
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if hi == lo:
        return _SPARK_BLOCKS[0] * len(values)

    span = hi - lo
    chars = []
    for v in values:
        idx = round((v - lo) / span * (len(_SPARK_BLOCKS) - 1))
        chars.append(_SPARK_BLOCKS[idx])
    return "".join(chars)
