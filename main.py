"""
Script principal para el monitoreo de Google Trends.

Uso:
    python main.py                  # Ejecutar MVP (solo queries)
    python main.py --full           # Ejecutar completo (queries + topics)
    python main.py --setup          # Solo configurar pestañas en Google Sheets
    python main.py --test-scraper   # Probar scraper sin exportar
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime

import config
from trends_scraper import TrendsScraper
from google_sheets_exporter import GoogleSheetsExporter
from backup import save_backup, cleanup_old_backups
from report_generator import ReportGenerator


def setup_logging():
    """Configura el sistema de logging."""
    # Crear directorio de logs si no existe
    log_dir = os.path.join(os.path.dirname(__file__), config.LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)

    # Nombre del archivo de log con fecha
    log_filename = datetime.now().strftime("trends_%Y%m%d_%H%M%S.log")
    log_path = os.path.join(log_dir, log_filename)

    # Configurar logging
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format=config.LOG_FORMAT,
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    return logging.getLogger(__name__)


def validate_config(logger) -> bool:
    """
    Valida que la configuración necesaria esté presente y sea válida.
    Fail fast: detecta errores antes de gastar tiempo/cuota en scraping.

    Returns:
        True si la configuración es válida
    """
    errors = []
    warnings = []

    # === Validaciones críticas (bloquean ejecución) ===

    if not config.GOOGLE_SHEET_ID:
        errors.append("GOOGLE_SHEET_ID no está configurado en .env")
    elif len(config.GOOGLE_SHEET_ID) < 20:
        errors.append(f"GOOGLE_SHEET_ID parece inválido (muy corto): {config.GOOGLE_SHEET_ID[:10]}...")

    if not os.path.exists(config.GOOGLE_CREDENTIALS_PATH):
        errors.append(f"Archivo de credenciales no encontrado: {config.GOOGLE_CREDENTIALS_PATH}")

    # === Validaciones de configuración de scraping ===

    if config.RATE_LIMIT_SECONDS <= 0:
        errors.append(f"RATE_LIMIT_SECONDS debe ser positivo, actual: {config.RATE_LIMIT_SECONDS}")
    elif config.RATE_LIMIT_SECONDS < 60:
        warnings.append(f"RATE_LIMIT_SECONDS={config.RATE_LIMIT_SECONDS}s es muy bajo, riesgo de 429")

    if not config.CURRENT_TERMS:
        errors.append("CURRENT_TERMS está vacío, no hay términos para monitorear")

    if not config.CURRENT_REGIONS:
        errors.append("CURRENT_REGIONS está vacío, no hay regiones para monitorear")

    # === Validaciones de grupos de países ===

    if hasattr(config, 'COUNTRY_GROUPS'):
        all_group_countries = set()
        for group_name, countries in config.COUNTRY_GROUPS.items():
            all_group_countries.update(countries)

        missing_in_groups = set(config.CURRENT_REGIONS.keys()) - all_group_countries
        if missing_in_groups:
            warnings.append(f"Países en CURRENT_REGIONS pero no en COUNTRY_GROUPS: {missing_in_groups}")

    # === Mostrar resultados ===

    for warning in warnings:
        logger.warning(f"⚠️  {warning}")

    if errors:
        logger.error("❌ Errores de configuración encontrados:")
        for error in errors:
            logger.error(f"   • {error}")
        return False

    logger.info("✓ Configuración validada correctamente")
    return True


def run_setup(logger):
    """Configura las pestañas en Google Sheets."""
    logger.info("=== Configurando Google Sheets ===")

    exporter = GoogleSheetsExporter()

    if exporter.connect():
        exporter.setup_sheets()
        counts = exporter.get_row_counts()

        logger.info("\nEstado actual de las pestañas:")
        for sheet, count in counts.items():
            logger.info(f"  {sheet}: {count} filas")

        logger.info("\nConfiguración completada!")
    else:
        logger.error("No se pudo conectar a Google Sheets")
        sys.exit(1)


def run_health_check(logger) -> bool:
    """
    Verifica la conectividad con Google Trends y Google Sheets.

    Returns:
        True si todo está OK
    """
    logger.info("=== Health Check ===")
    all_ok = True

    # 1. Verificar Google Sheets
    logger.info("\n[1/2] Verificando conexion a Google Sheets...")
    try:
        exporter = GoogleSheetsExporter()
        if exporter.connect():
            counts = exporter.get_row_counts()
            total_rows = sum(counts.values())
            logger.info(f"  [OK] Google Sheets - {total_rows} filas totales")
        else:
            logger.error("  [FAIL] Google Sheets - No se pudo conectar")
            all_ok = False
    except Exception as e:
        logger.error(f"  [FAIL] Google Sheets - Error: {e}")
        all_ok = False

    # 2. Verificar Google Trends (intento básico)
    logger.info("\n[2/2] Verificando conexion a Google Trends...")
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl='en-US', tz=360, timeout=(5, 10))
        # Intento con suggestions (más estable que trending_searches)
        suggestions = pytrends.suggestions(keyword='test')
        if suggestions is not None:
            logger.info(f"  [OK] Google Trends - API accesible")
        else:
            logger.warning("  [WARN] Google Trends - Respuesta vacia")
    except Exception as e:
        error_str = str(e)
        if '429' in error_str:
            logger.warning(f"  [WARN] Google Trends - Rate limited (429), conectividad OK")
        elif '404' in error_str:
            logger.warning(f"  [WARN] Google Trends - Endpoint no disponible, pero puede funcionar")
        else:
            logger.error(f"  [FAIL] Google Trends - Error: {e}")
            all_ok = False

    # Resumen
    logger.info("\n" + "="*40)
    if all_ok:
        logger.info("[OK] Health check PASSED")
    else:
        logger.error("[FAIL] Health check FAILED")

    return all_ok


def run_test_scraper(logger):
    """Ejecuta el scraper sin exportar (para pruebas)."""
    logger.info("=== Modo prueba: Solo scraping ===")

    scraper = TrendsScraper()
    data = scraper.scrape_all(include_topics=False)

    logger.info(f"\nResultados: {len(data)} registros extraídos")

    # Mostrar resumen por tipo
    by_type = {}
    for item in data:
        by_type[item.data_type] = by_type.get(item.data_type, 0) + 1

    logger.info("\nPor tipo:")
    for data_type, count in by_type.items():
        logger.info(f"  {data_type}: {count}")

    # Mostrar ejemplos
    if data:
        logger.info("\nPrimeros 5 resultados:")
        for item in data[:5]:
            logger.info(f"  [{item.data_type}] {item.title}: {item.value}")


def run_monitor(logger, include_topics: bool = False, include_interest: bool = False, group: str = None):
    """
    Ejecuta el ciclo completo de monitoreo con exportación incremental.

    Args:
        include_topics: Si incluir Related Topics
        include_interest: Si incluir Interest Over Time
        group: Grupo de países a ejecutar (group_1, group_2, group_3) o None para todos
    """
    start_time = time.time()  # Para métricas de duración

    features = []
    if include_topics:
        features.append("Topics")
    if include_interest:
        features.append("Interest")
    mode = f"COMPLETO ({', '.join(features)})" if features else "MVP (solo queries)"

    # Filtrar regiones por grupo si se especifica
    if group and hasattr(config, 'COUNTRY_GROUPS') and group in config.COUNTRY_GROUPS:
        country_codes = config.COUNTRY_GROUPS[group]
        regions = {k: v for k, v in config.CURRENT_REGIONS.items() if k in country_codes}
        logger.info(f"=== Monitoreo de Google Trends ({mode}) - {group} ===")
    else:
        regions = config.CURRENT_REGIONS
        logger.info(f"=== Iniciando monitoreo de Google Trends ({mode}) ===")

    terms = config.CURRENT_TERMS
    logger.info(f"Términos: {terms}")
    logger.info(f"Regiones: {list(regions.keys())}")

    # Inicializar scraper y exporter
    scraper = TrendsScraper()
    exporter = GoogleSheetsExporter()

    if not exporter.connect():
        logger.error("No se pudo conectar a Google Sheets")
        sys.exit(1)

    # Contadores totales
    total_scraped = 0
    total_exported = 0
    export_counts = {}
    failed_combinations = []  # Tracking failed term/region combinations
    all_data = []  # Acumular todos los datos para el informe

    total_combinations = sum(
        len(terms) + len(config.COUNTRY_EXTRA_TERMS.get(geo, []))
        for geo in regions
    )
    current = 0

    logger.info(f"\nIniciando scraping incremental: {total_combinations} combinaciones en {len(regions)} países")
    for geo in regions:
        country_terms = terms + config.COUNTRY_EXTRA_TERMS.get(geo, [])
        logger.info(f"  {geo}: {len(country_terms)} términos {country_terms}")

    # Limpiar backups antiguos al inicio
    cleanup_old_backups(keep_days=7)

    for geo, country_name in regions.items():
        country_terms = terms + config.COUNTRY_EXTRA_TERMS.get(geo, [])
        for term in country_terms:
            current += 1
            logger.info(f"\n[{current}/{total_combinations}] Procesando '{term}' en {country_name} ({geo})")

            batch_data = []

            # Extraer Related Queries
            queries_result = scraper.scrape_related_queries(term, geo, country_name)
            if queries_result.success:
                batch_data.extend(queries_result.data)
                logger.info(f"  Queries: {len(queries_result.data)} registros")
            else:
                logger.error(f"  Queries fallido: {queries_result.error_message}")
                failed_combinations.append({
                    "term": term, "region": geo, "country": country_name,
                    "type": "queries", "error_type": queries_result.error_type
                })

            # Extraer Related Topics (si está habilitado)
            if include_topics:
                topics_result = scraper.scrape_related_topics(term, geo, country_name)
                if topics_result.success:
                    batch_data.extend(topics_result.data)
                    logger.info(f"  Topics: {len(topics_result.data)} registros")
                else:
                    logger.error(f"  Topics fallido: {topics_result.error_message}")
                    failed_combinations.append({
                        "term": term, "region": geo, "country": country_name,
                        "type": "topics", "error_type": topics_result.error_type
                    })

            # Extraer Interest Over Time (si está habilitado)
            if include_interest:
                interest_result = scraper.scrape_interest_over_time(term, geo, country_name)
                if interest_result.success:
                    batch_data.extend(interest_result.data)
                    logger.info(f"  Interest: {len(interest_result.data)} registros")
                else:
                    logger.error(f"  Interest fallido: {interest_result.error_message}")
                    failed_combinations.append({
                        "term": term, "region": geo, "country": country_name,
                        "type": "interest", "error_type": interest_result.error_type
                    })

            # Exportar inmediatamente este lote
            if batch_data:
                total_scraped += len(batch_data)
                all_data.extend(batch_data)  # Acumular para informe

                try:
                    batch_counts = exporter.export(batch_data)
                    for sheet, count in batch_counts.items():
                        export_counts[sheet] = export_counts.get(sheet, 0) + count
                        total_exported += count
                    logger.info(f"  Exportado: {sum(batch_counts.values())} filas a Sheets")

                    # Guardar backup incremental
                    save_backup(batch_data, f"{group}_{term}_{geo}" if group else f"{term}_{geo}")

                except Exception as e:
                    logger.error(f"  Error exportando: {e}")
                    # Guardar backup de emergencia
                    save_backup(batch_data, f"emergency_{term}_{geo}")

    # Resumen final
    logger.info(f"\n{'='*50}")
    logger.info("RESUMEN FINAL")
    logger.info(f"{'='*50}")
    logger.info(f"Total scrapeado: {total_scraped} registros")
    logger.info(f"Total exportado: {total_exported} filas")
    if export_counts:
        logger.info("Por hoja:")
        for sheet, count in export_counts.items():
            logger.info(f"  {sheet}: {count} filas")

    # Mostrar combinaciones fallidas para análisis
    if failed_combinations:
        logger.warning(f"\n⚠️  {len(failed_combinations)} extracciones fallaron:")

        # Clasificar por tipo de error
        from trends_scraper import ErrorType
        error_counts = {}
        for failure in failed_combinations:
            error_type = failure.get('error_type', ErrorType.UNKNOWN)
            error_counts[error_type] = error_counts.get(error_type, 0) + 1

        logger.warning("\n📊 Resumen por tipo de error:")
        error_labels = {
            ErrorType.RATE_LIMIT: "Rate Limit (429)",
            ErrorType.NO_DATA: "Sin datos",
            ErrorType.AUTH_ERROR: "Autenticación",
            ErrorType.NETWORK_ERROR: "Red/Conexión",
            ErrorType.UNKNOWN: "Otros",
            ErrorType.NONE: "Sin clasificar"
        }
        for error_type, count in sorted(error_counts.items(), key=lambda x: -x[1]):
            label = error_labels.get(error_type, error_type)
            logger.warning(f"  • {label}: {count}")

        # Agrupar por combinación term/region para mejor visualización
        by_combination = {}
        for failure in failed_combinations:
            key = f"{failure['term']} - {failure['region']} ({failure['country']})"
            if key not in by_combination:
                by_combination[key] = []
            by_combination[key].append(failure['type'])

        logger.warning("\n📋 Detalle de combinaciones fallidas:")
        for combination, types in sorted(by_combination.items()):
            logger.warning(f"  • {combination}: {', '.join(types)}")

        # Consejos basados en el tipo de error predominante
        logger.warning("\n💡 Próximos pasos:")
        if error_counts.get(ErrorType.RATE_LIMIT, 0) > len(failed_combinations) / 2:
            logger.warning("  → Mayoría son Rate Limit: Aumenta RATE_LIMIT_SECONDS o distribuye en más grupos")
        elif error_counts.get(ErrorType.NO_DATA, 0) > len(failed_combinations) / 2:
            logger.warning("  → Mayoría sin datos: Revisa términos/regiones (pueden no tener tráfico)")
        elif error_counts.get(ErrorType.AUTH_ERROR, 0) > 0:
            logger.warning("  → Errores de autenticación: Verifica credenciales/proxies")
        else:
            logger.warning("  → Revisa los logs para más detalles sobre los errores")
    else:
        logger.info("\n✓ Todas las extracciones completadas exitosamente")

    # Generar informe para el equipo de contenidos
    if all_data:
        logger.info("\n" + "="*50)
        logger.info("INFORME PARA CONTENIDOS")
        logger.info("="*50)

        report_generator = ReportGenerator()
        report = report_generator.generate(all_data, group=group)

        # Mostrar informe en formato plain en los logs
        logger.info("\n" + report_generator.format_plain(report))

        # Guardar informe en formato Slack para uso posterior
        slack_report = report_generator.format_slack(report)
        report_path = os.path.join(
            os.path.dirname(__file__),
            config.LOG_DIR,
            f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(slack_report)
            logger.info(f"\nInforme Slack guardado en: {report_path}")
        except Exception as e:
            logger.warning(f"No se pudo guardar informe: {e}")

        # Exportar informe a pestaña individual en Google Sheets (formato rico)
        if report.potential_apps or report.watchlist_apps:
            try:
                sheet_rows = report_generator.format_sheet_rows(report)
                sheet_name = exporter.export_report_to_sheet(
                    headers=[],  # Headers incluidos en las filas con formato rico
                    rows=sheet_rows,
                    timestamp=datetime.now()
                )
                if sheet_name:
                    logger.info(f"\n📋 Informe exportado a Google Sheets: '{sheet_name}'")
            except Exception as e:
                logger.warning(f"No se pudo exportar informe a Sheets: {e}")

        # Resumen rápido
        if report.potential_apps:
            logger.info(f"\n🎯 {len(report.potential_apps)} apps/términos detectados para revisar")
        else:
            logger.info("\nℹ️ No se detectaron apps nuevas en esta ejecución")

    # Métricas estructuradas en JSON (para monitoreo/integración)
    duration_seconds = int(time.time() - start_time)

    # Contar errores por tipo
    from trends_scraper import ErrorType
    error_breakdown = {}
    for failure in failed_combinations:
        error_type = failure.get('error_type', ErrorType.UNKNOWN)
        error_breakdown[error_type] = error_breakdown.get(error_type, 0) + 1

    metrics = {
        "timestamp": datetime.now().isoformat(),
        "group": group or "all",
        "duration_seconds": duration_seconds,
        "total_combinations": total_combinations,
        "successful_requests": total_combinations - len(failed_combinations),
        "failed_requests": len(failed_combinations),
        "success_rate": round((total_combinations - len(failed_combinations)) / total_combinations * 100, 1) if total_combinations > 0 else 0,
        "total_scraped": total_scraped,
        "total_exported": total_exported,
        "apps_detected": len(report.potential_apps) if all_data else 0,
        "watchlist_detected": len(report.watchlist_apps) if all_data else 0,
        "errors_by_type": error_breakdown,
        "export_by_sheet": export_counts
    }

    # Log métricas como JSON
    logger.info("\n📊 MÉTRICAS (JSON):")
    logger.info(json.dumps(metrics, indent=2, ensure_ascii=False))

    # Guardar métricas en archivo separado
    metrics_path = os.path.join(
        os.path.dirname(__file__),
        config.LOG_DIR,
        f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    try:
        with open(metrics_path, 'w', encoding='utf-8') as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
        logger.info(f"Métricas guardadas en: {metrics_path}")
    except Exception as e:
        logger.warning(f"No se pudieron guardar métricas: {e}")

    logger.info("\n=== Monitoreo completado ===")


def main():
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(
        description="Sistema de monitoreo de Google Trends"
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='Ejecutar modo completo (queries + topics)'
    )
    parser.add_argument(
        '--setup',
        action='store_true',
        help='Solo configurar pestañas en Google Sheets'
    )
    parser.add_argument(
        '--test-scraper',
        action='store_true',
        help='Probar scraper sin exportar a Sheets'
    )
    parser.add_argument(
        '--group',
        type=str,
        choices=['group_1', 'group_2', 'group_3', 'group_4', 'group_5'],
        help='Ejecutar solo un grupo de países (para distribución)'
    )
    parser.add_argument(
        '--interest',
        action='store_true',
        help='Incluir Interest Over Time en la extracción'
    )
    parser.add_argument(
        '--health',
        action='store_true',
        help='Ejecutar health check de conectividad'
    )

    args = parser.parse_args()

    logger = setup_logging()
    logger.info(f"Inicio de ejecución: {datetime.now().isoformat()}")

    # Modo test-scraper no requiere credenciales de Sheets
    if args.test_scraper:
        run_test_scraper(logger)
        return

    # Health check
    if args.health:
        success = run_health_check(logger)
        sys.exit(0 if success else 1)

    # Validar configuración para modos que usan Sheets
    if not validate_config(logger):
        logger.error("\nPor favor, configura las variables de entorno:")
        logger.error("  1. Copia .env.example a .env")
        logger.error("  2. Configura GOOGLE_SHEET_ID y GOOGLE_CREDENTIALS_PATH")
        logger.error("\nConsulta README.md para instrucciones detalladas.")
        sys.exit(1)

    # Ejecutar según modo
    if args.setup:
        run_setup(logger)
    else:
        run_monitor(logger, include_topics=args.full, include_interest=args.interest, group=args.group)


if __name__ == "__main__":
    main()
