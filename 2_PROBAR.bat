@echo off
chcp 65001 >nul
cd /d "%~dp0"
title GTA Clipper - Prueba
echo Buscando y editando clips (la primera vez descarga el modelo de subtitulos, tarda un poco)...
echo.
python -m clipper run
echo.
echo Abriendo la carpeta con los videos...
if exist output start "" "output"
echo Si te gustan, abre 3_INICIAR_AUTOMATICO.bat para dejarlo funcionando solo.
pause
