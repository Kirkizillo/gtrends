"""
Tests unitarios para rss_trends.py (feed RSS "Trending Now").
"""
import sys
import os
from unittest.mock import patch, MagicMock

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rss_trends
from rss_trends import fetch_trending_rss, is_geo_supported
from trends_scraper import ErrorType


# Fixture: feed RSS mínimo con el namespace ht real
RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
  <channel>
    <title>Daily Search Trends</title>
    <item>
      <title>ejemplo app viral</title>
      <ht:approx_traffic>200+</ht:approx_traffic>
      <pubDate>Tue, 07 Jul 2026 10:00:00 -0700</pubDate>
      <link>https://trends.google.com/trending?geo=US&amp;q=ejemplo</link>
    </item>
    <item>
      <title>otro trend</title>
      <ht:approx_traffic>1000+</ht:approx_traffic>
      <pubDate>Tue, 07 Jul 2026 09:00:00 -0700</pubDate>
    </item>
  </channel>
</rss>
"""


def _mock_response(text, status_code=200):
    response = MagicMock()
    response.text = text
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    return response


class TestFetchTrendingRss:
    """Tests del parseo del feed RSS."""

    @patch('rss_trends.requests.get')
    def test_parse_ok(self, mock_get):
        mock_get.return_value = _mock_response(RSS_FIXTURE)

        result = fetch_trending_rss("US", "United States")

        assert result.success is True
        assert result.error_type == ErrorType.NONE
        assert len(result.data) == 2

        first = result.data[0]
        assert first.data_type == "trending_rss"
        assert first.term == "trending"
        assert first.country_code == "US"
        assert first.country_name == "United States"
        assert first.title == "ejemplo app viral"
        assert first.value == "200+"
        assert first.link == "https://trends.google.com/trending?geo=US&q=ejemplo"
        # timestamp con formato "%Y-%m-%d %H:%M:%S"
        assert len(first.timestamp) == 19
        assert first.timestamp[4] == "-" and first.timestamp[10] == " "

        # Item sin <link> → fallback a URL de explore
        second = result.data[1]
        assert second.title == "otro trend"
        assert second.value == "1000+"
        assert "trends.google.com/trends/explore" in second.link
        assert "geo=US" in second.link

        # URL correcta del feed
        called_url = mock_get.call_args[0][0]
        assert called_url == "https://trends.google.com/trending/rss?geo=US"

    @patch('rss_trends.time.sleep')  # no esperar entre reintentos
    @patch('rss_trends.requests.get')
    def test_timeout(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.exceptions.Timeout("timed out")

        result = fetch_trending_rss("US", "United States")

        assert result.success is False
        assert result.error_type == ErrorType.NETWORK_ERROR
        assert result.data == []
        # 1 intento + 1 reintento
        assert mock_get.call_count == 2

    @patch('rss_trends.time.sleep')
    @patch('rss_trends.requests.get')
    def test_xml_invalido(self, mock_get, mock_sleep):
        mock_get.return_value = _mock_response("esto no es XML")

        result = fetch_trending_rss("US", "United States")

        assert result.success is False
        assert result.error_type == ErrorType.UNKNOWN

    @patch('rss_trends.requests.get')
    def test_feed_vacio(self, mock_get):
        empty = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
        mock_get.return_value = _mock_response(empty)

        result = fetch_trending_rss("US", "United States")

        assert result.success is False
        assert result.error_type == ErrorType.NO_DATA

    def test_ww_no_soportado(self):
        # WW no tiene variante en el feed (sin geo devuelve US)
        assert is_geo_supported("WW") is False
        assert is_geo_supported("US") is True

        result = fetch_trending_rss("WW", "Worldwide")
        assert result.success is False
        assert result.error_type == ErrorType.NO_DATA
