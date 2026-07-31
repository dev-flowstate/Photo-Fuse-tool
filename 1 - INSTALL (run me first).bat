@echo off
title Photo Fuse - install
cd /d "%~dp0"

echo ======================================================
echo   Photo Fuse - one-time setup
echo ======================================================
echo.

rem Find Python. A python-path.txt next to this file (or one folder up) wins,
rem so a Python living somewhere unusual can be pointed at directly. Otherwise
rem "py" is tried first: it is the Windows launcher, lives in C:\Windows, and
rem works even when "Add python.exe to PATH" was never ticked. Plain "python"
rem is tried after it because it can hit the Microsoft Store placeholder.
set "PY="
if exist "%~dp0python-path.txt" for /f "usebackq delims=" %%L in ("%~dp0python-path.txt") do if not defined PY if exist "%%~L" set PY="%%~L"
if exist "%~dp0..\python-path.txt" for /f "usebackq delims=" %%L in ("%~dp0..\python-path.txt") do if not defined PY if exist "%%~L" set PY="%%~L"
if defined PY goto found
py -3 --version >nul 2>&1
if not errorlevel 1 (set "PY=py -3" & goto found)
python --version >nul 2>&1
if not errorlevel 1 (set "PY=python" & goto found)
py --version >nul 2>&1
if not errorlevel 1 (set "PY=py" & goto found)
python3 --version >nul 2>&1
if not errorlevel 1 (set "PY=python3" & goto found)
goto nopython

:found
echo Found Python using "%PY%":
%PY% --version
%PY% -c "import sys; print('  at', sys.executable)"
echo.
echo Installing Pillow, numpy and openpyxl into THAT Python...
echo.
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo.
echo ======================================================
echo   Done. Now double-click "2 - START Photo Fuse.bat"
echo ======================================================
echo.
echo (If anything still complains a library is missing, run
echo  "Check setup.bat" - it shows exactly what is going on.)
pause
exit /b 0

:nopython
echo Python was not found by any of these commands:
echo     py -3      python      py      python3
echo.
echo If you are SURE Python is already installed, it was almost certainly
echo installed without "Add python.exe to PATH". Two ways to fix it:
echo.
echo   A) Settings ^> Apps ^> Installed apps ^> Python ^> Modify ^> Modify ^>
echo      tick "Add Python to environment variables", finish, run this again.
echo.
echo   B) Or make a file called python-path.txt in this folder holding the
echo      full path to your python.exe on one line, for example:
echo         D:\Programs\Python311\python.exe
echo      Every one of these .bat files will then use exactly that Python.
echo.
echo If Python is genuinely not installed:
echo.
echo   1. Go to https://www.python.org/downloads/
echo   2. Download Python 3.10 or newer.
echo   3. IMPORTANT: tick "Add python.exe to PATH" on the first install screen.
echo   4. Finish the install, then run this file again.
echo.
echo Note: the "Python" from the Microsoft Store sometimes does not register
echo properly. The installer from python.org is the reliable one.
echo.
pause
exit /b 1

:failed
echo.
echo Install failed. Check your internet connection and try again.
echo If it keeps failing, run "Check setup.bat" and send over what it says.
pause
exit /b 1
