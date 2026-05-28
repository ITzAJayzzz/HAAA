@echo off
echo.
echo  GlobalTalk Setup (Windows)
echo ============================
echo.

cd /d "%~dp0backend"

echo [1/3] Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    pause
    exit /b 1
)

echo [2/3] Installing packages...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed
    pause
    exit /b 1
)

echo [3/3] Copying .env...
if not exist .env (
    copy .env.example .env
    echo Created backend\.env — add your Firebase key path
)

echo.
echo  Setup complete!
echo.
echo  Next steps:
echo   1. Drop serviceAccountKey.json into the backend\ folder
echo   2. Run:  run.bat
echo.
pause
