"""
Señal complementaria gratuita: feed RSS oficial de Google Trends "Trending Now".

Feed: https://trends.google.com/trending/rss?geo=XX  (geo = código ISO de país)

Notas:
- Es un feed oficial y público: no necesita rate limiting agresivo,
  pero se consulta de forma secuencial (sin fetches en paralelo) por cortesía.
- No existe variante worldwide: omitir el parámetro geo devuelve US por
  defecto, así que WW se salta (ver GEOS_NO_SOPORTADOS).
- Nunca lanza excepciones: siempre devuelve un ScrapingResult.
"""
import logging
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from trends_scraper import TrendData, ScrapingResult, ErrorType

logger = logging.getLogger(__name__)

# URL base del feed RSS de Trending Now
RSS_URL = "https://trends.google.com/trending/rss"

# Namespace de los campos ht: (approx_traffic, etc.)
HT_NS = "https://trends.google.com/trending/rss"

# Timeout por request (segundos) y reintentos (1 intento + 1 reintento)
TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 5

# El feed no soporta worldwide: sin geo devuelve US por defecto
GEOS_NO_SOPORTADOS = {"WW"}


def is_geo_supported(country_code: str) -> bool:
    """Indica si el feed RSS soporta el código de país dado."""
    return country_code not in GEOS_NO_SOPORTADOS


def _classify_error(exception: Exception) -> str:
    """Clasifica una excepción de requests en un ErrorType."""
    if isinstance(exception, requests.exceptions.Timeout):
        return ErrorType.NETWORK_ERROR
    if isinstance(exception, requests.exceptions.ConnectionError):
        return ErrorType.NETWORK_ERROR
    if isinstance(exception, requests.exceptions.HTTPError):
        response = getattr(exception, 'response', None)
        status = response.status_code if response is not None else None
        if status == 429:
            return ErrorType.RATE_LIMIT
        if status in (401, 403):
            return ErrorType.AUTH_ERROR
        return ErrorType.NETWORK_ERROR
    return ErrorType.UNKNOWN


def _parse_rss(xml_text: str, country_code: str, country_name: str) -> list:
    """
    Parsea el XML del feed RSS y devuelve una lista de TrendData.

    Campos por item: title, ht:approx_traffic, pubDate, link.
    """
    root = ET.fromstring(xml_text)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    data = []
    for item in root.iter('item'):
        title_el = item.find('title')
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        if not title:
            continue

        traffic_el = item.find(f'{{{HT_NS}}}approx_traffic')
        traffic = traffic_el.text.strip() if traffic_el is not None and traffic_el.text else ""

        link_el = item.find('link')
        link = link_el.text.strip() if link_el is not None and link_el.text else ""
        # El feed real pone como <link> la URL del propio feed — no aporta nada
        if not link or "/trending/rss" in link:
            # Fallback: URL de explore de Google Trends
            link = (
                "https://trends.google.com/trends/explore"
                f"?q={urllib.parse.quote(title)}&geo={country_code}"
            )

        data.append(TrendData(
            timestamp=timestamp,
            term="trending",
            country_code=country_code,
            country_name=country_name,
            data_type="trending_rss",
            title=title,
            value=traffic,
            link=link
        ))

    return data


def fetch_trending_rss(country_code: str, country_name: str) -> ScrapingResult:
    """
    Obtiene las tendencias del feed RSS "Trending Now" para un país.

    Args:
        country_code: Código ISO del país (ej: "US", "IN")
        country_name: Nombre del país (ej: "United States")

    Returns:
        ScrapingResult con TrendData (data_type='trending_rss'). Nunca lanza.
    """
    if not is_geo_supported(country_code):
        return ScrapingResult(
            success=False,
            error_message=f"El feed RSS no soporta la región {country_code}",
            error_type=ErrorType.NO_DATA
        )

    url = f"{RSS_URL}?geo={country_code}"
    last_error = None
    last_error_type = ErrorType.UNKNOWN

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            logger.info(f"Fetching RSS trending para {country_name} ({country_code}) [intento {attempt}/{MAX_ATTEMPTS}]")
            response = requests.get(
                url,
                timeout=TIMEOUT_SECONDS,
                headers={"User-Agent": "Mozilla/5.0 (compatible; trends-monitor)"}
            )
            response.raise_for_status()

            data = _parse_rss(response.text, country_code, country_name)

            if not data:
                return ScrapingResult(
                    success=False,
                    error_message=f"Feed RSS sin items para {country_code}",
                    error_type=ErrorType.NO_DATA
                )

            logger.info(f"RSS trending: {len(data)} items para {country_code}")
            return ScrapingResult(success=True, data=data)

        except ET.ParseError as e:
            last_error = f"Error parseando XML del feed RSS: {e}"
            last_error_type = ErrorType.UNKNOWN
            logger.warning(f"  {last_error}")
        except requests.exceptions.RequestException as e:
            last_error = f"Error de red obteniendo feed RSS: {e}"
            last_error_type = _classify_error(e)
            logger.warning(f"  {last_error}")
        except Exception as e:
            last_error = f"Error inesperado en feed RSS: {e}"
            last_error_type = ErrorType.UNKNOWN
            logger.warning(f"  {last_error}")

        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY_SECONDS)

    return ScrapingResult(
        success=False,
        error_message=last_error or "Error desconocido",
        error_type=last_error_type
    )
