"""
Tests de calidad del informe (jul-2026):
- Clasificación casino/betting en sección propia
- Detector estricto de apps (filtra "ocular migraine", "come")
- Dedup con colapso de espacios ("789 bingo" ≡ "789bingo")
- Formateo de scores con unidades (+39,400% vs Breakout vs 0-100)
- Badge RSS Trending Now (📰)
- Compatibilidad hacia atrás de generate()

Ejecutar: pytest tests/test_report_quality.py -v
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from trends_scraper import TrendData
from report_generator import (
    ReportGenerator, ReportItem, ContentReport, CASINO_PATTERNS
)
from database import TrendsDatabase


# =============================================================================
# Helpers
# =============================================================================

def make_trend_data(title, country_code="US", country_name="United States",
                    data_type="queries_rising", value="Breakout", term="apk"):
    return TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term=term,
        country_code=country_code,
        country_name=country_name,
        data_type=data_type,
        title=title,
        value=value,
        link="https://trends.google.com/test"
    )


def names_of(items):
    return [i.name.lower() for i in items]


# =============================================================================
# 1. Clasificación casino / betting
# =============================================================================

class TestCasinoClassification:

    def setup_method(self):
        self.generator = ReportGenerator()

    def test_casino_positives_pattern(self):
        """Términos de casino coinciden con CASINO_PATTERNS."""
        positives = [
            "789 jackpots apk", "789bingo", "789 bingo", "fire kirin xyz",
            "winzo app download", "91 club download apk", "777win",
            "4rabet", "orion stars", "teen patti gold", "aviator game",
            "365 jeet", "bg 678 game", "game vault 999", "juwa casino",
            "milkyway apk", "rummy circle", "lottery sambad", "bet365",
        ]
        for term in positives:
            assert CASINO_PATTERNS.search(term), f"'{term}' debería ser casino"

    def test_casino_negatives_pattern(self):
        """Apps legítimas NO coinciden con CASINO_PATTERNS."""
        negatives = [
            "minecraft", "roblox", "roblox apk", "whatsapp apk",
            "alphabet learning", "capcut pro", "spotify", "terraria 1.4.5",
            "789",  # número solo no debe coincidir
            "2026",
        ]
        for term in negatives:
            assert not CASINO_PATTERNS.search(term), f"'{term}' NO debería ser casino"

    def test_casino_items_go_to_own_section(self):
        """Items de casino van a casino_apps, no a potential_apps ni watchlist."""
        data = [
            make_trend_data("789 jackpots apk", value="+39400%"),
            make_trend_data("fire kirin xyz apk", value="Breakout"),
            make_trend_data("winzo app download", value="+500%"),
            make_trend_data("91 club download apk", value="+300%"),
            make_trend_data("roblox apk", value="+200%"),
            make_trend_data("whatsapp apk", value="100", data_type="queries_top"),
        ]
        report = self.generator.generate(data)

        casino_names = names_of(report.casino_apps)
        assert len(report.casino_apps) == 4
        assert any('jackpot' in n for n in casino_names)
        assert any('kirin' in n for n in casino_names)
        assert any('winzo' in n for n in casino_names)
        assert any('club' in n for n in casino_names)

        potential_names = names_of(report.potential_apps)
        assert any('roblox' in n for n in potential_names)
        assert any('whatsapp' in n for n in potential_names)
        assert not any('winzo' in n for n in potential_names)

        # Casino fuera de watchlist aunque coincida con patrones gambling
        watchlist_names = names_of(report.watchlist_apps)
        assert not any('jackpot' in n for n in watchlist_names)

        # Categoría correcta
        for item in report.casino_apps:
            assert item.category == 'casino'
        for item in report.potential_apps:
            assert item.category == 'app'

    def test_casino_excluded_from_global_trends_and_summary(self):
        """Casino no aparece en tendencias globales ni resumen ejecutivo."""
        data = [
            make_trend_data("fire kirin apk", "US", "United States"),
            make_trend_data("fire kirin apk", "IN", "India"),
            make_trend_data("fire kirin apk", "BR", "Brazil"),
        ]
        report = self.generator.generate(data)

        assert not report.global_trends
        assert not report.potential_apps
        summary = ' '.join(report.executive_summary).lower()
        assert 'kirin' not in summary

    def test_casino_section_in_all_formats(self):
        """La sección 🎰 aparece en plain, Slack y Sheets."""
        data = [make_trend_data("789 jackpots apk", value="Breakout")]
        report = self.generator.generate(data)

        slack = self.generator.format_slack(report)
        assert "🎰 *CASINO / BETTING (1)*" in slack

        plain = self.generator.format_plain(report)
        assert "CASINO / BETTING (1)" in plain

        rows = self.generator.format_sheet_rows(report)
        flat = [cell for row in rows for cell in row]
        assert any("CASINO / BETTING" in c for c in flat)


# =============================================================================
# 2. Detector estricto de apps
# =============================================================================

class TestStrictAppDetector:

    def setup_method(self):
        self.generator = ReportGenerator()

    def test_ocular_migraine_filtered(self):
        """Términos sin señal de app se filtran a no_app_terms."""
        data = [
            make_trend_data("ocular migraine", value="+39400%"),
            make_trend_data("capcut pro apk", value="+500%"),
        ]
        report = self.generator.generate(data)

        assert not any('migraine' in n for n in names_of(report.potential_apps))
        assert any('migraine' in n for n in names_of(report.no_app_terms))
        assert any('capcut' in n for n in names_of(report.potential_apps))

    def test_come_filtered_by_stopword(self):
        """'come' está en la stoplist y se filtra siempre."""
        data = [make_trend_data("come", value="Breakout")]
        report = self.generator.generate(data)

        assert not report.potential_apps
        assert any(n == 'come' for n in names_of(report.no_app_terms))

    def test_minecraft_kept_when_token_backed(self):
        """'minecraft' sin token sobrevive si existe 'minecraft ... apk indir'."""
        data = [
            make_trend_data("minecraft", value="Breakout"),
            make_trend_data("minecraft son surum apk indir", "TR", "Turkey", value="+300%"),
        ]
        report = self.generator.generate(data)

        potential_names = names_of(report.potential_apps)
        assert any(n == 'minecraft' for n in potential_names), \
            f"minecraft debería sobrevivir, potential={potential_names}"
        assert not any('minecraft' in n for n in names_of(report.no_app_terms))

    def test_bare_title_filtered_without_backing(self):
        """Título sin token, sin respaldo y en 1 solo país se filtra."""
        data = [make_trend_data("minecraft", value="Breakout")]
        report = self.generator.generate(data)

        assert not report.potential_apps
        assert any('minecraft' in n for n in names_of(report.no_app_terms))

    def test_multi_country_kept_without_token(self):
        """Ante la duda: título sin token pero en 2+ países se mantiene."""
        data = [
            make_trend_data("whatsapp", "IN", "India", "queries_top", "100"),
            make_trend_data("whatsapp", "BR", "Brazil", "queries_top", "95"),
        ]
        report = self.generator.generate(data)

        assert any('whatsapp' in n for n in names_of(report.potential_apps))

    def test_app_tokens_multilingual(self):
        """Tokens de app en varios idiomas se reconocen."""
        gen = self.generator
        assert gen._title_has_app_token("minecraft apk")
        assert gen._title_has_app_token("winzo app download")
        assert gen._title_has_app_token("whatsapp indir")
        assert gen._title_has_app_token("скачать minecraft")
        assert gen._title_has_app_token("ดาวน์โหลด tiktok")
        assert gen._title_has_app_token("télécharger capcut")
        assert gen._title_has_app_token("aplicación de fotos")
        assert not gen._title_has_app_token("ocular migraine")
        assert not gen._title_has_app_token("whatsapp")  # 'app' embebido no cuenta

    def test_no_app_filtered_shown_in_footer(self):
        """Los filtrados no-app se listan en el footer de los renders."""
        data = [
            make_trend_data("ocular migraine", value="+39400%"),
            make_trend_data("capcut pro apk", value="+500%"),
        ]
        report = self.generator.generate(data)

        slack = self.generator.format_slack(report)
        assert "No-app filtrados (1)" in slack
        assert "Ocular Migraine" in slack

        rows = self.generator.format_sheet_rows(report)
        flat = [cell for row in rows for cell in row]
        assert any("No-app filtrados (1)" in c for c in flat)


# =============================================================================
# 3. Dedup con colapso de espacios
# =============================================================================

class TestSpaceCollapseDedup:

    def setup_method(self):
        self.generator = ReportGenerator()

    def test_spaced_and_collapsed_merge(self):
        """'789bingo' y '789 Bingo' se agrupan en un solo item."""
        data = [
            make_trend_data("789bingo apk", "IN", "India", value="+500%"),
            make_trend_data("789 Bingo apk", "BR", "Brazil", value="Breakout"),
        ]
        report = self.generator.generate(data)

        assert len(report.casino_apps) == 1
        item = report.casino_apps[0]
        # Se prefiere la variante con espacios
        assert item.name == "789 Bingo"
        assert len(set(item.countries)) == 2

    def test_non_casino_space_collapse(self):
        """Colapso de espacios también aplica a apps normales."""
        data = [
            make_trend_data("picsart apk", value="+200%"),
            make_trend_data("pics art apk", value="+300%"),
        ]
        report = self.generator.generate(data)

        assert len(report.potential_apps) == 1
        assert report.potential_apps[0].name == "Pics Art"

    def test_suffix_variants_not_merged(self):
        """Variantes con sufijo ('Fire Kirin Xyz') siguen siendo items propios."""
        data = [
            make_trend_data("fire kirin apk", value="+200%"),
            make_trend_data("fire kirin xyz apk", value="+300%"),
        ]
        report = self.generator.generate(data)

        assert len(report.casino_apps) == 2


# =============================================================================
# 4. Formateo de scores con unidades
# =============================================================================

class TestScoreFormatting:

    def setup_method(self):
        self.generator = ReportGenerator()

    def _item(self, value, is_rising):
        return ReportItem(
            name="TestApp", original_titles=["TestApp"],
            data_type="queries_rising" if is_rising else "queries_top",
            countries=["US"], max_value=value, is_rising=is_rising, links=[]
        )

    def test_rising_big_number_gets_percent(self):
        assert self.generator._format_score(self._item("39400", True)) == "+39,400%"

    def test_breakout_stays_breakout(self):
        assert self.generator._format_score(self._item("Breakout", True)) == "Breakout"

    def test_top_score_plain(self):
        assert self.generator._format_score(self._item("85", False)) == "85"

    def test_rising_small_percent_unchanged(self):
        assert self.generator._format_score(self._item("+500%", True)) == "+500%"

    def test_formatted_score_in_renders(self):
        """El score formateado aparece en plain, Slack y Sheets."""
        data = [
            make_trend_data("capcut pro apk", value="39400"),
            make_trend_data("whatsapp apk", data_type="queries_top", value="85"),
        ]
        report = self.generator.generate(data)

        plain = self.generator.format_plain(report)
        assert "+39,400%" in plain
        assert "Valor: 85" in plain

        slack = self.generator.format_slack(report)
        assert "+39,400%" in slack
        assert "Score: 85" in slack

        rows = self.generator.format_sheet_rows(report)
        flat = [cell for row in rows for cell in row]
        assert "+39,400%" in flat
        assert "85" in flat


# =============================================================================
# 5. Badge RSS Trending Now
# =============================================================================

class TestRssTrendingBadge:

    def setup_method(self):
        self.generator = ReportGenerator()

    def test_rss_match_sets_flag_and_badge(self):
        data = [make_trend_data("minecraft apk", value="Breakout")]
        report = self.generator.generate(
            data, rss_titles=["Minecraft new update", "otro trend"]
        )

        item = report.potential_apps[0]
        assert item.rss_trending is True

        slack = self.generator.format_slack(report)
        assert "📰" in slack

        plain = self.generator.format_plain(report)
        assert "📰" in plain

        rows = self.generator.format_sheet_rows(report)
        flat = [cell for row in rows for cell in row]
        assert any("📰" in c for c in flat)

    def test_rss_match_executive_summary_bullet(self):
        data = [make_trend_data("minecraft apk", value="Breakout")]
        report = self.generator.generate(data, rss_titles=["minecraft"])

        assert any(
            "también está en Trending Now de Google (señal fuerte)" in b
            for b in report.executive_summary
        )

    def test_rss_no_match_no_badge(self):
        data = [make_trend_data("capcut pro apk", value="Breakout")]
        report = self.generator.generate(data, rss_titles=["taylor swift concert"])

        assert report.potential_apps[0].rss_trending is False
        assert "📰" not in self.generator.format_slack(report)

    def test_rss_normalization_diacritics(self):
        """Títulos RSS se normalizan igual que nombres de apps."""
        data = [make_trend_data("musica apk", value="Breakout")]
        report = self.generator.generate(data, rss_titles=["Música App"])

        assert report.potential_apps[0].rss_trending is True

    def test_generate_without_rss_titles_backward_compatible(self):
        """generate() sin rss_titles funciona como antes."""
        data = [make_trend_data("capcut pro apk", value="Breakout")]

        report_old = self.generator.generate(data, group="group_1")
        assert isinstance(report_old, ContentReport)
        assert report_old.potential_apps[0].rss_trending is False

        report_no_group = self.generator.generate(data)
        assert isinstance(report_no_group, ContentReport)

        report_none = self.generator.generate(data, group="g", rss_titles=None)
        assert report_none.potential_apps[0].rss_trending is False

        report_empty = self.generator.generate(data, group="g", rss_titles=[])
        assert report_empty.potential_apps[0].rss_trending is False


# =============================================================================
# 6. Integración con DB mockeada
# =============================================================================

class TestWithMockedDb:

    def test_generate_with_db_enriches_casino_too(self):
        """El enriquecimiento con Turso no rompe con items casino."""
        db = MagicMock(spec=TrendsDatabase)
        db.is_connected = True
        db.get_novelty_status.return_value = ('nueva', None)
        db.get_velocities_batch.return_value = {}

        generator = ReportGenerator(db=db)
        data = [
            make_trend_data("789 jackpots apk", value="+39400%"),
            make_trend_data("capcut pro apk", value="+500%"),
        ]
        report = generator.generate(data, group="test")

        assert len(report.casino_apps) == 1
        assert len(report.potential_apps) == 1
        # new_apps solo considera potential_apps (casino excluido)
        assert names_of(report.new_apps) == ['capcut pro']
        # Ambos se enriquecieron
        assert report.casino_apps[0].novelty == 'nueva'
        assert report.potential_apps[0].novelty == 'nueva'
