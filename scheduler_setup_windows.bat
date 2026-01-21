@echo off
REM ==============================================================================
REM Script para configurar Task Scheduler en Windows
REM Ejecutar como Administrador
REM ==============================================================================

echo ==============================================
echo Configuracion de Task Scheduler para Google Trends Monitor
echo ==============================================
echo.

set SCRIPT_DIR=%~dp0
set TASK_NAME=GoogleTrendsMonitor

echo Directorio del proyecto: %SCRIPT_DIR%
echo.

REM Verificar si existe main.py
if not exist "%SCRIPT_DIR%main.py" (
    echo ERROR: No se encontro main.py en %SCRIPT_DIR%
    pause
    exit /b 1
)

echo Este script creara una tarea programada que ejecuta cada 4 horas.
echo.
set /p CONFIRM="Deseas continuar? (S/N): "

if /i not "%CONFIRM%"=="S" (
    echo Operacion cancelada.
    pause
    exit /b 0
)

REM Eliminar tarea existente si existe
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

REM Crear nueva tarea programada
REM Ejecuta cada 4 horas empezando a medianoche
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "python \"%SCRIPT_DIR%main.py\"" ^
    /sc hourly ^
    /mo 4 ^
    /st 00:00 ^
    /ru "%USERNAME%" ^
    /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo Tarea programada creada exitosamente!
    echo.
    echo Horarios de ejecucion (cada 4 horas):
    echo   00:00, 04:00, 08:00, 12:00, 16:00, 20:00
    echo.
    echo Para ver la tarea: schtasks /query /tn "%TASK_NAME%"
    echo Para ejecutar ahora: schtasks /run /tn "%TASK_NAME%"
    echo Para eliminar: schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo.
    echo ERROR: No se pudo crear la tarea programada.
    echo Asegurate de ejecutar como Administrador.
)

echo.
pause
