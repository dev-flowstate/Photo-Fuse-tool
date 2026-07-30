@echo off
title Photo Fuse
cd /d "%~dp0"
python photofuse_gui.py %*
if errorlevel 1 (
  echo.
  echo Photo Fuse could not start.
  echo If it says a module is missing, run "1 - INSTALL (run me first).bat" first.
  echo.
  pause
)
