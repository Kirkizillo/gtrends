"""
Script principal para el monitoreo de Google Trends.

Uso:
    python main.py                  # Ejecutar MVP (solo queries)
    python main.py --full           # Ejecutar completo (queries + topics)
    python main.py --setup          # Solo configurar pestañas en Google Sheets
    python main.py --test-scraper   # Probar scraper sin exportar
"""
import argparse
import logging
import os
import sys
from datetime import datetime

import config
from trends_scraper import TrendsScraper
from google_sheets_exporter import GoogleSheetsExporter
from backup import save_backup, cleanup_old_backups


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
    Valida que la configuración necesaria esté presente.

    Returns:
        True si la configuración es válida
    """
    errors = []

    if not config.GOOGLE_SHEET_ID:
        errors.append("GOOGLE_SHEET_ID no está configurado en .env")

    if not os.path.exists(config.GOOGLE_CREDENTIALS_PATH):
        errors.append(f"Archivo de credenciales no encontrado: {config.GOOGLE_CREDENTIALS_PATH}")

    if errors:
        for error in errors:
            logger.error(error)
        return False

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
    Ejecuta el ciclo completo de monitoreo.

    Args:
        include_topics: Si incluir Related Topics
        include_interest: Si incluir Interest Over Time
        group: Grupo de países a ejecutar (group_1, group_2, group_3) o None para todos
    """
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

    logger.info(f"Términos: {config.CURRENT_TERMS}")
    logger.info(f"Regiones: {list(regions.keys())}")

    # Fase 1: Scraping
    logger.info("\n[1/2] Extrayendo datos de Google Trends...")
    scraper = TrendsScraper()
    data = scraper.scrape_all(regions=regions, include_topics=include_topics, include_interest=include_interest)

    if not data:
        logger.warning("No se extrajeron datos. Finalizando.")
        return

    logger.info(f"Extraídos {len(data)} registros")

    # Guardar backup local
    backup_path = save_backup(data, group)
    if backup_path:
        logger.info(f"Backup guardado: {backup_path}")

    # Limpiar backups antiguos (más de 7 días)
    cleanup_old_backups(keep_days=7)

    # Fase 2: Exportación
    logger.info("\n[2/2] Exportando a Google Sheets...")
    exporter = GoogleSheetsExporter()

    try:
        export_counts = exporter.export(data)

        logger.info("\nResumen de exportación:")
        total_exported = 0
        for sheet, count in export_counts.items():
            logger.info(f"  {sheet}: {count} filas")
            total_exported += count

        logger.info(f"\nTotal exportado: {total_exported} filas")

    except ConnectionError as e:
        logger.error(f"Error de conexión: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error durante exportación: {e}")
        sys.exit(1)

    logger.info("\n=== Monitoreo completado exitosamente ===")


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
        choices=['group_1', 'group_2', 'group_3'],
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
