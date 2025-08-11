@echo off
echo Starting My Game Library Dashboard...

:: Navigate to the directory where the script is located
cd /d "%~dp0"

:: Start the Python Flask server
start "Game Dashboard Server" python game_dashboard.py

:: Wait for a few seconds to give the server time to start
timeout /t 5 /nobreak > nul

:: Open the dashboard in the default web browser
start http://127.0.0.1:5000

echo Dashboard is running. You can close this window.
