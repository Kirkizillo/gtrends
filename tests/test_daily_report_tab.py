"""
Tests para las pestañas diarias de informe (Inf_YYYY-MM-DD):
- Creación de la pestaña cuando no existe (con posicionamiento)
- Append con separador cuando la pestaña del día ya existe
- Cleanup compatible con ambos formatos de nombre (nuevo y legacy)

Ejecutar: pytest tests/test_daily_report_tab.py -v
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

import gspread

from google_sheets_exporter import GoogleSheetsExporter


HEADERS = ['app', 'paises', 'valor']
ROWS = [
    ['CapCut', 'BR,MX', 'Breakout'],
    ['WhatsApp', 'IN', '+300%'],
]


def make_exporter():
    """Crea un exporter con spreadsheet mockeado (sin conexión real)."""
    exporter = GoogleSheetsExporter()
    exporter.spreadsheet = MagicMock()
    return exporter


# =============================================================================
# 1. Creación de pestaña cuando no existe
# =============================================================================

class TestTabCreatedWhenMissing:
    """Primera exportación del día → se crea la pestaña diaria."""

    def test_creates_daily_tab_with_date_only_name(self):
        """El nombre de la pestaña es Inf_YYYY-MM-DD, sin hora."""
        exporter = make_exporter()
        exporter.spreadsheet.worksheet.side_effect = \
            gspread.exceptions.WorksheetNotFound("no existe")
        mock_ws = MagicMock()
        exporter.spreadsheet.add_worksheet.return_value = mock_ws

        ts = datetime(2026, 7, 17, 14, 32)
        result = exporter.export_report_to_sheet(HEADERS, ROWS, timestamp=ts)

        assert result == "Inf_2026-07-17"
        exporter.spreadsheet.add_worksheet.assert_called_once()
        kwargs = exporter.spreadsheet.add_worksheet.call_args.kwargs
        assert kwargs['title'] == "Inf_2026-07-17"
        assert kwargs['cols'] == len(HEADERS)

    def test_writes_headers_and_rows_on_create(self):
        """En la creación se escriben headers y datos, sin separador."""
        exporter = make_exporter()
        exporter.spreadsheet.worksheet.side_effect = \
            gspread.exceptions.WorksheetNotFound("no existe")
        mock_ws = MagicMock()
        exporter.spreadsheet.add_worksheet.return_value = mock_ws

        exporter.export_report_to_sheet(HEADERS, ROWS,
                                        timestamp=datetime(2026, 7, 17, 2, 0))

        mock_ws.append_row.assert_called_once_with(HEADERS)
        mock_ws.append_rows.assert_called_once_with(ROWS, value_input_option='RAW')

    def test_positions_new_tab_after_related_queries_rising(self):
        """La pestaña nueva se mueve a la posición 2 (tras Related_Queries_Rising)."""
        exporter = make_exporter()
        exporter.spreadsheet.worksheet.side_effect = \
            gspread.exceptions.WorksheetNotFound("no existe")
        mock_ws = MagicMock()
        exporter.spreadsheet.add_worksheet.return_value = mock_ws

        exporter.export_report_to_sheet(HEADERS, ROWS,
                                        timestamp=datetime(2026, 7, 17, 2, 0))

        mock_ws.update_index.assert_called_once_with(2)


# =============================================================================
# 2. Append con separador cuando la pestaña existe
# =============================================================================

class TestAppendWhenTabExists:
    """Runs posteriores del mismo día → append debajo del contenido."""

    def test_appends_with_separator_containing_run_time(self):
        """Se agrega fila en blanco + separador con hora + headers + datos."""
        exporter = make_exporter()
        mock_ws = MagicMock()
        exporter.spreadsheet.worksheet.return_value = mock_ws

        ts = datetime(2026, 7, 17, 14, 32)
        result = exporter.export_report_to_sheet(HEADERS, ROWS, timestamp=ts)

        assert result == "Inf_2026-07-17"
        # No se crea pestaña nueva ni se reposiciona
        exporter.spreadsheet.add_worksheet.assert_not_called()
        mock_ws.update_index.assert_not_called()

        mock_ws.append_rows.assert_called_once()
        block = mock_ws.append_rows.call_args[0][0]

        # Estructura: [""], [separador], headers, filas de datos
        assert block[0] == [""], "La primera fila debe estar en blanco"
        separator = block[1][0]
        assert "14:32" in separator, "El separador debe contener la hora del run"
        assert "UTC" in separator
        assert "═══" in separator
        assert block[2] == HEADERS
        assert block[3:] == ROWS, "Los datos deben ir después del separador y headers"

    def test_append_uses_raw_input_option(self):
        """El append usa value_input_option='RAW' como el resto del exporter."""
        exporter = make_exporter()
        mock_ws = MagicMock()
        exporter.spreadsheet.worksheet.return_value = mock_ws

        exporter.export_report_to_sheet(HEADERS, ROWS,
                                        timestamp=datetime(2026, 7, 17, 9, 40))

        assert mock_ws.append_rows.call_args.kwargs.get('value_input_option') == 'RAW'

    def test_append_without_headers(self):
        """Sin headers, el bloque es blanco + separador + datos."""
        exporter = make_exporter()
        mock_ws = MagicMock()
        exporter.spreadsheet.worksheet.return_value = mock_ws

        exporter.export_report_to_sheet([], ROWS,
                                        timestamp=datetime(2026, 7, 17, 21, 40))

        block = mock_ws.append_rows.call_args[0][0]
        assert block[0] == [""]
        assert "21:40" in block[1][0]
        assert block[2:] == ROWS


# =============================================================================
# 3. Cleanup con ambos formatos de nombre
# =============================================================================

class TestCleanupBothFormats:
    """El cleanup parsea Inf_YYYY-MM-DD e Inf_YYYY-MM-DD_HH:MM."""

    def _make_ws(self, title):
        ws = MagicMock()
        ws.title = title
        return ws

    def test_deletes_old_tabs_in_both_formats(self):
        """Pestañas viejas se eliminan sea cual sea su formato."""
        exporter = make_exporter()

        old_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        recent_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

        old_legacy = self._make_ws(f"Inf_{old_date}_12:00")
        old_daily = self._make_ws(f"Inf_{old_date}")
        recent_legacy = self._make_ws(f"Inf_{recent_date}_14:25")
        recent_daily = self._make_ws(f"Inf_{recent_date}")
        data_tab = self._make_ws("Related_Queries_Rising")

        exporter.spreadsheet.worksheets.return_value = [
            old_legacy, old_daily, recent_legacy, recent_daily, data_tab
        ]

        exporter._cleanup_old_report_tabs(keep_days=7)

        deleted = [c[0][0] for c in
                   exporter.spreadsheet.del_worksheet.call_args_list]
        assert old_legacy in deleted
        assert old_daily in deleted
        assert recent_legacy not in deleted
        assert recent_daily not in deleted
        assert data_tab not in deleted
        assert len(deleted) == 2

    def test_keeps_tabs_within_keep_days(self):
        """Pestañas de hoy y de hace <7 días no se tocan."""
        exporter = make_exporter()
        today = datetime.now().strftime("%Y-%m-%d")

        exporter.spreadsheet.worksheets.return_value = [
            self._make_ws(f"Inf_{today}"),
            self._make_ws(f"Inf_{today}_09:40"),
        ]

        exporter._cleanup_old_report_tabs(keep_days=7)

        exporter.spreadsheet.del_worksheet.assert_not_called()

    def test_ignores_non_report_and_malformed_tabs(self):
        """Pestañas no-informe o con fecha inválida se ignoran."""
        exporter = make_exporter()

        exporter.spreadsheet.worksheets.return_value = [
            self._make_ws("Related_Queries_Top"),
            self._make_ws("Inf_notadate99"),   # 14 chars pero sin fecha válida
            self._make_ws("Inf_2020"),          # demasiado corta
            self._make_ws("Informe_general"),   # empieza por Inf_ pero no es fecha
        ]

        exporter._cleanup_old_report_tabs(keep_days=7)

        exporter.spreadsheet.del_worksheet.assert_not_called()

    def test_parse_report_tab_date(self):
        """_parse_report_tab_date acepta ambos formatos y rechaza el resto."""
        parse = GoogleSheetsExporter._parse_report_tab_date
        assert parse("Inf_2026-07-17") == "2026-07-17"
        assert parse("Inf_2026-07-17_14:32") == "2026-07-17"
        assert parse("Inf_2026-7-17") is None
        assert parse("Related_Queries_Top") is None
        assert parse("Inf_abc") is None

    def test_cleanup_handles_errors_gracefully(self):
        """Errores de la API no crashean el cleanup."""
        exporter = make_exporter()
        exporter.spreadsheet.worksheets.side_effect = Exception("API error")

        # No debe lanzar excepción
        exporter._cleanup_old_report_tabs()
