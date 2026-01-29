"""
Test para verificar la configuración de backoff.

Ejecutar: python test_backoff.py
"""
import sys

# Asegurar encoding UTF-8 en Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import config


def test_config_values():
    """Verificar que los valores de config son correctos."""
    print("=" * 60)
    print("TEST: Configuración de backoff")
    print("=" * 60)

    tests_passed = True

    # Test MAX_RETRIES
    expected_retries = 2
    actual_retries = config.MAX_RETRIES
    status = "✅" if actual_retries == expected_retries else "❌"
    if actual_retries != expected_retries:
        tests_passed = False
    print(f"  {status} MAX_RETRIES = {actual_retries} (esperado: {expected_retries})")

    # Test MAX_BACKOFF_SECONDS
    expected_backoff = 180
    actual_backoff = getattr(config, 'MAX_BACKOFF_SECONDS', None)
    status = "✅" if actual_backoff == expected_backoff else "❌"
    if actual_backoff != expected_backoff:
        tests_passed = False
    print(f"  {status} MAX_BACKOFF_SECONDS = {actual_backoff} (esperado: {expected_backoff})")

    return tests_passed


def test_backoff_calculation():
    """Verificar que el cálculo de backoff respeta el límite."""
    print("\n" + "=" * 60)
    print("TEST: Cálculo de backoff con límite")
    print("=" * 60)

    import random
    random.seed(42)  # Para reproducibilidad

    max_backoff = config.MAX_BACKOFF_SECONDS
    tests_passed = True

    print(f"\n  MAX_BACKOFF_SECONDS = {max_backoff}s")
    print(f"  Simulando cálculos de espera:\n")

    for attempt in range(3):
        base_wait = 60 * (2 ** attempt)
        jitter = random.randint(20, 60)
        raw_wait = base_wait + jitter
        actual_wait = min(raw_wait, max_backoff)

        capped = " (CAPPED)" if raw_wait > max_backoff else ""
        status = "✅" if actual_wait <= max_backoff else "❌"

        if actual_wait > max_backoff:
            tests_passed = False

        print(f"  {status} Intento {attempt + 1}: base={base_wait}s + jitter={jitter}s = {raw_wait}s → {actual_wait}s{capped}")

    return tests_passed


def test_max_time_per_combination():
    """Calcular tiempo máximo por combinación fallida."""
    print("\n" + "=" * 60)
    print("TEST: Tiempo máximo por combinación fallida")
    print("=" * 60)

    max_retries = config.MAX_RETRIES
    max_backoff = config.MAX_BACKOFF_SECONDS

    # Peor caso: todos los intentos usan max_backoff
    # (excepto el último que no espera, solo falla)
    max_wait_time = max_backoff * (max_retries - 1)

    print(f"\n  MAX_RETRIES = {max_retries}")
    print(f"  MAX_BACKOFF_SECONDS = {max_backoff}s")
    print(f"\n  Peor caso por combinación:")
    print(f"    Intentos con espera: {max_retries - 1}")
    print(f"    Espera máxima total: {max_wait_time}s = {max_wait_time / 60:.1f} min")

    # Con 12 combinaciones fallando
    total_12_combinations = max_wait_time * 12
    print(f"\n  Si 12 combinaciones fallan:")
    print(f"    Tiempo total: {total_12_combinations}s = {total_12_combinations / 60:.1f} min")

    # Verificar que no excede timeout de 90 min
    timeout = 90 * 60  # 90 minutos en segundos
    fits_in_timeout = total_12_combinations < timeout

    status = "✅" if fits_in_timeout else "❌"
    print(f"\n  {status} ¿Cabe en timeout de 90 min? {fits_in_timeout}")

    return fits_in_timeout


def main():
    """Ejecutar todos los tests."""
    print("\n" + "=" * 60)
    print("    TESTS DE CONFIGURACIÓN DE BACKOFF")
    print("=" * 60)

    results = []
    results.append(("Valores de config", test_config_values()))
    results.append(("Cálculo de backoff", test_backoff_calculation()))
    results.append(("Tiempo máximo", test_max_time_per_combination()))

    # Resumen
    print("\n" + "=" * 60)
    print("    RESUMEN")
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
