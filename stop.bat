@echo off
REM Stop all job-hunter containers. Data is preserved.
REM Usage: double-click this file, or run "stop.bat" in any terminal.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop.ps1"
