#!/bin/bash
# ==============================================================================
# Script para configurar el cron job de monitoreo de Google Trends
# Ejecutar con: bash scheduler_setup.sh
# ==============================================================================

# Obtener directorio del script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_PATH=$(which python3 || which python)
MAIN_SCRIPT="$SCRIPT_DIR/main.py"

echo "=============================================="
echo "Configuración de Cron para Google Trends Monitor"
echo "=============================================="
echo ""
echo "Directorio del proyecto: $SCRIPT_DIR"
echo "Python: $PYTHON_PATH"
echo ""

# Verificar que existe main.py
if [ ! -f "$MAIN_SCRIPT" ]; then
    echo "ERROR: No se encontró main.py en $SCRIPT_DIR"
    exit 1
fi

# Crear la línea de cron (cada 4 horas)
CRON_LINE="0 */4 * * * cd $SCRIPT_DIR && $PYTHON_PATH $MAIN_SCRIPT >> $SCRIPT_DIR/logs/cron.log 2>&1"

echo "Línea de cron a agregar:"
echo "$CRON_LINE"
echo ""

read -p "¿Deseas agregar esta línea al crontab? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Obtener crontab actual y agregar nueva línea
    (crontab -l 2>/dev/null | grep -v "trends_monitor/main.py"; echo "$CRON_LINE") | crontab -

    echo ""
    echo "Cron job agregado exitosamente!"
    echo ""
    echo "Crontab actual:"
    crontab -l
else
    echo ""
    echo "Operación cancelada."
    echo ""
    echo "Para agregar manualmente, ejecuta: crontab -e"
    echo "Y agrega la siguiente línea:"
    echo "$CRON_LINE"
fi

echo ""
echo "=============================================="
echo "Horarios de ejecución (cada 4 horas):"
echo "  00:00, 04:00, 08:00, 12:00, 16:00, 20:00"
echo "=============================================="
