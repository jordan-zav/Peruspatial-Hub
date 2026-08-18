@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0"

echo ============================================================
echo   PERUSPATIAL HUB - EMPAQUETADOR DE RELEASE PARA QGIS
echo ============================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] No se encontro Python en el sistema o en el PATH.
    echo Por favor asegurese de tener Python instalado.
    pause
    exit /b 1
)

python scripts\package_plugin.py --interactive

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Hubo un error durante la generacion del release.
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Proceso finalizado. El archivo .zip se encuentra en la carpeta 'releases\'.
echo.

set "openfolder=s"
set /p "openfolder=Desea abrir la carpeta 'releases' en el Explorador de Windows? [S/n]: "

if /i "!openfolder!"=="n" goto :skip_open
if /i "!openfolder!"=="no" goto :skip_open

explorer.exe releases

:skip_open
echo.
pause
