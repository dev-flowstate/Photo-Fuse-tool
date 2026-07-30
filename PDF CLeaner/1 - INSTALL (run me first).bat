@echo off
title PDF Cleaner - install
cd /d "%~dp0"

echo ======================================================
echo   PDF Cleaner - one-time setup
echo ======================================================
echo.

python --version >nul 2>&1
if errorlevel 1 goto nopython

echo Found Python:
python --version
echo.
echo Installing Pillow, numpy and PyMuPDF...
echo.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto failed

if not exist "..\photofuse.py" goto misplaced

echo.
echo ======================================================
echo   Done. Now double-click "2 - START PDF Cleaner.bat"
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

:misplaced
echo.
echo WARNING: photofuse.py was not found in the folder above this one.
echo.
echo This "pdf cleaner" folder must stay INSIDE the "Photo Fuse tool" folder,
echo because it shares the image-cleaning code with Photo Fuse.
echo.
pause
exit /b 1

:failed
echo.
echo Install failed. Check your internet connection and try again.
echo If it keeps failing, copy the red text above and send it over.
pause
exit /b 1
