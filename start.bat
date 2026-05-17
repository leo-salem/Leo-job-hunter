@echo off
REM One-command startup wrapper - calls start.ps1 from a regular cmd window.
REM Usage: double-click this file, or run "start.bat" in any terminal.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
