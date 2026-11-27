@echo off
setlocal EnableExtensions
:: Carga en Ambar los Boletines Consolidados de la BVRD que ya descargaste en tu navegador.
:: Procesa todo en esta computadora y sube el resultado directo a Supabase. No se conecta a la BVRD.
set "BASE=C:\AmbarBot"

echo =======================================================
echo   CARGA DE BOLETINES BVRD A LA TERMINAL AMBAR
echo =======================================================
echo.

if not exist "%BASE%\venv\Scripts\python.exe" (
    echo [ERROR] Falta la instalacion en %BASE%. Ejecuta primero instalar.ps1.
    pause
    exit /b 1
)

"%BASE%\venv\Scripts\python.exe" "%BASE%\repo\scripts\cargar_local.py" --base "%BASE%"
if errorlevel 1 (
    echo.
    echo [ERROR] La carga no termino. Revisa los mensajes de arriba.
    pause
    exit /b 1
)

echo.
echo =======================================================
echo   LISTO. Recarga Ambar para ver los datos.
echo =======================================================
pause
