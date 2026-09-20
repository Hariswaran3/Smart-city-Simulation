@echo off
echo 🚦 SUMO Live Dashboard
echo =====================

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found! Please install Python 3.7+
    pause
    exit /b 1
)

REM Run the dashboard
python run_dashboard.py

pause