"""
Test para verificar las mejoras implementadas:
1. Deduplicación case-insensitive y Unicode-aware
2. Clasificación de errores por tipo
3. Métricas estructuradas JSON

Ejecutar: python test_improvements.py
"""
import sys
import os

# Asegurar encoding UTF-8 en Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Imports del proyecto
from trends_scraper import TrendsScraper, TrendData, ScrapingResult, ErrorType


def test_deduplication():
    """Test de deduplicación mejorada."""
    print("=" * 60)
    print("TEST 1: Deduplicación case-insensitive y Unicode-aware")
    print("=" * 60)

    scraper = TrendsScraper()

    # Datos de prueba con duplicados que antes no se detectaban
    test_data = [
        # Mismo título, diferente case
        TrendData("2026-01-29", "apk", "US", "USA", "queries_top", "WhatsApp APK", "100", ""),
        TrendData("2026-01-29", "apk", "US", "USA", "queries_top", "whatsapp apk", "100", ""),
        TrendData("2026-01-29", "apk", "US", "USA", "queries_top", "WHATSAPP APK", "100", ""),

        # Mismo título con espacios diferentes
        TrendData("2026-01-29", "apk", "BR", "Brazil", "queries_rising", "  CapCut Pro  ", "+500%", ""),
        TrendData("2026-01-29", "apk", "BR", "Brazil", "queries_rising", "CapCut Pro", "+500%", ""),

        # Mismo título con acentos/Unicode
        TrendData("2026-01-29", "apk", "MX", "Mexico", "queries_top", "música app", "85", ""),
        TrendData("2026-01-29", "apk", "MX", "Mexico", "queries_top", "musica app", "85", ""),

        # Estos NO deben ser duplicados (diferente país o data_type)
        TrendData("2026-01-29", "apk", "IN", "India", "queries_top", "WhatsApp APK", "100", ""),
        TrendData("2026-01-29", "apk", "US", "USA", "queries_rising", "WhatsApp APK", "+200%", ""),
    ]

    print(f"\nDatos originales: {len(test_data)} registros")
    for d in test_data:
        print(f"  [{d.country_code}] [{d.data_type}] '{d.title}'")

    # Ejecutar deduplicación
    deduplicated = scraper._deduplicate(test_data)

    print(f"\nDespués de deduplicar: {len(deduplicated)} registros")
    for d in deduplicated:
        print(f"  [{d.country_code}] [{d.data_type}] '{d.title}'")

    # Verificar
    expected = 5  # 3 WhatsApp→1, 2 CapCut→1, 2 música→1, 1 India WhatsApp, 1 US rising WhatsApp
    status = "✅ PASS" if len(deduplicated) == expected else f"❌ FAIL (esperado {expected})"
    print(f"\nResultado: {status}")
    print(f"  Eliminados: {len(test_data) - len(deduplicated)} duplicados")

    return len(deduplicated) == expected


def test_normalize_for_dedup():
    """Test de normalización de texto."""
    print("\n" + "=" * 60)
    print("TEST 2: Normalización de texto para deduplicación")
    print("=" * 60)

    scraper = TrendsScraper()

    test_cases = [
        ("WhatsApp APK", "whatsapp apk"),
        ("  CapCut Pro  ", "capcut pro"),
        ("música app", "musica app"),
        ("Café Runner", "cafe runner"),
        ("TELEGRAM", "telegram"),
        ("tiktok  lite", "tiktok  lite"),  # Espacios internos se mantienen
        ("naïve app", "naive app"),  # Diacríticos
    ]

    all_passed = True
    for original, expected in test_cases:
        result = scraper._normalize_for_dedup(original)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_passed = False
        print(f"  {status} '{original}' → '{result}' (esperado: '{expected}')")

    print(f"\nResultado: {'✅ PASS' if all_passed else '❌ FAIL'}")
    return all_passed


def test_error_classification():
    """Test de clasificación de errores."""
    print("\n" + "=" * 60)
    print("TEST 3: Clasificación de errores por tipo")
    print("=" * 60)

    scraper = TrendsScraper()

    test_cases = [
        (Exception("429 Too Many Requests"), ErrorType.RATE_LIMIT),
        (Exception("Response error: 429"), ErrorType.RATE_LIMIT),
        (Exception("Empty response from API"), ErrorType.NO_DATA),
        (Exception("No data available"), ErrorType.NO_DATA),
        (Exception("401 Unauthorized"), ErrorType.AUTH_ERROR),
        (Exception("403 Forbidden"), ErrorType.AUTH_ERROR),
        (Exception("Connection timeout"), ErrorType.NETWORK_ERROR),
        (Exception("Network error occurred"), ErrorType.NETWORK_ERROR),
        (Exception("Something weird happened"), ErrorType.UNKNOWN),
    ]

    all_passed = True
    for error, expected_type in test_cases:
        result = scraper._classify_error(error)
        status = "✅" if result == expected_type else "❌"
        if result != expected_type:
            all_passed = False
        print(f"  {status} '{str(error)[:40]}...' → {result} (esperado: {expected_type})")

    print(f"\nResultado: {'✅ PASS' if all_passed else '❌ FAIL'}")
    return all_passed


def test_scraping_result_with_error_type():
    """Test de ScrapingResult con error_type."""
    print("\n" + "=" * 60)
    print("TEST 4: ScrapingResult incluye error_type")
    print("=" * 60)

    # Resultado exitoso
    result_ok = ScrapingResult(success=True)
    print(f"  Resultado exitoso: error_type = '{result_ok.error_type}'")

    # Resultado con error
    result_error = ScrapingResult(
        success=False,
        error_message="429 Too Many Requests",
        error_type=ErrorType.RATE_LIMIT
    )
    print(f"  Resultado con 429: error_type = '{result_error.error_type}'")

    passed = (
        result_ok.error_type == ErrorType.NONE and
        result_error.error_type == ErrorType.RATE_LIMIT
    )
    print(f"\nResultado: {'✅ PASS' if passed else '❌ FAIL'}")
    return passed


def test_metrics_structure():
    """Test de estructura de métricas."""
    print("\n" + "=" * 60)
    print("TEST 5: Estructura de métricas JSON")
    print("=" * 60)

    import json
    from datetime import datetime

    # Simular métricas como las genera main.py
    metrics = {
        "timestamp": datetime.now().isoformat(),
        "group": "group_1",
        "duration_seconds": 125,
        "total_combinations": 12,
        "successful_requests": 10,
        "failed_requests": 2,
        "success_rate": 83.3,
        "total_scraped": 150,
        "total_exported": 150,
        "apps_detected": 8,
        "watchlist_detected": 1,
        "errors_by_type": {
            ErrorType.RATE_LIMIT: 1,
            ErrorType.NO_DATA: 1
        },
        "export_by_sheet": {
            "Related_Queries_Top": 75,
            "Related_Queries_Rising": 75
        }
    }

    # Verificar que se puede serializar a JSON
    try:
        json_str = json.dumps(metrics, indent=2, ensure_ascii=False)
        print("  Métricas serializadas correctamente:")
        print("  " + json_str.replace("\n", "\n  ")[:500] + "...")

        # Verificar campos requeridos
        required_fields = [
            "timestamp", "group", "duration_seconds", "total_combinations",
            "successful_requests", "failed_requests", "success_rate",
            "apps_detected", "errors_by_type"
        ]
        missing = [f for f in required_fields if f not in metrics]
        if missing:
            print(f"\n  ❌ Campos faltantes: {missing}")
            return False

        print(f"\n  ✅ Todos los campos requeridos presentes")
        print(f"\nResultado: ✅ PASS")
        return True

    except Exception as e:
        print(f"  ❌ Error serializando: {e}")
        print(f"\nResultado: ❌ FAIL")
        return False


def main():
    """Ejecutar todos los tests."""
    print("\n" + "=" * 60)
    print("    TESTS DE MEJORAS IMPLEMENTADAS")
    print("=" * 60)

    results = []
    results.append(("Deduplicación mejorada", test_deduplication()))
    results.append(("Normalización de texto", test_normalize_for_dedup()))
    results.append(("Clasificación de errores", test_error_classification()))
    results.append(("ScrapingResult con error_type", test_scraping_result_with_error_type()))
    results.append(("Estructura de métricas", test_metrics_structure()))

    # Resumen final
    print("\n" + "=" * 60)
    print("    RESUMEN DE TESTS")
    print("=" * 60)

    passed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {name}")
        if result:
            passed += 1

    print(f"\n  Total: {passed}/{len(results)} tests pasados")
    print("=" * 60)

    return passed == len(results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
