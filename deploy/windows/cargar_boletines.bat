@echo off
setlocal EnableExtensions
:: Sube a Ambar los Boletines Consolidados de la BVRD que ya descargaste en tu navegador.
:: No descarga nada de la BVRD: solo copia los Excel de tu carpeta Descargas al servidor y los procesa alli.

set "KEY_PATH=%USERPROFILE%\Downloads\ssh-key-2026-11-27.key"
set "DOWNLOADS=%USERPROFILE%\Downloads"
set "SERVER=ubuntu@147.5.111.149"

echo =======================================================
echo   CARGA DE BOLETINES BVRD A LA TERMINAL AMBAR
echo =======================================================
echo.

if not exist "%KEY_PATH%" (
    echo [ERROR] No encuentro la llave SSH en:
    echo %KEY_PATH%
    pause
    exit /b 1
)

if not exist "%DOWNLOADS%\*Consolidado*.xlsx" (
    echo [ERROR] No hay archivos "*Consolidado*.xlsx" en:
    echo %DOWNLOADS%
    echo.
    echo Descargalos primero desde tu navegador y vuelve a ejecutar este archivo.
    pause
    exit /b 1
)

:: 1. Copiar al servidor, uno por uno (scp de Windows no expande comodines).
::    -p conserva la hora del archivo: si bajaste dos versiones del mismo dia, queda la mas reciente.
echo [1/3] Subiendo archivos al servidor...
set "FALLO="
for %%F in ("%DOWNLOADS%\*Consolidado*.xlsx") do (
    echo   %%~nxF
    scp -p -q -i "%KEY_PATH%" "%%~fF" %SERVER%:~/ || set "FALLO=1"
)
if defined FALLO (
    echo.
    echo [ERROR] No se pudo subir al menos un archivo. Revisa la conexion o la llave.
    pause
    exit /b 1
)

:: 2. Procesar en el servidor
echo.
echo [2/3] Procesando boletines en el servidor...
ssh -i "%KEY_PATH%" %SERVER% "sudo git -C /opt/ambar pull -q && sudo bash /opt/ambar/deploy/servidor/cargar.sh ~/*Consolidado*.xlsx"
if errorlevel 1 (
    echo.
    echo [ERROR] El servidor no pudo procesar los boletines. Revisa los mensajes de arriba.
    echo Los archivos quedan en el servidor; puedes volver a ejecutar este archivo.
    pause
    exit /b 1
)

:: 3. Limpiar
echo.
echo [3/3] Borrando las copias del servidor...
ssh -i "%KEY_PATH%" %SERVER% "rm -f ~/*Consolidado*.xlsx"

echo.
echo =======================================================
echo   LISTO. Recarga Ambar para ver los datos.
echo =======================================================
echo.
echo Conviene borrar los Excel de Descargas: si quedan, la proxima vez se vuelven a subir.
set /p BORRAR="Borrar los Excel de tu carpeta Descargas? (S/N): "
if /i "%BORRAR%"=="S" (
    del "%DOWNLOADS%\*Consolidado*.xlsx"
    echo Archivos locales eliminados.
)
pause
