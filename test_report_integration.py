"""
Test de integración del generador de informes.
Simula una ejecución del monitor con datos mock para verificar
que el informe se genera correctamente.
"""
import sys
import os

# Asegurar encoding UTF-8 para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from datetime import datetime
from trends_scraper import TrendData
from report_generator import ReportGenerator, REPORT_SHEET_HEADERS

# Datos mock que simulan una extracción real
MOCK_DATA = [
    # Rising - Alta prioridad
    TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term="apk",
        country_code="IN",
        country_name="India",
        data_type="queries_rising",
        title="capcut pro apk",
        value="Breakout",
        link="https://trends.google.com/trends/explore?q=capcut+pro+apk&geo=IN"
    ),
    TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term="apk",
        country_code="BR",
        country_name="Brazil",
        data_type="queries_rising",
        title="CapCut Pro",
        value="+450%",
        link="https://trends.google.com/trends/explore?q=capcut+pro&geo=BR"
    ),
    TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term="apk",
        country_code="ID",
        country_name="Indonesia",
        data_type="queries_rising",
        title="alight motion pro",
        value="+320%",
        link="https://trends.google.com/trends/explore?q=alight+motion+pro&geo=ID"
    ),
    TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term="download apk",
        country_code="PH",
        country_name="Philippines",
        data_type="queries_rising",
        title="Mobile Legends Bang Bang",
        value="+280%",
        link="https://trends.google.com/trends/explore?q=mobile+legends&geo=PH"
    ),

    # Top queries - Prioridad media
    TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term="apk",
        country_code="US",
        country_name="United States",
        data_type="queries_top",
        title="whatsapp",
        value="100",
        link="https://trends.google.com/trends/explore?q=whatsapp&geo=US"
    ),
    TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term="apk",
        country_code="MX",
        country_name="Mexico",
        data_type="queries_top",
        title="Spotify Premium APK",
        value="92",
        link="https://trends.google.com/trends/explore?q=spotify+premium&geo=MX"
    ),
    TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term="apk",
        country_code="IN",
        country_name="India",
        data_type="queries_top",
        title="free fire max",
        value="88",
        link="https://trends.google.com/trends/explore?q=free+fire+max&geo=IN"
    ),
    TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term="app download",
        country_code="BR",
        country_name="Brazil",
        data_type="queries_top",
        title="GTA San Andreas",
        value="75",
        link="https://trends.google.com/trends/explore?q=gta+san+andreas&geo=BR"
    ),
    TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term="apk",
        country_code="DE",
        country_name="Germany",
        data_type="queries_top",
        title="Telegram",
        value="70",
        link="https://trends.google.com/trends/explore?q=telegram&geo=DE"
    ),

    # Términos genéricos que deben filtrarse
    TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term="apk",
        country_code="WW",
        country_name="Worldwide",
        data_type="queries_top",
        title="download apk",
        value="95",
        link="https://trends.google.com/trends/explore?q=download+apk"
    ),
    TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term="apk",
        country_code="IN",
        country_name="India",
        data_type="queries_top",
        title="mod apk",
        value="82",
        link="https://trends.google.com/trends/explore?q=mod+apk&geo=IN"
    ),
    TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term="apk",
        country_code="BR",
        country_name="Brazil",
        data_type="queries_top",
        title="free games",
        value="60",
        link="https://trends.google.com/trends/explore?q=free+games&geo=BR"
    ),
    TrendData(
        timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        term="apk",
        country_code="ID",
        country_name="Indonesia",
        data_type="queries_rising",
        title="hack",
        value="+150%",
        link="https://trends.google.com/trends/explore?q=hack&geo=ID"
    ),
]


def test_report_generation():
    """Prueba la generación del informe."""
    print("=" * 60)
    print("TEST: Generación de Informe para Contenidos")
    print("=" * 60)
    print()

    # Mock de DB con apps conocidas: el detector estricto rescata títulos
    # pelados (sin token de app) solo si apps_seen los conoce — como en
    # producción con Turso disponible
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_db.is_known_app.return_value = True
    mock_db.get_novelty_status.return_value = ('conocida', None)
    mock_db.get_velocities_batch.return_value = {}
    generator = ReportGenerator(db=mock_db)
    report = generator.generate(MOCK_DATA, group="group_1")

    # Verificar clasificación
    print("📊 RESULTADOS DE CLASIFICACIÓN:")
    print("-" * 40)
    print(f"Total items procesados: {report.total_items_processed}")
    print(f"Términos únicos: {report.total_unique_terms}")
    print(f"Apps/términos detectados: {len(report.potential_apps)}")
    print(f"Términos genéricos filtrados: {len(report.generic_terms)}")
    print()

    # Listar apps detectadas
    print("✅ APPS DETECTADAS:")
    for app in report.potential_apps:
        rising_mark = "🔥" if app.is_rising else "📈"
        print(f"   {rising_mark} {app.name} ({', '.join(app.countries)}) - {app.max_value}")
    print()

    # Listar genéricos filtrados
    print("⏭️ GENÉRICOS FILTRADOS:")
    for term in report.generic_terms:
        print(f"   - {term.name}")
    print()

    # Mostrar formato Slack
    print("=" * 60)
    print("FORMATO SLACK (para copiar/pegar):")
    print("=" * 60)
    print()
    print(generator.format_slack(report))
    print()

    # Mostrar filas para Sheet
    print("=" * 60)
    print("FILAS PARA GOOGLE SHEET:")
    print("=" * 60)
    print()
    print("Headers:", REPORT_SHEET_HEADERS)
    rows = generator.format_sheet_rows(report)
    for i, row in enumerate(rows[:5]):  # Mostrar primeras 5
        print(f"Row {i+1}: {row}")
    if len(rows) > 5:
        print(f"... y {len(rows) - 5} filas más")
    print()

    # Verificaciones
    print("=" * 60)
    print("VERIFICACIONES:")
    print("=" * 60)

    app_names = [app.name for app in report.potential_apps]
    generic_names = [term.name for term in report.generic_terms]

    # Apps que DEBEN estar detectadas
    expected_apps = ["Capcut Pro", "Alight Motion Pro", "Mobile Legends Bang Bang",
                     "Whatsapp", "Spotify Premium", "Free Fire Max", "GTA San Andreas", "Telegram"]

    # Términos que DEBEN estar filtrados
    expected_generic = ["Download", "Mod", "Free Games", "Hack"]

    all_ok = True

    app_names_lower = [n.lower() for n in app_names]
    for app in expected_apps:
        if app.lower() in app_names_lower:
            print(f"   ✅ '{app}' detectada correctamente")
        else:
            print(f"   ❌ '{app}' NO detectada (debería estar)")
            all_ok = False

    for term in expected_generic:
        if term in generic_names:
            print(f"   ✅ '{term}' filtrado correctamente")
        else:
            print(f"   ❌ '{term}' NO filtrado (debería estar en genéricos)")
            all_ok = False

    print()
    if all_ok:
        print("🎉 TODAS LAS VERIFICACIONES PASARON")
    else:
        print("⚠️ ALGUNAS VERIFICACIONES FALLARON")

    return all_ok


if __name__ == "__main__":
    success = test_report_generation()
    sys.exit(0 if success else 1)
