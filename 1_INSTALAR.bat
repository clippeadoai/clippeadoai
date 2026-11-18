@echo off
chcp 65001 >nul
cd /d "%~dp0"
title GTA Clipper - Instalacion
echo.
echo ===============================================
echo   GTA Clipper - Instalacion (solo la 1a vez)
echo ===============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
  echo [X] No encuentro Python.
  echo     Instalalo desde https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
  echo     y MARCA la casilla "Add python.exe to PATH". Luego vuelve a abrir este archivo.
  pause
  exit /b 1
)
echo [OK] Python encontrado

ffmpeg -version >nul 2>&1
if errorlevel 1 (
  echo [..] No encuentro FFmpeg. Intento instalarlo automaticamente...
  winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
  echo.
  echo [!] Si se ha instalado, CIERRA esta ventana y vuelve a abrir 1_INSTALAR.bat
  echo     Si ha fallado, instala FFmpeg a mano: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
  pause
  exit /b 1
)
echo [OK] FFmpeg encontrado
echo.
echo Instalando librerias (puede tardar unos minutos)...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [X] Ha fallado la instalacion de librerias. Haz una captura y mandasela a Claude.
  pause
  exit /b 1
)
echo.
echo [OK] Librerias instaladas
python -m clipper setup
python -m clipper doctor
echo.
echo Siguiente paso: abre 2_PROBAR.bat
pause
