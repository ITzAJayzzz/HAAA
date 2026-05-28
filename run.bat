@echo off
echo.
echo  Starting GlobalTalk...
echo.

cd /d "%~dp0backend"

if not exist venv (
    echo ERROR: venv not found. Run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
set FLASK_ENV=development

echo  Server starting at http://localhost:5000
echo  Press Ctrl+C to stop
echo.
python app.py
pause
