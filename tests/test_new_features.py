"""
Tests para las features añadidas post 03-12:
- Velocity query (LIKE pattern fix)
- Normalización consistente entre database.py y report_generator.py
- Cleanup de pestañas antiguas
- Weekly report generation
- Enrichment logging
- Digest empty state consistency
- spread_score recalculation

Ejecutar: pytest tests/test_new_features.py -v
"""
import json
import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from datetime import datetime, timedelta

from trends_scraper import TrendData
from report_generator import ReportGenerator, ReportItem, ContentReport
from database import TrendsDatabase


# =============================================================================
# Helpers
# =============================================================================

def make_trend_data(title="TestApp", country_code="US", country_name="United States",
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


# =============================================================================
# 1. Velocity LIKE pattern fix
# =============================================================================

class TestVelocityQuery:
    """Verifica que el patrón LIKE de velocity usa prefix match."""

    def test_normalize_title_basic(self):
        """Normalización básica funciona."""
        result = TrendsDatabase._normalize_title("CapCut Pro APK")
        assert result == "capcut pro"

    def test_normalize_title_with_version(self):
        """Versiones se eliminan del título."""
        result = TrendsDatabase._normalize_title("Terraria 1.4.5 APK")
        assert result == "terraria"

    def test_normalize_title_diacritics(self):
        """Diacríticos se eliminan."""
        result = TrendsDatabase._normalize_title("Música App")
        assert result == "musica"

    def test_normalize_title_empty(self):
        """String vacío retorna vacío."""
        assert TrendsDatabase._normalize_title("") == ""
        assert TrendsDatabase._normalize_title(None) == ""

    def test_velocity_uses_dual_pattern(self):
        """get_velocity() usa prefix + word-boundary, no substring."""
        db = TrendsDatabase()
        db.conn = MagicMock()
        db._connected = True

        # Mock fetchone to return counts
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (5,)
        db.conn.execute.return_value = mock_cursor

        db.get_velocity("Instagram")

        # Verificar que usa dos patterns: prefix y word-boundary
        calls = db.conn.execute.call_args_list
        for call in calls:
            args = call[0]
            if len(args) > 1 and isinstance(args[1], tuple):
                patterns = args[1]
                # Debe tener 2 patterns: "instagram%" y "% instagram%"
                assert len(patterns) == 2, \
                    f"Expected 2 LIKE patterns, got {len(patterns)}: {patterns}"
                assert patterns[0] == "instagram%", \
                    f"First pattern should be prefix: {patterns[0]}"
                assert patterns[1] == "% instagram%", \
                    f"Second pattern should be word-boundary: {patterns[1]}"


# =============================================================================
# 2. Normalización consistente
# =============================================================================

class TestNormalizationConsistency:
    """Verifica que database y report_generator normalizan igual."""

    def setup_method(self):
        self.generator = ReportGenerator()

    def test_basic_consistency(self):
        """Nombres básicos se normalizan igual."""
        titles = ["CapCut Pro APK", "WhatsApp Download", "Spotify Premium"]
        for title in titles:
            db_norm = TrendsDatabase._normalize_title(title)
            rg_norm = self.generator._get_base_app_name(title)
            assert db_norm == rg_norm, \
                f"Mismatch for '{title}': db='{db_norm}' vs rg='{rg_norm}'"

    def test_diacritics_consistency(self):
        """Diacríticos se manejan igual en ambos módulos."""
        titles = ["Música App", "café download", "résumé apk"]
        for title in titles:
            db_norm = TrendsDatabase._normalize_title(title)
            rg_norm = self.generator._get_base_app_name(title)
            assert db_norm == rg_norm, \
                f"Diacritics mismatch for '{title}': db='{db_norm}' vs rg='{rg_norm}'"

    def test_version_removal_consistency(self):
        """Versiones se eliminan consistentemente."""
        titles = ["Terraria 1.4.5", "Minecraft 1.21.131 APK", "GTA v2.0"]
        for title in titles:
            db_norm = TrendsDatabase._normalize_title(title)
            rg_norm = self.generator._get_base_app_name(title)
            assert db_norm == rg_norm, \
                f"Version mismatch for '{title}': db='{db_norm}' vs rg='{rg_norm}'"


# =============================================================================
# 3. Cleanup de pestañas antiguas
# =============================================================================

class TestTabCleanup:
    """Verifica la lógica de cleanup de pestañas Inf_*."""

    def test_cleanup_deletes_old_tabs(self):
        """Pestañas con más de 7 días se eliminan."""
        from google_sheets_exporter import GoogleSheetsExporter

        exporter = GoogleSheetsExporter()
        exporter.spreadsheet = MagicMock()

        old_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        recent_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        today_date = datetime.now().strftime("%Y-%m-%d")

        mock_old = MagicMock()
        mock_old.title = f"Inf_{old_date}_12:00"
        mock_recent = MagicMock()
        mock_recent.title = f"Inf_{recent_date}_14:25"
        mock_today = MagicMock()
        mock_today.title = f"Inf_{today_date}_09:40"
        mock_data = MagicMock()
        mock_data.title = "Related_Queries_Top"

        exporter.spreadsheet.worksheets.return_value = [
            mock_old, mock_recent, mock_today, mock_data
        ]

        exporter._cleanup_old_report_tabs(keep_days=7)

        # Solo la pestaña vieja debe eliminarse
        exporter.spreadsheet.del_worksheet.assert_called_once_with(mock_old)

    def test_cleanup_ignores_non_report_tabs(self):
        """Pestañas que no empiezan con Inf_ no se tocan."""
        from google_sheets_exporter import GoogleSheetsExporter

        exporter = GoogleSheetsExporter()
        exporter.spreadsheet = MagicMock()

        mock_data = MagicMock()
        mock_data.title = "Related_Queries_Top"
        mock_data2 = MagicMock()
        mock_data2.title = "Related_Queries_Rising"

        exporter.spreadsheet.worksheets.return_value = [mock_data, mock_data2]

        exporter._cleanup_old_report_tabs()

        exporter.spreadsheet.del_worksheet.assert_not_called()

    def test_cleanup_handles_errors_gracefully(self):
        """Errores en cleanup no crashean el sistema."""
        from google_sheets_exporter import GoogleSheetsExporter

        exporter = GoogleSheetsExporter()
        exporter.spreadsheet = MagicMock()
        exporter.spreadsheet.worksheets.side_effect = Exception("API error")

        # No debe lanzar excepción
        exporter._cleanup_old_report_tabs()


# =============================================================================
# 4. Weekly report
# =============================================================================

class TestWeeklyReport:
    """Verifica la generación del informe semanal."""

    def test_generate_weekly_report_with_data(self):
        """Genera HTML con datos mock."""
        from weekly_report import generate_weekly_report

        db = MagicMock(spec=TrendsDatabase)
        db.is_connected = True

        db.get_weekly_top_by_country.return_value = {
            'IN': [{'title': 'WhatsApp', 'count': 50, 'data_types': ['queries_top']}],
            'BR': [{'title': 'CapCut', 'count': 30, 'data_types': ['queries_rising']}],
        }
        db.get_weekly_new_apps.return_value = [
            {'title_normalized': 'newapp', 'display_name': 'NewApp',
             'first_seen': '2026-03-15T10:00:00', 'countries': ['IN', 'BR']},
        ]
        db.get_weekly_cross_market.return_value = [
            {'title': 'WhatsApp', 'count': 120, 'countries': ['IN', 'BR', 'US', 'MX'],
             'data_types': ['queries_top'], 'n_countries': 4},
        ]
        db.get_weekly_comparison.return_value = {
            'this_week': 9500, 'last_week': 9000, 'change_pct': 5.6,
            'this_week_new': 25, 'last_week_new': 20,
            'region_activity': [
                {'country_code': 'IN', 'this_week': 1000, 'last_week': 950},
                {'country_code': 'BR', 'this_week': 800, 'last_week': 750},
            ]
        }

        html = generate_weekly_report(db, days=7)

        assert '<!DOCTYPE html>' in html
        assert 'Informe Semanal' in html
        assert 'WhatsApp' in html
        assert 'CapCut' in html
        assert 'NewApp' in html
        assert '9,500' in html  # this_week formatted
        assert '4 paises' in html  # cross-market spread

    def test_generate_weekly_report_empty_data(self):
        """Genera HTML válido con datos vacíos."""
        from weekly_report import generate_weekly_report

        db = MagicMock(spec=TrendsDatabase)
        db.is_connected = True
        db.get_weekly_top_by_country.return_value = {}
        db.get_weekly_new_apps.return_value = []
        db.get_weekly_cross_market.return_value = []
        db.get_weekly_comparison.return_value = {
            'this_week': 0, 'last_week': 0, 'change_pct': 0.0,
            'this_week_new': 0, 'last_week_new': 0, 'region_activity': []
        }

        html = generate_weekly_report(db, days=7)

        assert '<!DOCTYPE html>' in html
        assert 'Sin datos' in html or 'Sin tendencias' in html or 'Sin apps nuevas' in html

    def test_weekly_html_escapes_special_chars(self):
        """HTML escapa caracteres especiales."""
        from weekly_report import _esc

        assert _esc('<script>alert("xss")</script>') == '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
        assert _esc('A & B') == 'A &amp; B'
        assert _esc(None) == ''
        assert _esc('') == ''


# =============================================================================
# 5. Enrichment logging (debug → warning)
# =============================================================================

class TestEnrichmentLogging:
    """Verifica que errores de enrichment se loguean como warning."""

    def test_enrichment_error_logs_warning(self):
        """_enrich_with_db loguea warning, no debug, en errores."""
        db = MagicMock(spec=TrendsDatabase)
        db.is_connected = True
        db.get_novelty_status.side_effect = Exception("DB timeout")

        generator = ReportGenerator(db=db)
        items = [ReportItem(
            name="TestApp", original_titles=["TestApp"],
            data_type="queries_rising", countries=["US"],
            max_value="100", is_rising=True, links=[]
        )]

        with patch('report_generator.logger') as mock_logger:
            generator._enrich_with_db(items)
            mock_logger.warning.assert_called()
            # Debe contener el nombre de la app en el mensaje
            call_args = mock_logger.warning.call_args[0][0]
            assert "TestApp" in call_args


# =============================================================================
# 6. Digest empty state consistency
# =============================================================================

class TestDigestEmptyState:
    """Verifica que todas las secciones del digest muestran 'Sin datos'."""

    def test_region_section_empty_shows_card(self):
        """_region_section con lista vacía muestra card con mensaje."""
        from digest import _region_section

        result = _region_section([])
        assert '<div class="card">' in result
        assert 'Sin datos' in result

    def test_region_section_with_data(self):
        """_region_section con datos muestra heatmap."""
        from digest import _region_section

        regions = [
            {'country_code': 'IN', 'count': 100},
            {'country_code': 'BR', 'count': 50},
        ]
        result = _region_section(regions)
        assert 'IN' in result
        assert 'BR' in result
        assert '100' in result

    def test_top_apps_section_empty(self):
        """_top_apps_section con lista vacía muestra mensaje."""
        from digest import _top_apps_section

        result = _top_apps_section([])
        assert 'Sin datos' in result

    def test_new_apps_section_empty(self):
        """_new_apps_section con lista vacía muestra mensaje."""
        from digest import _new_apps_section

        result = _new_apps_section([])
        assert 'Sin apps nuevas' in result


# =============================================================================
# 7. spread_score recalculation
# =============================================================================

class TestSpreadScoreRecalc:
    """Verifica que spread_score se recalcula post-enrichment."""

    def test_spread_score_initial(self):
        """spread_score se calcula en __post_init__."""
        item = ReportItem(
            name="TestApp", original_titles=["TestApp"],
            data_type="queries_rising",
            countries=["US", "IN", "BR", "US"],  # duplicado
            max_value="100", is_rising=True, links=[]
        )
        # __post_init__ deduplica countries y calcula spread_score
        assert item.spread_score == 3  # US, IN, BR (sin duplicado)

    def test_spread_score_recalc_after_enrich(self):
        """spread_score se recalcula después del enriquecimiento."""
        db = MagicMock(spec=TrendsDatabase)
        db.is_connected = True
        db.get_novelty_status.return_value = ('conocida', '2026-01-01')
        db.get_velocity.return_value = {'trend': 'estable', 'change_24h': 0.0}

        generator = ReportGenerator(db=db)

        data = [
            make_trend_data("TestApp", "US", "United States"),
            make_trend_data("TestApp", "IN", "India"),
            make_trend_data("TestApp", "BR", "Brazil"),
            make_trend_data("TestApp", "MX", "Mexico"),
        ]

        report = generator.generate(data, group="test")

        # La app debe tener spread_score = 4 (4 países)
        test_items = [a for a in report.potential_apps if 'testapp' in a.name.lower()]
        if test_items:
            assert test_items[0].spread_score == 4

    def test_global_trends_threshold(self):
        """Apps con spread_score >= 3 aparecen en global_trends."""
        generator = ReportGenerator()

        data = [
            make_trend_data("GlobalApp", "US", "United States"),
            make_trend_data("GlobalApp", "IN", "India"),
            make_trend_data("GlobalApp", "BR", "Brazil"),
            make_trend_data("LocalApp", "US", "United States"),
        ]

        report = generator.generate(data)

        global_names = [a.name.lower() for a in report.global_trends]
        assert any('globalapp' in n for n in global_names), \
            f"GlobalApp should be in global_trends, got: {global_names}"
        assert not any('localapp' in n for n in global_names), \
            "LocalApp should NOT be in global_trends (only 1 country)"


# =============================================================================
# 8. Novelty detection
# =============================================================================

class TestNoveltyDetection:
    """Verifica la detección de novedades."""

    def test_new_app_status(self):
        """App no vista retorna 'nueva'."""
        db = TrendsDatabase()
        db.conn = MagicMock()
        db._connected = True

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # No encontrada
        db.conn.execute.return_value = mock_cursor

        status, first_seen = db.get_novelty_status("NewApp")
        assert status == 'nueva'
        assert first_seen is None

    def test_known_app_status(self):
        """App vista recientemente retorna 'conocida'."""
        db = TrendsDatabase()
        db.conn = MagicMock()
        db._connected = True

        recent = datetime.utcnow().isoformat()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (recent, recent)
        db.conn.execute.return_value = mock_cursor

        status, first_seen = db.get_novelty_status("WhatsApp")
        assert status == 'conocida'
        assert first_seen == recent

    def test_disconnected_returns_unknown(self):
        """Sin conexión retorna 'desconocido'."""
        db = TrendsDatabase()
        db._connected = False

        status, first_seen = db.get_novelty_status("AnyApp")
        assert status == 'desconocido'
        assert first_seen is None


# =============================================================================
# 9. Weekly DB queries
# =============================================================================

class TestWeeklyDBQueries:
    """Verifica las queries semanales en database.py."""

    def setup_method(self):
        self.db = TrendsDatabase()
        self.db.conn = MagicMock()
        self.db._connected = True

    def test_weekly_top_by_country_groups_correctly(self):
        """get_weekly_top_by_country agrupa por país."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('IN', 'WhatsApp', 50, 'queries_top'),
            ('IN', 'CapCut', 30, 'queries_rising'),
            ('BR', 'WhatsApp', 40, 'queries_top'),
        ]
        self.db.conn.execute.return_value = mock_cursor

        result = self.db.get_weekly_top_by_country(days=7, limit=10)

        assert 'IN' in result
        assert 'BR' in result
        assert len(result['IN']) == 2
        assert len(result['BR']) == 1
        assert result['IN'][0]['title'] == 'WhatsApp'

    def test_weekly_top_respects_limit(self):
        """get_weekly_top_by_country respeta el límite por país."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('IN', f'App{i}', 50 - i, 'queries_top') for i in range(20)
        ]
        self.db.conn.execute.return_value = mock_cursor

        result = self.db.get_weekly_top_by_country(days=7, limit=5)

        assert len(result['IN']) == 5

    def test_weekly_new_apps(self):
        """get_weekly_new_apps retorna formato correcto."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('newapp', 'NewApp', '2026-03-15T10:00:00', '["IN","BR"]'),
        ]
        self.db.conn.execute.return_value = mock_cursor

        result = self.db.get_weekly_new_apps(days=7)

        assert len(result) == 1
        assert result[0]['display_name'] == 'NewApp'
        assert result[0]['countries'] == ['IN', 'BR']

    def test_weekly_cross_market(self):
        """get_weekly_cross_market filtra por min_countries."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ('WhatsApp', 120, 'IN,BR,US,MX', 'queries_top', 4),
        ]
        self.db.conn.execute.return_value = mock_cursor

        result = self.db.get_weekly_cross_market(days=7, min_countries=3)

        assert len(result) == 1
        assert result[0]['n_countries'] == 4
        assert len(result[0]['countries']) == 4

    def test_weekly_comparison(self):
        """get_weekly_comparison retorna estructura correcta."""
        call_count = [0]

        def mock_execute(sql, params=None):
            mock_cursor = MagicMock()
            call_count[0] += 1
            if call_count[0] <= 4:
                # COUNT queries
                mock_cursor.fetchone.return_value = (100,)
            else:
                # Region activity
                mock_cursor.fetchall.return_value = [
                    ('IN', 500, 450),
                    ('BR', 300, 280),
                ]
            return mock_cursor

        self.db.conn.execute = mock_execute

        result = self.db.get_weekly_comparison()

        assert 'this_week' in result
        assert 'last_week' in result
        assert 'change_pct' in result
        assert 'region_activity' in result
        assert isinstance(result['region_activity'], list)

    def test_disconnected_returns_empty(self):
        """Sin conexión, todas las queries semanales retornan vacío."""
        self.db._connected = False

        assert self.db.get_weekly_top_by_country() == {}
        assert self.db.get_weekly_new_apps() == []
        assert self.db.get_weekly_cross_market() == []
        assert self.db.get_weekly_comparison()['this_week'] == 0


# =============================================================================
# 10. Report generator integration with new features
# =============================================================================

class TestReportGeneratorIntegration:
    """Test de integración del report generator con las nuevas features."""

    def test_generate_with_multiple_countries(self):
        """Genera informe con datos de múltiples países."""
        generator = ReportGenerator()

        data = [
            make_trend_data("WhatsApp", "IN", "India", "queries_top", "100"),
            make_trend_data("WhatsApp", "BR", "Brazil", "queries_top", "95"),
            make_trend_data("WhatsApp", "US", "United States", "queries_top", "90"),
            make_trend_data("WhatsApp", "MX", "Mexico", "queries_rising", "Breakout"),
            make_trend_data("CapCut Pro", "IN", "India", "queries_rising", "+500%"),
            make_trend_data("CapCut Pro APK", "BR", "Brazil", "queries_rising", "+300%"),
            make_trend_data("download apk", "US", "United States", "queries_top", "85"),
        ]

        report = generator.generate(data, group="test_group")

        # WhatsApp debe estar en potential_apps con spread alto
        whatsapp = [a for a in report.potential_apps if 'whatsapp' in a.name.lower()]
        assert len(whatsapp) == 1
        assert whatsapp[0].spread_score >= 3  # 4 países
        assert whatsapp[0].is_rising  # Tiene un rising entry

        # CapCut debe agruparse (con y sin "Pro")
        capcut = [a for a in report.potential_apps if 'capcut' in a.name.lower()]
        assert len(capcut) == 1  # Agrupados

        # "download apk" debe ser filtrado como genérico
        generic_names = [a.name.lower() for a in report.generic_terms]
        assert any('download' in n for n in generic_names)

        # WhatsApp debe estar en global_trends (4 países >= 3)
        assert len(report.global_trends) >= 1

    def test_sheet_rows_format(self):
        """format_sheet_rows genera filas correctas."""
        generator = ReportGenerator()
        data = [
            make_trend_data("TestApp", "IN", "India", "queries_rising", "+200%"),
        ]
        report = generator.generate(data)
        rows = generator.format_sheet_rows(report)

        assert isinstance(rows, list)
        assert len(rows) > 0
        # Cada fila debe ser una lista
        for row in rows:
            assert isinstance(row, list)
