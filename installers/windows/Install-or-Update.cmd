@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-or-update.ps1" %*
if errorlevel 1 pause
