@echo off
title Photo Fuse
cd /d "%~dp0"

rem Same Python hunt as the installer, so both always agree on which one to
rem use: python-path.txt if present, otherwise py / python.
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

echo Python was not found.
echo Run "Check setup.bat" - it explains exactly what to do.
echo.
pause
exit /b 1

:found
%PY% photofuse_gui.py %*
if errorlevel 1 (
  echo.
  echo Photo Fuse could not start.
  echo Run "Check setup.bat" to see which Python is being used and what is
  echo missing from it.
  echo.
  pause
)
