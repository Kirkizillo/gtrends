"""
Módulo de backup local para datos extraídos.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import List
from dataclasses import asdict

import config
from trends_scraper import TrendData

logger = logging.getLogger(__name__)

BACKUP_DIR = "backups"


def save_backup(data: List[TrendData], group: str = None) -> str:
    """
    Guarda los datos extraídos en un archivo JSON como backup.

    Args:
        data: Lista de TrendData a guardar
        group: Grupo de países (opcional, para el nombre del archivo)

    Returns:
        Ruta del archivo de backup creado
    """
    # Crear directorio de backups si no existe
    backup_dir = os.path.join(os.path.dirname(__file__), BACKUP_DIR)
    os.makedirs(backup_dir, exist_ok=True)

    # Generar nombre de archivo
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    group_suffix = f"_{group}" if group else ""
    filename = f"trends_backup_{timestamp}{group_suffix}.json"
    filepath = os.path.join(backup_dir, filename)

    # Convertir datos a formato serializable
    backup_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "group": group,
        "record_count": len(data),
        "data": [asdict(item) for item in data]
    }

    # Guardar archivo
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        logger.info(f"Backup guardado: {filepath} ({len(data)} registros)")
        return filepath
    except Exception as e:
        logger.error(f"Error guardando backup: {e}")
        return ""


def load_backup(filepath: str) -> List[TrendData]:
    """
    Carga datos desde un archivo de backup.

    Args:
        filepath: Ruta al archivo de backup

    Returns:
        Lista de TrendData
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)

        data = []
        for item in backup_data.get("data", []):
            data.append(TrendData(**item))

        logger.info(f"Backup cargado: {filepath} ({len(data)} registros)")
        return data
    except Exception as e:
        logger.error(f"Error cargando backup: {e}")
        return []


def list_backups() -> List[str]:
    """
    Lista todos los archivos de backup disponibles.

    Returns:
        Lista de rutas a archivos de backup
    """
    backup_dir = os.path.join(os.path.dirname(__file__), BACKUP_DIR)

    if not os.path.exists(backup_dir):
        return []

    backups = []
    for filename in os.listdir(backup_dir):
        if filename.startswith("trends_backup_") and filename.endswith(".json"):
            backups.append(os.path.join(backup_dir, filename))

    return sorted(backups, reverse=True)  # Más recientes primero


def cleanup_old_backups(keep_days: int = 7):
    """
    Elimina backups más antiguos que keep_days días.

    Args:
        keep_days: Número de días a mantener
    """
    backup_dir = os.path.join(os.path.dirname(__file__), BACKUP_DIR)

    if not os.path.exists(backup_dir):
        return

    now = datetime.now(timezone.utc)
    deleted_count = 0

    for filename in os.listdir(backup_dir):
        if not filename.startswith("trends_backup_"):
            continue

        filepath = os.path.join(backup_dir, filename)
        file_time = datetime.fromtimestamp(os.path.getmtime(filepath), tz=timezone.utc)
        age_days = (now - file_time).days

        if age_days > keep_days:
            try:
                os.remove(filepath)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Error eliminando backup antiguo {filename}: {e}")

    if deleted_count > 0:
        logger.info(f"Eliminados {deleted_count} backups antiguos (>{keep_days} días)")
