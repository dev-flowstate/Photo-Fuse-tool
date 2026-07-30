@echo off
title Photo Fuse - install
cd /d "%~dp0"

echo ======================================================
echo   Photo Fuse - one-time setup
echo ======================================================
echo.

python --version >nul 2>&1
if errorlevel 1 goto nopython

echo Found Python:
python --version
echo.
echo Installing Pillow, numpy and openpyxl...
echo.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo.
echo ======================================================
echo   Done. Now double-click "2 - START Photo Fuse.bat"
echo ======================================================
pause
exit /b 0

:nopython
echo Python is NOT installed (or not on PATH).
echo.
echo 1. Go to https://www.python.org/downloads/
echo 2. Download Python 3.10 or newer.
echo 3. IMPORTANT: tick "Add python.exe to PATH" on the first install screen.
echo 4. Finish the install, then run this file again.
echo.
pause
exit /b 1

:failed
echo.
echo Install failed. Check your internet connection and try again.
echo If it keeps failing, copy the red text above and send it over.
pause
exit /b 1
