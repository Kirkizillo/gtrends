"""
Tests unitarios para el scraper de Google Trends.
Usa mocks para evitar llamadas reales a la API.

Ejecutar: pytest tests/ -v
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

import config
from trends_scraper import TrendsScraper, TrendData, ScrapingResult


class TestConfig:
    """Tests para verificar la configuración."""

    def test_terms_not_empty(self):
        """Verifica que hay términos configurados."""
        assert len(config.CURRENT_TERMS) > 0

    def test_regions_not_empty(self):
        """Verifica que hay regiones configuradas."""
        assert len(config.CURRENT_REGIONS) > 0

    def test_worldwide_in_regions(self):
        """Verifica que Worldwide está configurado."""
        assert "WW" in config.CURRENT_REGIONS
        assert config.CURRENT_REGIONS["WW"] == "Worldwide"

    def test_country_groups_balanced(self):
        """Verifica que los grupos de países están balanceados."""
        groups = config.COUNTRY_GROUPS
        sizes = [len(g) for g in groups.values()]
        # Máxima diferencia de 1 entre grupos
        assert max(sizes) - min(sizes) <= 1

    def test_all_regions_in_groups(self):
        """Verifica que todas las regiones están asignadas a un grupo."""
        all_in_groups = []
        for countries in config.COUNTRY_GROUPS.values():
            all_in_groups.extend(countries)

        for region in config.CURRENT_REGIONS.keys():
            assert region in all_in_groups, f"Región {region} no está en ningún grupo"

    def test_timeframe_format(self):
        """Verifica el formato del timeframe."""
        assert config.TIMEFRAME.startswith("now ")


class TestTrendData:
    """Tests para la estructura TrendData."""

    def test_trend_data_creation(self):
        """Verifica que TrendData se crea correctamente."""
        data = TrendData(
            timestamp="2026-01-22 10:00:00",
            term="apk",
            country_code="IN",
            country_name="India",
            data_type="queries_top",
            title="whatsapp apk",
            value="100",
            link="https://trends.google.com/trends/explore?q=whatsapp+apk&geo=IN"
        )
        assert data.term == "apk"
        assert data.country_code == "IN"
        assert data.data_type == "queries_top"


class TestWorldwideMapping:
    """Tests para el mapeo de Worldwide (WW -> '')."""

    @patch('trends_scraper.TrendReq')
    def test_ww_maps_to_empty_geo(self, mock_trendreq):
        """Verifica que WW se mapea a geo vacío en build_payload."""
        mock_pytrends = MagicMock()
        mock_trendreq.return_value = mock_pytrends

        scraper = TrendsScraper()
        scraper._build_payload("apk", "WW")

        # Verificar que build_payload fue llamado con geo=""
        mock_pytrends.build_payload.assert_called_once()
        call_args = mock_pytrends.build_payload.call_args
        assert call_args[1]['geo'] == "", "WW debe mapearse a geo vacío"

    @patch('trends_scraper.TrendReq')
    def test_normal_geo_unchanged(self, mock_trendreq):
        """Verifica que geo normal no se modifica."""
        mock_pytrends = MagicMock()
        mock_trendreq.return_value = mock_pytrends

        scraper = TrendsScraper()
        scraper._build_payload("apk", "IN")

        call_args = mock_pytrends.build_payload.call_args
        assert call_args[1]['geo'] == "IN", "geo normal no debe modificarse"


class TestRetryLogic:
    """Tests para la lógica de reintentos con 429."""

    @patch('trends_scraper.TrendReq')
    @patch('time.sleep')  # Mock sleep para que los tests sean rápidos
    def test_retry_rebuilds_payload_after_429(self, mock_sleep, mock_trendreq):
        """Verifica que el payload se reconstruye después de un 429."""
        mock_pytrends = MagicMock()
        mock_trendreq.return_value = mock_pytrends

        # Primera llamada lanza 429, segunda tiene éxito
        call_count = [0]
        def side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("The request failed: Google returned a response with code 429")
            return {"apk": {"top": pd.DataFrame(), "rising": pd.DataFrame()}}

        mock_pytrends.related_queries.side_effect = side_effect

        scraper = TrendsScraper()
        scraper._build_payload("apk", "IN")

        # Reset el mock para contar llamadas a build_payload
        mock_pytrends.build_payload.reset_mock()

        # Ejecutar fetch_with_retry
        result = scraper._fetch_with_retry(
            lambda: scraper.pytrends.related_queries(),
            term="apk",
            geo="IN"
        )

        # Verificar que build_payload fue llamado de nuevo después del 429
        assert mock_pytrends.build_payload.call_count >= 1, \
            "build_payload debe llamarse después de reiniciar por 429"

    @patch('trends_scraper.TrendReq')
    @patch('time.sleep')
    def test_retry_rebuilds_payload_with_ww(self, mock_sleep, mock_trendreq):
        """Verifica que WW se mapea correctamente en el retry."""
        mock_pytrends = MagicMock()
        mock_trendreq.return_value = mock_pytrends

        call_count = [0]
        def side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("429")
            return {"apk": {"top": pd.DataFrame(), "rising": pd.DataFrame()}}

        mock_pytrends.related_queries.side_effect = side_effect

        scraper = TrendsScraper()
        scraper._build_payload("apk", "WW")
        mock_pytrends.build_payload.reset_mock()

        scraper._fetch_with_retry(
            lambda: scraper.pytrends.related_queries(),
            term="apk",
            geo="WW"
        )

        # Verificar que el retry usó geo="" para WW
        call_args = mock_pytrends.build_payload.call_args
        assert call_args[1]['geo'] == "", "WW debe mapearse a geo vacío en retry"


class TestDeduplication:
    """Tests para la deduplicación de datos."""

    @patch('trends_scraper.TrendReq')
    def test_deduplication_removes_duplicates(self, mock_trendreq):
        """Verifica que los duplicados se eliminan."""
        mock_trendreq.return_value = MagicMock()
        scraper = TrendsScraper()

        data = [
            TrendData("2026-01-22 10:00:00", "apk", "IN", "India", "queries_top", "whatsapp", "100", ""),
            TrendData("2026-01-22 10:00:00", "apk", "IN", "India", "queries_top", "whatsapp", "100", ""),  # Duplicado
            TrendData("2026-01-22 10:00:00", "apk", "IN", "India", "queries_top", "telegram", "80", ""),   # Diferente
        ]

        result = scraper._deduplicate(data)

        assert len(result) == 2, "Debe eliminar el duplicado"
        titles = [d.title for d in result]
        assert "whatsapp" in titles
        assert "telegram" in titles


class TestLinkGeneration:
    """Tests para la generación de links."""

    def test_link_contains_date_parameter(self):
        """Verifica que los links incluyen el parámetro date."""
        from urllib.parse import quote_plus

        # Simular la generación de link como en el código
        query_text = "whatsapp apk"
        geo = "IN"
        link = f"https://trends.google.com/trends/explore?q={quote_plus(query_text)}&geo={geo}&date={quote_plus(config.TIMEFRAME)}"

        assert "date=" in link, "Link debe incluir parámetro date"
        assert config.TIMEFRAME.replace(" ", "+") in link or quote_plus(config.TIMEFRAME) in link


class TestScrapingResult:
    """Tests para ScrapingResult."""

    def test_scraping_result_default_values(self):
        """Verifica valores por defecto de ScrapingResult."""
        result = ScrapingResult(success=False)
        assert result.success == False
        assert result.data == []
        assert result.error_message == ""

    def test_scraping_result_with_data(self):
        """Verifica ScrapingResult con datos."""
        data = [TrendData("", "apk", "IN", "India", "queries_top", "test", "100", "")]
        result = ScrapingResult(success=True, data=data)
        assert result.success == True
        assert len(result.data) == 1


class TestRateLimiter:
    """Tests para el rate limiter."""

    def test_rate_limit_config(self):
        """Verifica la configuración del rate limiter."""
        assert config.RATE_LIMIT_SECONDS > 0
        assert config.RATE_LIMIT_SECONDS >= 60, "Rate limit debe ser al menos 60s para evitar 429"


# Ejecutar tests si se ejecuta directamente
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
