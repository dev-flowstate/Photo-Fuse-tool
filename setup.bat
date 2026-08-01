@echo off
setlocal enabledelayedexpansion
title Photo Fuse + PDF Cleaner - setup
cd /d "%~dp0"

echo ==============================================================
echo    Photo Fuse + PDF Cleaner - setup
echo ==============================================================
echo.
echo This gets everything ready. Leave it running - it can take a
echo few minutes the first time.
echo.

rem ==============================================================
rem  1. Find Python
rem ==============================================================
call :findpython
if defined PY goto haspython

echo --------------------------------------------------------------
echo   Python is not on this computer yet
echo --------------------------------------------------------------
echo.
echo Downloading the official installer from python.org (about 27 MB)
echo and installing it for your account only, so no administrator
echo password is needed.
echo.

set "PYVER=3.12.10"
set "ARCH=amd64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=arm64"
if /i "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "ARCH=arm64"
set "PYURL=https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-%ARCH%.exe"
set "PYSETUP=%TEMP%\python-%PYVER%-%ARCH%.exe"

echo From: %PYURL%
echo.
if exist "%PYSETUP%" del "%PYSETUP%" >nul 2>&1

where curl.exe >nul 2>&1
if errorlevel 1 goto useps
curl.exe -L --fail --progress-bar -o "%PYSETUP%" "%PYURL%"
if not errorlevel 1 goto downloaded

:useps
echo (using PowerShell to download instead)
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%PYURL%' -OutFile '%PYSETUP%' -UseBasicParsing } catch { exit 1 }"
if errorlevel 1 goto downloadfailed

:downloaded
if not exist "%PYSETUP%" goto downloadfailed
echo.
echo Installing Python %PYVER%. A progress window will appear - let it
echo finish, it closes by itself.
echo.
"%PYSETUP%" /passive InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
del "%PYSETUP%" >nul 2>&1
echo.

call :findpython
if defined PY goto haspython
rem PATH is stale inside this window, so look where a per-user install lands.
for %%V in (312 313 314 311) do (
    if not defined PY if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" set PY="%LocalAppData%\Programs\Python\Python%%V\python.exe"
)
if defined PY goto haspython
goto installfailed

rem ==============================================================
rem  2. Install the libraries
rem ==============================================================
:haspython
echo --------------------------------------------------------------
echo   Using this Python
echo --------------------------------------------------------------
%PY% --version
%PY% -c "import sys; print('   at', sys.executable)"
echo.
echo --------------------------------------------------------------
echo   Installing the libraries
echo --------------------------------------------------------------
echo.
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto pipfailed
if exist "PDF CLeaner\requirements.txt" %PY% -m pip install -r "PDF CLeaner\requirements.txt"

rem ==============================================================
rem  3. Check it actually worked
rem ==============================================================
echo.
echo --------------------------------------------------------------
echo   Checking
echo --------------------------------------------------------------
echo.
%PY% check_setup.py --fix
rem 2 means a library is installed but Windows cannot load it - that is the
rem Visual C++ runtime missing, which pip can do nothing about.
if errorlevel 2 goto vcredist
if errorlevel 1 goto checkfailed
goto alldone

rem ==============================================================
rem  Missing Visual C++ runtime
rem ==============================================================
:vcredist
echo.
echo --------------------------------------------------------------
echo   One more Windows piece is needed
echo --------------------------------------------------------------
echo.
echo PyMuPDF is installed correctly, but it is partly written in C
echo and needs Microsoft's Visual C++ runtime, which this PC does
echo not have yet. Plenty of programs need it; it is a normal part
echo of Windows that simply is not always present.
echo.
echo Downloading it from Microsoft (about 25 MB).
echo Windows will ask permission to install it - click YES.
echo.

set "VCARCH=x64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "VCARCH=arm64"
if /i "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "VCARCH=arm64"
set "VCURL=https://aka.ms/vs/17/release/vc_redist.%VCARCH%.exe"
set "VCEXE=%TEMP%\vc_redist.%VCARCH%.exe"
if exist "%VCEXE%" del "%VCEXE%" >nul 2>&1

where curl.exe >nul 2>&1
if errorlevel 1 goto vcps
curl.exe -L --fail --progress-bar -o "%VCEXE%" "%VCURL%"
goto vcgot

:vcps
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%VCURL%' -OutFile '%VCEXE%' -UseBasicParsing } catch { exit 1 }"

:vcgot
if not exist "%VCEXE%" goto vcfailed
echo.
echo Installing the Visual C++ runtime...
"%VCEXE%" /install /passive /norestart
set "VCCODE=%errorlevel%"
del "%VCEXE%" >nul 2>&1
if "%VCCODE%"=="1223" goto vccancelled

echo.
echo Checking again...
echo.
%PY% check_setup.py --fix
if errorlevel 2 goto vcstillbad
if errorlevel 1 goto checkfailed
if "%VCCODE%"=="3010" goto vcrestart
goto alldone

:alldone
echo.
echo ==============================================================
echo   All done - everything is installed.
echo ==============================================================
echo.
echo Now double-click:
echo    "2 - START Photo Fuse.bat"          to name and fuse images
echo    "PDF CLeaner\2 - START PDF Cleaner.bat"   to clean a paper
echo.
pause
exit /b 0

:vcrestart
echo.
echo ==============================================================
echo   All done - please restart the computer
echo ==============================================================
echo.
echo Windows wants a restart to finish setting up the runtime.
echo After restarting, everything is ready to use.
echo.
pause
exit /b 0

:vccancelled
echo.
echo The Visual C++ runtime was not installed - the permission
echo prompt was declined.
echo.
echo PDF Cleaner cannot work without it. Photo Fuse is unaffected
echo and works right now.
echo.
echo To finish later, run setup.bat again and click YES, or install
echo it by hand from:
echo    %VCURL%
echo.
pause
exit /b 1

:vcstillbad
echo.
echo The runtime installed but the library still will not load.
echo Please RESTART the computer and run setup.bat once more -
echo that resolves it in almost every case.
echo.
pause
exit /b 1

:vcfailed
echo.
echo Could not download the Visual C++ runtime.
echo.
echo Install it by hand from this address, then restart:
echo    %VCURL%
echo.
echo Photo Fuse works without it - this only affects PDF Cleaner.
echo.
pause
exit /b 1

rem ==============================================================
rem  Problems
rem ==============================================================
:downloadfailed
echo.
echo Could not download Python.
echo.
echo Usually this is no internet, or a school/office firewall.
echo Install it by hand instead:
echo.
echo   1. Go to  https://www.python.org/downloads/
echo   2. Click the big yellow "Download Python" button.
echo   3. Run it and TICK "Add python.exe to PATH" on the first screen.
echo   4. Then run this setup.bat again.
echo.
pause
exit /b 1

:installfailed
echo.
echo Python was installed but this window cannot see it yet.
echo.
echo Close this window and run setup.bat again - that is usually all
echo it needs. If it still says this, restart the computer and try
echo once more.
echo.
pause
exit /b 1

:pipfailed
echo.
echo The libraries could not be installed.
echo.
echo Run "Check setup.bat" - it retries and explains what the error
echo means. If you are behind a school firewall, try this line:
echo.
echo    %PY% -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
echo.
pause
exit /b 1

:checkfailed
echo.
echo Something is still missing - the check above says what.
echo Run "Check setup.bat" for more detail.
echo.
pause
exit /b 1

rem ==============================================================
rem  Locate Python: an explicit python-path.txt wins, otherwise try
rem  the launcher first ("py" lives in C:\Windows so it works even
rem  when PATH was never set up), then plain python.
rem ==============================================================
:findpython
set "PY="
if exist "%~dp0python-path.txt" for /f "usebackq delims=" %%L in ("%~dp0python-path.txt") do if not defined PY if exist "%%~L" set PY="%%~L"
if defined PY goto :eof
py -3 --version >nul 2>&1
if not errorlevel 1 (set "PY=py -3" & goto :eof)
python --version >nul 2>&1
if not errorlevel 1 (set "PY=python" & goto :eof)
py --version >nul 2>&1
if not errorlevel 1 (set "PY=py" & goto :eof)
python3 --version >nul 2>&1
if not errorlevel 1 (set "PY=python3" & goto :eof)
goto :eof
