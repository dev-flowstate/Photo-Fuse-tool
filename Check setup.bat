@echo off
title Check setup
cd /d "%~dp0"

rem Find Python. A python-path.txt next to this file (or one folder up) wins,
rem so a Python living somewhere unusual can be pointed at directly. Otherwise
rem "py" is tried first: it is the Windows launcher, lives in C:\Windows, and
rem works even when "Add python.exe to PATH" was never ticked.
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

echo ==============================================================
echo   No Python at all
echo ==============================================================
echo.
echo None of these worked:  py -3    python    py    python3
echo.
echo If Python IS installed, it was installed without ticking
echo "Add python.exe to PATH". Two ways to fix it:
echo.
echo   A) Settings ^> Apps ^> Installed apps ^> Python ^> Modify ^>
echo      Modify ^> tick "Add Python to environment variables".
echo.
echo   B) Or make a file called python-path.txt in this folder,
echo      holding the full path to python.exe on one line, e.g.
echo         D:\Programs\Python311\python.exe
echo.
echo If Python is not installed: https://www.python.org/downloads/
echo (tick "Add python.exe to PATH" on the first screen).
echo.
pause
exit /b 1

:found
echo Using: %PY%
echo.
%PY% check_setup.py
echo.
pause
