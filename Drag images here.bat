@echo off
rem Select the crops of ONE question in Explorer and drag them onto this file.
rem They open in Photo Fuse already loaded, in the order Windows hands them over
rem (check the order in the list, and use Move up / Move down if needed).
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
