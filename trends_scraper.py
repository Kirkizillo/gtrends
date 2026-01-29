"""
Scraper de Google Trends usando PyTrends.
"""
import logging
import random
import unicodedata
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from pytrends.request import TrendReq

import config
from rate_limiter import RateLimiter, retry_with_backoff

logger = logging.getLogger(__name__)

# Lista de User-Agents para rotación
USER_AGENTS = [
    # Chrome on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',

    # Firefox on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',

    # Chrome on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',

    # Safari on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',

    # Firefox on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 13.6; rv:120.0) Gecko/20100101 Firefox/120.0',

    # Chrome on Linux
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',

    # Firefox on Linux
    'Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0',

    # Edge on Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0',

    # Edge on macOS
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
]


@dataclass
class TrendData:
    """Estructura para almacenar datos de tendencias."""
    timestamp: str
    term: str
    country_code: str
    country_name: str
    data_type: str  # 'queries_top', 'queries_rising', 'topics_top', 'topics_rising'
    title: str
    value: str
    link: str = ""


class ErrorType:
    """Tipos de error para clasificación."""
    NONE = "none"
    RATE_LIMIT = "rate_limit"      # Error 429
    NO_DATA = "no_data"            # Respuesta vacía o sin datos
    AUTH_ERROR = "auth_error"      # Error de autenticación
    NETWORK_ERROR = "network"      # Error de red/conexión
    UNKNOWN = "unknown"            # Otros errores


@dataclass
class ScrapingResult:
    """Resultado del scraping con datos y metadatos."""
    success: bool
    data: List[TrendData] = field(default_factory=list)
    error_message: str = ""
    error_type: str = ErrorType.NONE  # Clasificación del error


class TrendsScraper:
    """
    Scraper para extraer datos de Google Trends.
    """

    def __init__(self):
        self.rate_limiter = RateLimiter(config.RATE_LIMIT_SECONDS)
        self.pytrends = None
        self.proxies = config.PROXIES if hasattr(config, 'PROXIES') else []
        self.current_proxy_index = 0
        self._init_pytrends()

    def _get_next_proxy(self):
        """Obtiene el siguiente proxy de la lista rotativa."""
        if not self.proxies:
            return None
        proxy = self.proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        return proxy

    def _init_pytrends(self):
        """Inicializa la conexión con Google Trends."""
        try:
            # Seleccionar un User-Agent aleatorio
            user_agent = random.choice(USER_AGENTS)
            logger.info(f"Usando User-Agent: {user_agent[:60]}...")

            # Configurar requests_args con headers de navegador
            requests_args = {
                'headers': {
                    'User-Agent': user_agent,
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            }

            # Agregar proxy si está disponible
            proxy = self._get_next_proxy()
            if proxy:
                requests_args['proxies'] = {
                    'http': proxy,
                    'https': proxy
                }
                logger.info(f"Usando proxy: {proxy[:30]}...")

            self.pytrends = TrendReq(
                hl='en-US',
                tz=360,
                timeout=(10, 25),
                requests_args=requests_args
            )
            logger.info("PyTrends inicializado correctamente")
        except Exception as e:
            logger.error(f"Error inicializando PyTrends: {e}")
            raise

    @retry_with_backoff(max_retries=config.MAX_RETRIES, base_delay=config.RETRY_DELAY_SECONDS)
    def _build_payload(self, term: str, geo: str):
        """Construye el payload para una búsqueda."""
        self.rate_limiter.wait()
        # WW (Worldwide) usa geo vacío en PyTrends
        pytrends_geo = "" if geo == "WW" else geo
        logger.info(f"Construyendo payload para '{term}' en {geo or 'Worldwide'}")
        self.pytrends.build_payload(
            kw_list=[term],
            timeframe=config.TIMEFRAME,
            geo=pytrends_geo
        )

    def _get_timestamp(self) -> str:
        """Retorna timestamp actual en formato ISO (UTC)."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def _fetch_with_retry(self, fetch_func, term: str = None, geo: str = None, max_retries: int = None):
        """
        Ejecuta una función de fetch con reintentos para errores 429.
        Usa backoff exponencial con límite máximo configurable.

        Args:
            fetch_func: Función a ejecutar
            term: Término de búsqueda (para reconstruir payload tras reinicio)
            geo: Código de país (para reconstruir payload tras reinicio)
            max_retries: Número máximo de reintentos (default: config.MAX_RETRIES)

        Returns:
            Resultado de la función
        """
        import time

        if max_retries is None:
            max_retries = config.MAX_RETRIES

        # Obtener MAX_BACKOFF de config (default 180s si no existe)
        max_backoff = getattr(config, 'MAX_BACKOFF_SECONDS', 180)

        for attempt in range(max_retries):
            try:
                return fetch_func()
            except Exception as e:
                if '429' in str(e):
                    if attempt < max_retries - 1:
                        # Backoff exponencial con límite máximo
                        # Base: 60s, luego 120s, pero nunca más de MAX_BACKOFF
                        base_wait = 60 * (2 ** attempt)
                        jitter = random.randint(20, 60)
                        wait_time = min(base_wait + jitter, max_backoff)

                        logger.warning(
                            f"Rate limit 429. Intento {attempt + 1}/{max_retries}. "
                            f"Esperando {wait_time}s (max: {max_backoff}s)..."
                        )
                        time.sleep(wait_time)
                        # Reinicializar pytrends con nueva sesión
                        self._init_pytrends()
                        # Reconstruir el payload después de reiniciar
                        if term is not None:
                            pytrends_geo = "" if geo == "WW" else geo
                            self.pytrends.build_payload(
                                kw_list=[term],
                                timeframe=config.TIMEFRAME,
                                geo=pytrends_geo
                            )
                    else:
                        raise
                else:
                    raise

    def scrape_related_queries(
        self,
        term: str,
        geo: str,
        country_name: str
    ) -> ScrapingResult:
        """
        Extrae Related Queries (Top y Rising) para un término.

        Args:
            term: Término de búsqueda
            geo: Código de país (ej: 'IN')
            country_name: Nombre del país

        Returns:
            ScrapingResult con los datos extraídos
        """
        result = ScrapingResult(success=False)
        timestamp = self._get_timestamp()

        try:
            self._build_payload(term, geo)
            queries = self._fetch_with_retry(lambda: self.pytrends.related_queries(), term=term, geo=geo)

            if not queries or term not in queries:
                logger.warning(f"No se encontraron queries para '{term}'")
                result.success = True
                return result

            term_data = queries[term]

            # Procesar Top Queries
            if term_data.get('top') is not None and not term_data['top'].empty:
                df_top = term_data['top']
                for _, row in df_top.iterrows():
                    query_text = str(row.get('query', ''))
                    result.data.append(TrendData(
                        timestamp=timestamp,
                        term=term,
                        country_code=geo,
                        country_name=country_name,
                        data_type='queries_top',
                        title=query_text,
                        value=str(row.get('value', '')),
                        link=f"https://trends.google.com/trends/explore?q={quote_plus(query_text)}&geo={geo}&date={quote_plus(config.TIMEFRAME)}"
                    ))
                logger.info(f"Extraídos {len(df_top)} Top Queries para '{term}'")

            # Procesar Rising Queries
            if term_data.get('rising') is not None and not term_data['rising'].empty:
                df_rising = term_data['rising']
                for _, row in df_rising.iterrows():
                    query_text = str(row.get('query', ''))
                    result.data.append(TrendData(
                        timestamp=timestamp,
                        term=term,
                        country_code=geo,
                        country_name=country_name,
                        data_type='queries_rising',
                        title=query_text,
                        value=str(row.get('value', '')),
                        link=f"https://trends.google.com/trends/explore?q={quote_plus(query_text)}&geo={geo}&date={quote_plus(config.TIMEFRAME)}"
                    ))
                logger.info(f"Extraídos {len(df_rising)} Rising Queries para '{term}'")

            result.success = True

        except Exception as e:
            result.error_message = str(e)
            result.error_type = self._classify_error(e)
            logger.error(f"Error extrayendo queries para '{term}': {e}")

        return result

    def _classify_error(self, error: Exception) -> str:
        """
        Clasifica un error según su tipo.

        Args:
            error: Excepción capturada

        Returns:
            Tipo de error (ErrorType)
        """
        error_str = str(error).lower()

        if '429' in error_str or 'too many requests' in error_str:
            return ErrorType.RATE_LIMIT
        elif 'empty' in error_str or 'no data' in error_str or 'none' in error_str:
            return ErrorType.NO_DATA
        elif '401' in error_str or '403' in error_str or 'unauthorized' in error_str or 'forbidden' in error_str:
            return ErrorType.AUTH_ERROR
        elif 'connection' in error_str or 'timeout' in error_str or 'network' in error_str:
            return ErrorType.NETWORK_ERROR
        else:
            return ErrorType.UNKNOWN

    def scrape_related_topics(
        self,
        term: str,
        geo: str,
        country_name: str
    ) -> ScrapingResult:
        """
        Extrae Related Topics (Top y Rising) para un término.

        NOTA: Esta función se usa en Fase 2+

        Args:
            term: Término de búsqueda
            geo: Código de país (ej: 'IN')
            country_name: Nombre del país

        Returns:
            ScrapingResult con los datos extraídos
        """
        result = ScrapingResult(success=False)
        timestamp = self._get_timestamp()

        try:
            self._build_payload(term, geo)

            # PyTrends related_topics() es inestable, capturar errores específicos
            try:
                topics = self._fetch_with_retry(lambda: self.pytrends.related_topics(), term=term, geo=geo)
            except (IndexError, KeyError) as e:
                # Bug conocido de PyTrends con related_topics
                logger.warning(f"PyTrends error en related_topics para '{term}': {e} (ignorando)")
                result.success = True
                return result

            if not topics or term not in topics:
                logger.warning(f"No se encontraron topics para '{term}'")
                result.success = True
                return result

            term_data = topics[term]

            # Procesar Top Topics
            try:
                if term_data.get('top') is not None and hasattr(term_data['top'], 'empty') and not term_data['top'].empty:
                    df_top = term_data['top']
                    for _, row in df_top.iterrows():
                        topic_title = str(row.get('topic_title', ''))
                        topic_mid = str(row.get('topic_mid', ''))
                        result.data.append(TrendData(
                            timestamp=timestamp,
                            term=term,
                            country_code=geo,
                            country_name=country_name,
                            data_type='topics_top',
                            title=topic_title,
                            value=str(row.get('value', '')),
                            link=f"https://trends.google.com/trends/explore?q={quote_plus(topic_mid)}&geo={geo}&date={quote_plus(config.TIMEFRAME)}" if topic_mid else ""
                        ))
                    logger.info(f"Extraídos {len(df_top)} Top Topics para '{term}'")
            except (IndexError, KeyError, AttributeError) as e:
                logger.warning(f"Error procesando Top Topics para '{term}': {e}")

            # Procesar Rising Topics
            try:
                if term_data.get('rising') is not None and hasattr(term_data['rising'], 'empty') and not term_data['rising'].empty:
                    df_rising = term_data['rising']
                    for _, row in df_rising.iterrows():
                        topic_title = str(row.get('topic_title', ''))
                        topic_mid = str(row.get('topic_mid', ''))
                        result.data.append(TrendData(
                            timestamp=timestamp,
                            term=term,
                            country_code=geo,
                            country_name=country_name,
                            data_type='topics_rising',
                            title=topic_title,
                            value=str(row.get('value', '')),
                            link=f"https://trends.google.com/trends/explore?q={quote_plus(topic_mid)}&geo={geo}&date={quote_plus(config.TIMEFRAME)}" if topic_mid else ""
                        ))
                    logger.info(f"Extraídos {len(df_rising)} Rising Topics para '{term}'")
            except (IndexError, KeyError, AttributeError) as e:
                logger.warning(f"Error procesando Rising Topics para '{term}': {e}")

            result.success = True

        except Exception as e:
            result.error_message = str(e)
            result.error_type = self._classify_error(e)
            logger.error(f"Error extrayendo topics para '{term}': {e}")

        return result

    def scrape_interest_over_time(
        self,
        term: str,
        geo: str,
        country_name: str
    ) -> ScrapingResult:
        """
        Extrae Interest Over Time para un término.

        Args:
            term: Término de búsqueda
            geo: Código de país (ej: 'IN')
            country_name: Nombre del país

        Returns:
            ScrapingResult con los datos extraídos
        """
        result = ScrapingResult(success=False)
        timestamp = self._get_timestamp()

        try:
            self._build_payload(term, geo)
            interest_df = self._fetch_with_retry(lambda: self.pytrends.interest_over_time(), term=term, geo=geo)

            if interest_df is None or interest_df.empty:
                logger.warning(f"No se encontró interest over time para '{term}'")
                result.success = True
                return result

            # Procesar datos de interés
            if term in interest_df.columns:
                for idx, row in interest_df.iterrows():
                    time_point = idx.strftime("%Y-%m-%d %H:%M:%S") if hasattr(idx, 'strftime') else str(idx)
                    result.data.append(TrendData(
                        timestamp=timestamp,
                        term=term,
                        country_code=geo,
                        country_name=country_name,
                        data_type='interest_over_time',
                        title=time_point,  # Usamos title para el punto temporal
                        value=str(row[term]),
                        link=f"https://trends.google.com/trends/explore?q={quote_plus(term)}&geo={geo}&date={quote_plus(config.TIMEFRAME)}"
                    ))
                logger.info(f"Extraídos {len(interest_df)} puntos de Interest Over Time para '{term}'")

            result.success = True

        except Exception as e:
            result.error_message = str(e)
            result.error_type = self._classify_error(e)
            logger.error(f"Error extrayendo interest over time para '{term}': {e}")

        return result

    def scrape_all(
        self,
        terms: List[str] = None,
        regions: Dict[str, str] = None,
        include_topics: bool = False,
        include_interest: bool = False
    ) -> List[TrendData]:
        """
        Ejecuta scraping completo para todos los términos y regiones.

        Args:
            terms: Lista de términos (default: config.CURRENT_TERMS)
            regions: Dict de regiones {código: nombre} (default: config.CURRENT_REGIONS)
            include_topics: Si incluir Related Topics
            include_interest: Si incluir Interest Over Time

        Returns:
            Lista de TrendData con todos los resultados
        """
        if terms is None:
            terms = config.CURRENT_TERMS
        if regions is None:
            regions = config.CURRENT_REGIONS

        all_data = []
        total_terms = len(terms)
        total_regions = len(regions)

        logger.info(f"Iniciando scraping: {total_terms} términos, {total_regions} regiones")

        for term_idx, term in enumerate(terms, 1):
            for geo, country_name in regions.items():
                logger.info(
                    f"[{term_idx}/{total_terms}] Procesando '{term}' en {country_name} ({geo})"
                )

                # Extraer Related Queries
                queries_result = self.scrape_related_queries(term, geo, country_name)
                if queries_result.success:
                    all_data.extend(queries_result.data)
                else:
                    logger.error(f"Falló extracción de queries: {queries_result.error_message}")

                # Extraer Related Topics (solo si está habilitado)
                if include_topics:
                    topics_result = self.scrape_related_topics(term, geo, country_name)
                    if topics_result.success:
                        all_data.extend(topics_result.data)
                    else:
                        logger.error(f"Falló extracción de topics: {topics_result.error_message}")

                # Extraer Interest Over Time (solo si está habilitado)
                if include_interest:
                    interest_result = self.scrape_interest_over_time(term, geo, country_name)
                    if interest_result.success:
                        all_data.extend(interest_result.data)
                    else:
                        logger.error(f"Falló extracción de interest: {interest_result.error_message}")

        # Deduplicar datos antes de retornar
        deduplicated_data = self._deduplicate(all_data)

        logger.info(f"Scraping completado. Total registros: {len(deduplicated_data)} (de {len(all_data)} antes de deduplicar)")
        return deduplicated_data

    def _normalize_for_dedup(self, text: str) -> str:
        """
        Normaliza texto para comparación en deduplicación.
        - Lowercase
        - Strip espacios
        - Normalización Unicode (NFKC: compatibilidad + composición)
        - Elimina acentos/diacríticos

        Args:
            text: Texto a normalizar

        Returns:
            Texto normalizado
        """
        if not text:
            return ""
        # Normalizar Unicode (NFKD descompone caracteres)
        normalized = unicodedata.normalize('NFKD', text)
        # Eliminar marcas diacríticas (acentos)
        without_accents = ''.join(
            c for c in normalized if not unicodedata.combining(c)
        )
        # Lowercase y strip
        return without_accents.lower().strip()

    def _deduplicate(self, data: List[TrendData]) -> List[TrendData]:
        """
        Elimina duplicados basándose en term + country + data_type + title.
        Usa normalización case-insensitive y Unicode-aware.

        Args:
            data: Lista de TrendData

        Returns:
            Lista sin duplicados
        """
        seen = set()
        unique_data = []

        for item in data:
            # Crear clave única normalizada
            normalized_title = self._normalize_for_dedup(item.title)
            key = (
                item.term.lower().strip(),
                item.country_code,
                item.data_type,
                normalized_title
            )

            if key not in seen:
                seen.add(key)
                unique_data.append(item)
            else:
                logger.debug(f"Duplicado eliminado: {item.title} ({item.data_type})")

        if len(data) != len(unique_data):
            logger.info(f"Eliminados {len(data) - len(unique_data)} duplicados")

        return unique_data


# Para pruebas directas
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format=config.LOG_FORMAT
    )

    scraper = TrendsScraper()

    # MVP: Solo queries, sin topics
    data = scraper.scrape_all(include_topics=False)

    print(f"\n{'='*60}")
    print(f"Resultados: {len(data)} registros")
    print(f"{'='*60}")

    for item in data[:10]:  # Mostrar primeros 10
        print(f"[{item.data_type}] {item.title}: {item.value}")
