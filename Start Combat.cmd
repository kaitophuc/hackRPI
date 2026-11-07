@echo off
cd /d "%~dp0"
python play_combat.py %*
if errorlevel 1 pause
