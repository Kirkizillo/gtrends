"""
Tests para el digest privado de Slack:
- render_utils: banderas, flechas de tendencia, sparkline
- digest.build_slack_digest_blocks: TL;DR, secciones, demote de casino,
  degradación limpia, escapado de texto

Ejecutar: pytest tests/test_slack_digest.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import render_utils
from digest import build_slack_digest_blocks, _slack_esc, _slack_tldr, _mock_digest_data


# =============================================================================
# render_utils
# =============================================================================

class TestFlags:
    def test_known_country_returns_flag(self):
        assert render_utils.flag("IN") == "🇮🇳"
        assert render_utils.flag("US") == "🇺🇸"

    def test_unknown_country_returns_empty(self):
        assert render_utils.flag("ZZ") == ""

    def test_flag_or_code_known(self):
        result = render_utils.flag_or_code("BR")
        assert "🇧🇷" in result and "BR" in result

    def test_flag_or_code_unknown_falls_back_to_code_only(self):
        assert render_utils.flag_or_code("ZZ") == "ZZ"

    def test_worldwide_uses_globe(self):
        assert render_utils.flag("WW") == "🌍"


class TestTrendArrow:
    def test_positive_change_is_up(self):
        assert render_utils.trend_arrow(15.4) == "▲"

    def test_negative_change_is_down(self):
        assert render_utils.trend_arrow(-8.0) == "▼"

    def test_small_change_is_flat(self):
        assert render_utils.trend_arrow(0.2) == "▬"
        assert render_utils.trend_arrow(-0.5) == "▬"

    def test_boundary_just_above_threshold(self):
        assert render_utils.trend_arrow(1.01) == "▲"
        assert render_utils.trend_arrow(-1.01) == "▼"


class TestSparkline:
    def test_empty_list_returns_empty_string(self):
        assert render_utils.sparkline([]) == ""

    def test_constant_values_use_lowest_block(self):
        result = render_utils.sparkline([50, 50, 50])
        assert result == "▁▁▁"
        assert len(result) == 3

    def test_varying_values_scale_to_min_max(self):
        result = render_utils.sparkline([0, 50, 100])
        assert len(result) == 3
        # El mínimo debe ser el bloque más bajo y el máximo el más alto
        assert result[0] == "▁"
        assert result[-1] == "█"

    def test_length_matches_input(self):
        values = [1, 5, 3, 9, 2, 7, 4]
        assert len(render_utils.sparkline(values)) == len(values)


# =============================================================================
# digest.build_slack_digest_blocks
# =============================================================================

def _find_block_containing(blocks, needle):
    """Devuelve el primer block cuyo texto (section/context) contiene needle."""
    for b in blocks:
        if b.get("type") == "section" and needle in b.get("text", {}).get("text", ""):
            return b
        if b.get("type") == "context":
            for el in b.get("elements", []):
                if needle in el.get("text", ""):
                    return b
    return None


class TestBuildSlackDigestBlocks:
    def test_mock_data_produces_all_sections(self):
        data = _mock_digest_data("2026-07-20")
        blocks = build_slack_digest_blocks(data)

        types = [b["type"] for b in blocks]
        assert types[0] == "header"
        assert "divider" in types

        # TL;DR menciona la app líder
        assert _find_block_containing(blocks, "minecraft") is not None
        # Sección de apps nuevas presente
        assert _find_block_containing(blocks, "Apps nuevas") is not None
        # Sección casino demotada presente y separada
        casino_block = _find_block_containing(blocks, "Casino / Betting")
        assert casino_block is not None
        # Regiones en un context block
        assert _find_block_containing(blocks, "Regiones más activas") is not None

    def test_casino_items_excluded_from_top_apps_section(self):
        data = _mock_digest_data("2026-07-20")
        blocks = build_slack_digest_blocks(data)
        top_apps_block = _find_block_containing(blocks, "Top apps de hoy")
        assert "789 jackpots" not in top_apps_block["text"]["text"]
        assert "fire kirin" not in top_apps_block["text"]["text"]

    def test_degraded_mode_shows_warning_and_skips_sections(self):
        data = {'date': '2026-07-20', 'degraded': True, 'comparison': {},
                'top_apps': [], 'new_apps': [], 'region_activity': [], 'history_7d': []}
        blocks = build_slack_digest_blocks(data)

        tldr_block = blocks[1]
        assert "degradado" in tldr_block["text"]["text"].lower() \
            or "Modo degradado" in tldr_block["text"]["text"]
        # Sin secciones de datos (solo header, TL;DR, divider, footer divider, footer)
        assert _find_block_containing(blocks, "Top apps de hoy") is None
        assert _find_block_containing(blocks, "Volumen del día") is None

    def test_no_apps_no_casino_shows_empty_state(self):
        data = {'date': '2026-07-20', 'degraded': False,
                'comparison': {'today': 0, 'yesterday': 0, 'change_pct': 0.0},
                'top_apps': [], 'new_apps': [], 'region_activity': [], 'history_7d': []}
        blocks = build_slack_digest_blocks(data)
        assert _find_block_containing(blocks, "Sin apps detectadas hoy") is not None

    def test_sparkline_included_when_history_present(self):
        data = _mock_digest_data("2026-07-20")
        blocks = build_slack_digest_blocks(data)
        vol_block = _find_block_containing(blocks, "Volumen del día")
        assert "`" in vol_block["text"]["text"]  # sparkline en code span

    def test_no_sparkline_without_history(self):
        data = _mock_digest_data("2026-07-20")
        data['history_7d'] = []
        blocks = build_slack_digest_blocks(data)
        vol_block = _find_block_containing(blocks, "Volumen del día")
        assert "últimos" not in vol_block["text"]["text"]

    def test_footer_link_only_when_url_provided(self):
        data = _mock_digest_data("2026-07-20")
        blocks_without = build_slack_digest_blocks(data)
        blocks_with = build_slack_digest_blocks(data, full_report_url="https://example.com/report")

        assert "Ver informe completo" not in blocks_without[-1]["elements"][0]["text"]
        assert "Ver informe completo" in blocks_with[-1]["elements"][0]["text"]
        assert "example.com" in blocks_with[-1]["elements"][0]["text"]

    def test_caps_top_apps_to_eighteen_with_overflow_note(self):
        data = _mock_digest_data("2026-07-20")
        # 25 apps normales (sin patrones de casino) para forzar el cap
        data['top_apps'] = [
            {'title': f'app number {i}', 'count': 25 - i, 'countries': ['US'],
             'data_types': ['queries_top'], 'link': ''}
            for i in range(25)
        ]
        blocks = build_slack_digest_blocks(data)
        top_block = _find_block_containing(blocks, "Top apps de hoy")
        text = top_block["text"]["text"]
        assert text.count("•") == 18
        assert "+7 más" in text

    def test_rising_vs_top_marker_per_app_line(self):
        data = _mock_digest_data("2026-07-20")
        data['top_apps'] = [
            {'title': 'app rising', 'count': 5, 'countries': ['US'],
             'data_types': ['queries_rising'], 'link': ''},
            {'title': 'app top', 'count': 4, 'countries': ['US'],
             'data_types': ['queries_top'], 'link': ''},
        ]
        blocks = build_slack_digest_blocks(data)
        text = _find_block_containing(blocks, "Top apps de hoy")["text"]["text"]
        assert "🔥 *app rising*" in text
        assert "📈 *app top*" in text

    def test_history_all_zero_does_not_crash(self):
        data = _mock_digest_data("2026-07-20")
        data['history_7d'] = [{'date': '2026-07-1%d' % i, 'count': 0} for i in range(4, 11)]
        blocks = build_slack_digest_blocks(data)  # no debe lanzar excepción
        assert blocks


class TestSlackEscaping:
    def test_escapes_ampersand_and_angle_brackets(self):
        assert _slack_esc("a & b <c> d") == "a &amp; b &lt;c&gt; d"

    def test_empty_string(self):
        assert _slack_esc("") == ""
        assert _slack_esc(None) == ""

    def test_app_name_with_special_chars_in_blocks(self):
        data = _mock_digest_data("2026-07-20")
        data['top_apps'] = [
            {'title': 'Fast & Furious <APK>', 'count': 5, 'countries': ['US'],
             'data_types': ['queries_top'], 'link': ''}
        ]
        blocks = build_slack_digest_blocks(data)
        top_block = _find_block_containing(blocks, "Top apps de hoy")
        assert "<APK>" not in top_block["text"]["text"]
        assert "&lt;APK&gt;" in top_block["text"]["text"]


class TestSlackTldr:
    def test_headline_names_top_app(self):
        data = _mock_digest_data("2026-07-20")
        app_items = [a for a in data['top_apps'] if 'jackpot' not in a['title']
                     and 'kirin' not in a['title'] and 'winzo' not in a['title']]
        tldr = _slack_tldr(data, app_items, [])
        assert "minecraft" in tldr

    def test_degraded_overrides_headline(self):
        data = {'degraded': True}
        tldr = _slack_tldr(data, [], [])
        assert "degradado" in tldr.lower() or "Modo degradado" in tldr

    def test_only_casino_no_apps(self):
        data = {'degraded': False, 'new_apps': []}
        casino_items = [{'title': '789 jackpots', 'count': 5, 'countries': ['IN']}]
        tldr = _slack_tldr(data, [], casino_items)
        assert "casino" in tldr.lower()

    def test_no_activity_at_all(self):
        data = {'degraded': False, 'new_apps': []}
        tldr = _slack_tldr(data, [], [])
        assert "Sin actividad" in tldr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
