@echo off
rem PDF Cleaner shares one setup with Photo Fuse, so this just runs it.
rem It installs everything both tools need in one go.
if not exist "%~dp0..\setup.bat" goto misplaced
call "%~dp0..\setup.bat"
exit /b %errorlevel%

:misplaced
echo.
echo setup.bat was not found in the folder above this one.
echo.
echo This "PDF CLeaner" folder must stay INSIDE the "Photo Fuse tool"
echo folder - it shares its code and its setup with Photo Fuse.
echo.
pause
exit /b 1
