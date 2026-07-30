@echo off
title PDF Cleaner
cd /d "%~dp0"
python pdfcleaner_gui.py %*
if errorlevel 1 (
  echo.
  echo PDF Cleaner could not start.
  echo If it says a module is missing, run "1 - INSTALL (run me first).bat" first.
  echo.
  pause
)
