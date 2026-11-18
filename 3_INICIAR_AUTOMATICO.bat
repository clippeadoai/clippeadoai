@echo off
chcp 65001 >nul
cd /d "%~dp0"
title GTA Clipper - Automatico (no cierres esta ventana)
echo Modo automatico: busca clips nuevos cada 30 minutos.
echo Los videos aparecen en la carpeta "output". Para parar: cierra esta ventana.
echo.
python -m clipper daemon
pause
