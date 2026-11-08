@echo off
rem Starts the Kuku Promo Studio review app on http://localhost:3000
rem (needs Node.js 18+; the Python environment is only needed for run_all.py, not for the app)
cd /d "%~dp0"
title Kuku Promo Studio

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js / npm was not found. Install Node.js 18 or newer from https://nodejs.org and run this again.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo First run: installing the app's packages, this takes a minute...
    call npm --prefix frontend install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        pause
        exit /b 1
    )
)

echo.
echo Kuku Promo Studio is starting on http://localhost:3000
echo The AI model comes from your .env (or use the "AI Model" button in the app).
echo Close this window to stop the app.
echo.
start "" /b cmd /c "timeout /t 4 /nobreak >nul & start "" http://localhost:3000"
call npm --prefix frontend run dev
pause
