"""
Tests para el fix de consistencia Sheets/Slack: get_today_top_apps() debe
fusionar variantes de nombre sin espacios ("789 Bingo" == "789bingo"),
igual que report_generator._get_base_app_name() ya hace para los informes
por-run. Antes de este fix, el digest podía mostrar la misma app partida
en dos filas con el conteo repartido.

Ejecutar: pytest tests/test_digest_dedup.py -v
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import TrendsDatabase


def _make_db_with_rows(rows):
    """DB mockeada cuyo execute(...).fetchall() devuelve `rows` una vez."""
    db = TrendsDatabase()
    db._connected = True
    db.conn = MagicMock()
    db.conn.execute.return_value.fetchall.return_value = rows
    return db


class TestTopAppsSpaceCollapseDedup:
    def test_merges_spaced_and_unspaced_variants(self):
        rows = [
            ("789 Bingo", 5, "IN", "queries_rising"),
            ("789bingo", 3, "TR", "queries_top"),
        ]
        db = _make_db_with_rows(rows)
        result = db.get_today_top_apps(limit=10, date="2026-07-20")

        assert len(result) == 1
        item = result[0]
        assert item['count'] == 8
        assert item['title'] == "789 Bingo"  # variante con espacio, más legible
        assert set(item['countries']) == {"IN", "TR"}
        assert set(item['data_types']) == {"queries_rising", "queries_top"}

    def test_does_not_merge_genuinely_different_apps(self):
        rows = [
            ("WhatsApp", 10, "US", "queries_top"),
            ("Instagram", 7, "IN", "queries_top"),
        ]
        db = _make_db_with_rows(rows)
        result = db.get_today_top_apps(limit=10, date="2026-07-20")

        assert len(result) == 2
        titles = {item['title'] for item in result}
        assert titles == {"WhatsApp", "Instagram"}

    def test_tie_break_prefers_higher_individual_count_when_same_spacing(self):
        # Mismo número de espacios (1 cada uno) -> el desempate cae en el
        # conteo individual, no en el número de espacios.
        rows = [
            ("Fire Kirin", 2, "US", "queries_rising"),
            ("FIRE KIRIN", 9, "US", "queries_rising"),
        ]
        db = _make_db_with_rows(rows)
        result = db.get_today_top_apps(limit=10, date="2026-07-20")

        assert len(result) == 1
        assert result[0]['title'] == "FIRE KIRIN"
        assert result[0]['count'] == 11

    def test_merged_result_respects_limit_after_dedup(self):
        # 3 variantes de la misma app (sin sufijo apk/app, para no mezclar con
        # el recorte de sufijos) + 2 apps distintas; limit=2 debe devolver la
        # app fusionada (conteo total 12) y la segunda más alta, no cortar las
        # variantes antes de fusionarlas.
        rows = [
            ("Fire Kirin", 4, "IN", "queries_rising"),
            ("FireKirin", 4, "BR", "queries_rising"),
            ("Fire  Kirin", 4, "US", "queries_rising"),  # doble espacio -> misma key
            ("Roblox", 6, "TR", "queries_top"),
            ("Minecraft", 3, "WW", "queries_top"),
        ]
        db = _make_db_with_rows(rows)
        result = db.get_today_top_apps(limit=2, date="2026-07-20")

        assert len(result) == 2
        assert result[0]['count'] == 12  # Fire Kirin fusionado, primero
        assert result[1]['title'] == "Roblox"

    def test_overfetch_multiplier_applied_to_sql_limit_param(self):
        db = _make_db_with_rows([])
        db.get_today_top_apps(limit=10, date="2026-07-20")

        call_args = db.conn.execute.call_args
        sql, params = call_args[0]
        assert params[-1] == max(10 * 5, 100)  # overfetch, no el limit real

    def test_not_connected_returns_empty(self):
        db = TrendsDatabase()
        assert db.get_today_top_apps(limit=10) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
