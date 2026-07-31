@echo off
rem Drag a past-paper PDF from Explorer and drop it onto this file.
rem PDF Cleaner opens with that paper already loaded - just press Clean PDF.
title PDF Cleaner
cd /d "%~dp0"

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
echo Run "Check setup.bat" in the folder above this one.
echo.
pause
exit /b 1

:found
%PY% pdfcleaner_gui.py %* 2>"%~dp0error-log.txt"
if not errorlevel 1 goto ok

echo.
echo ==============================================================
echo   PDF Cleaner could not start. The actual error:
echo ==============================================================
echo.
type "%~dp0error-log.txt"
echo.
echo --------------------------------------------------------------
echo Saved as error-log.txt next to this file - send that over if
echo you are stuck. "Check setup.bat" in the folder above fixes
echo most causes by itself.
echo.
pause
exit /b 1

:ok
del "%~dp0error-log.txt" >nul 2>&1
