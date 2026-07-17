"""
Tests para la frecuencia adaptativa de escaneo por país (tiers):
- load_country_tiers (main.py)
- should_scan_country (main.py)
- compute_tier / retier_countries / format_retier_section (digest.py)

Ejecutar: pytest tests/test_tiers.py -v
"""
import json
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from main import load_country_tiers, should_scan_country
from digest import compute_tier, retier_countries, format_retier_section
from database import TrendsDatabase


# =============================================================================
# 1. load_country_tiers
# =============================================================================

class TestLoadCountryTiers:
    """Carga del JSON de tiers con fail-safe."""

    def test_missing_file_returns_empty(self, tmp_path):
        """Fichero inexistente → {} (todos los países se escanean)."""
        result = load_country_tiers(path=str(tmp_path / "no_existe.json"))
        assert result == {}

    def test_corrupt_json_returns_empty(self, tmp_path):
        """JSON corrupto → {} sin lanzar excepción."""
        path = tmp_path / "corrupto.json"
        path.write_text("{esto no es json valido", encoding='utf-8')
        result = load_country_tiers(path=str(path))
        assert result == {}

    def test_non_dict_json_returns_empty(self, tmp_path):
        """JSON válido pero no-dict (ej. lista) → {}."""
        path = tmp_path / "lista.json"
        path.write_text('["high", "low"]', encoding='utf-8')
        result = load_country_tiers(path=str(path))
        assert result == {}

    def test_happy_path(self, tmp_path):
        """JSON válido se carga completo."""
        payload = {
            "updated": "2026-07-17",
            "thresholds": {"high_min_rows_day": 15, "medium_min_rows_day": 4},
            "tiers": {"IN": "high", "TH": "medium", "AU": "low"},
        }
        path = tmp_path / "tiers.json"
        path.write_text(json.dumps(payload), encoding='utf-8')
        result = load_country_tiers(path=str(path))
        assert result == payload
        assert result["tiers"]["TH"] == "medium"

    def test_seed_file_in_repo(self):
        """El seed commiteado carga y cubre todas las regiones actuales."""
        result = load_country_tiers()
        assert result, "country_tiers.json debe existir junto a main.py"
        assert set(result["tiers"].keys()) == set(config.CURRENT_REGIONS.keys())
        assert all(t in ("high", "medium", "low") for t in result["tiers"].values())


# =============================================================================
# 2. should_scan_country
# =============================================================================

TIERS = {"tiers": {"IN": "high", "TH": "medium", "AU": "low"}}

# Días de referencia: 2026-01-03 → tm_yday=3 (%3==0), 2026-01-04 → tm_yday=4
MORNING_DAY3 = datetime(2026, 1, 3, 9, 40)
AFTERNOON_DAY3 = datetime(2026, 1, 3, 21, 40)
MORNING_DAY4 = datetime(2026, 1, 4, 9, 40)
MIDNIGHT_DAY3 = datetime(2026, 1, 3, 0, 0)   # run de las 00:00 de group_1


class TestShouldScanCountry:
    """Decisión de escaneo por tier."""

    def test_high_always_scans(self):
        for now in (MORNING_DAY3, AFTERNOON_DAY3, MORNING_DAY4, MIDNIGHT_DAY3):
            scan, _ = should_scan_country("IN", TIERS, now)
            assert scan is True

    def test_medium_morning_only(self):
        scan, _ = should_scan_country("TH", TIERS, MORNING_DAY3)
        assert scan is True
        scan, reason = should_scan_country("TH", TIERS, AFTERNOON_DAY3)
        assert scan is False
        assert "medium" in reason

    def test_medium_midnight_counts_as_morning(self):
        """El run de las 00:00 (group_1) es hour 0 < 12 → su 'mañana'."""
        scan, _ = should_scan_country("TH", TIERS, MIDNIGHT_DAY3)
        assert scan is True

    def test_low_morning_and_day_mod_3(self):
        scan, _ = should_scan_country("AU", TIERS, MORNING_DAY3)
        assert scan is True

    def test_low_skips_afternoon_even_on_apt_day(self):
        scan, reason = should_scan_country("AU", TIERS, AFTERNOON_DAY3)
        assert scan is False
        assert "low" in reason

    def test_low_skips_non_apt_day(self):
        scan, reason = should_scan_country("AU", TIERS, MORNING_DAY4)
        assert scan is False
        assert "low" in reason

    def test_unknown_country_scans(self):
        """País sin tier asignado → fail-safe: siempre se escanea."""
        for now in (MORNING_DAY3, AFTERNOON_DAY3, MORNING_DAY4):
            scan, _ = should_scan_country("XX", TIERS, now)
            assert scan is True

    def test_empty_tiers_scans(self):
        """Sin fichero de tiers ({}) → todos los países se escanean."""
        scan, _ = should_scan_country("AU", {}, AFTERNOON_DAY3)
        assert scan is True

    def test_unknown_tier_value_scans(self):
        """Tier con valor desconocido → fail-safe: se escanea."""
        weird = {"tiers": {"AU": "ultra"}}
        scan, _ = should_scan_country("AU", weird, AFTERNOON_DAY3)
        assert scan is True


# =============================================================================
# 3. compute_tier (umbrales)
# =============================================================================

class TestComputeTier:
    """Asignación de tier en los límites de los umbrales."""

    THRESHOLDS = {"high_min_rows_day": 15, "medium_min_rows_day": 4}

    def test_high_boundary(self):
        # 450 filas/30d = exactamente 15/día → high
        assert compute_tier(450 / 30.0, self.THRESHOLDS) == "high"
        # 449 filas/30d = 14.97/día → medium
        assert compute_tier(449 / 30.0, self.THRESHOLDS) == "medium"

    def test_medium_boundary(self):
        # 120 filas/30d = exactamente 4/día → medium
        assert compute_tier(120 / 30.0, self.THRESHOLDS) == "medium"
        # 119 filas/30d = 3.97/día → low
        assert compute_tier(119 / 30.0, self.THRESHOLDS) == "low"

    def test_zero_is_low(self):
        assert compute_tier(0.0, self.THRESHOLDS) == "low"

    def test_default_thresholds_from_config(self):
        assert compute_tier(100.0) == "high"
        assert compute_tier(0.5) == "low"


# =============================================================================
# 4. retier_countries
# =============================================================================

class TestRetierCountries:
    """Reevaluación mensual completa con BD mockeada."""

    def _fake_db(self, volumes):
        db = MagicMock(spec=TrendsDatabase)
        db.is_connected = True
        db.get_country_volumes_30d.return_value = volumes
        return db

    def test_tier_assignment_and_changes(self, tmp_path):
        """Tiers se recalculan y los cambios se reportan."""
        tiers_path = tmp_path / "country_tiers.json"
        old = {
            "tiers": {geo: "high" for geo in config.CURRENT_REGIONS},
        }
        tiers_path.write_text(json.dumps(old), encoding='utf-8')

        # IN sigue high (3000/30=100), TH baja a medium (300/30=10),
        # AU baja a low (30/30=1); el resto (sin filas) baja a low
        volumes = {"IN": 3000, "TH": 300, "AU": 30}
        db = self._fake_db(volumes)

        changes = retier_countries(db, tiers_path=str(tiers_path))

        written = json.loads(tiers_path.read_text(encoding='utf-8'))
        assert written["tiers"]["IN"] == "high"
        assert written["tiers"]["TH"] == "medium"
        assert written["tiers"]["AU"] == "low"
        assert written["tiers"]["JP"] == "low"  # ausente en volumes → 0 filas

        # Stats con rows_30d y rows_day
        assert written["stats"]["IN"] == {"rows_30d": 3000, "rows_day": 100.0}
        assert written["stats"]["JP"] == {"rows_30d": 0, "rows_day": 0.0}
        assert written["thresholds"] == config.TIER_THRESHOLDS
        assert set(written["tiers"].keys()) == set(config.CURRENT_REGIONS.keys())

        # Cambios: todos menos IN (que sigue high)
        changed_geos = {c[0] for c in changes}
        assert "IN" not in changed_geos
        assert ("TH", "high", "medium", 10.0) in changes
        assert ("AU", "high", "low", 1.0) in changes
        assert len(changes) == len(config.CURRENT_REGIONS) - 1

    def test_no_changes(self, tmp_path):
        """Si los volúmenes mantienen los tiers, la lista de cambios es vacía."""
        tiers_path = tmp_path / "country_tiers.json"
        volumes = {geo: 3000 for geo in config.CURRENT_REGIONS}  # todos high
        old = {"tiers": {geo: "high" for geo in config.CURRENT_REGIONS}}
        tiers_path.write_text(json.dumps(old), encoding='utf-8')

        changes = retier_countries(self._fake_db(volumes), tiers_path=str(tiers_path))
        assert changes == []

    def test_missing_old_file_assumes_high(self, tmp_path):
        """Sin JSON previo, el tier anterior se asume 'high'."""
        tiers_path = tmp_path / "country_tiers.json"
        volumes = {geo: 3000 for geo in config.CURRENT_REGIONS}
        volumes["AU"] = 0  # AU → low

        changes = retier_countries(self._fake_db(volumes), tiers_path=str(tiers_path))
        assert changes == [("AU", "high", "low", 0.0)]
        assert tiers_path.exists()

    def test_boundary_volumes(self, tmp_path):
        """Límites exactos de filas/30d: 450 → high, 120 → medium."""
        tiers_path = tmp_path / "country_tiers.json"
        volumes = {geo: 3000 for geo in config.CURRENT_REGIONS}
        volumes["GB"] = 450   # 15.0/día → high
        volumes["DE"] = 449   # 14.97/día → medium
        volumes["JP"] = 120   # 4.0/día → medium
        volumes["RO"] = 119   # 3.97/día → low

        retier_countries(self._fake_db(volumes), tiers_path=str(tiers_path))
        written = json.loads(tiers_path.read_text(encoding='utf-8'))
        assert written["tiers"]["GB"] == "high"
        assert written["tiers"]["DE"] == "medium"
        assert written["tiers"]["JP"] == "medium"
        assert written["tiers"]["RO"] == "low"


# =============================================================================
# 5. Sección Markdown del digest
# =============================================================================

class TestFormatRetierSection:

    def test_with_changes(self):
        section = format_retier_section([("TH", "high", "medium", 10.0)])
        assert "## Cambios de frecuencia de escaneo" in section
        assert "| TH | high | medium | 10.0 |" in section

    def test_without_changes(self):
        section = format_retier_section([])
        assert "## Cambios de frecuencia de escaneo" in section
        assert "Sin cambios" in section


# =============================================================================
# 6. Totales honestos al omitir regiones
# =============================================================================

class TestSkipTotals:
    """El total de combinaciones excluye las regiones omitidas por tier."""

    def test_total_combinations_excludes_skipped(self):
        """Réplica del cálculo de run_monitor: los países que no se escanean
        no cuentan en total_combinations (success_rate honesto)."""
        regions = {"IN": "India", "TH": "Thailand", "AU": "Australia"}
        terms = config.CURRENT_TERMS
        now = AFTERNOON_DAY3  # tarde → medium y low se omiten

        skipped = {
            geo for geo in regions
            if not should_scan_country(geo, TIERS, now)[0]
        }
        assert skipped == {"TH", "AU"}

        total = sum(
            len(terms) + len(config.COUNTRY_EXTRA_TERMS.get(geo, []))
            for geo in regions
            if geo not in skipped
        )
        # Solo IN (sin extra terms): 3 términos base
        assert total == len(terms)

    def test_morning_apt_day_scans_everything(self):
        """En la mañana de un día %3==0 no se omite nada."""
        regions = {"IN": "India", "TH": "Thailand", "AU": "Australia"}
        skipped = {
            geo for geo in regions
            if not should_scan_country(geo, TIERS, MORNING_DAY3)[0]
        }
        assert skipped == set()
