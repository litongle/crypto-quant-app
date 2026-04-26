@echo off
echo ===================================================
echo RSI Layered Extreme Value Tracking Trading System
echo Development Environment Launcher
echo ===================================================
echo.

:: Check if Python is installed
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.8+ and try again.
    pause
    exit /b 1
)

:: Check if Node.js is installed
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found. Please install Node.js and try again.
    pause
    exit /b 1
)

echo [INFO] Starting development environment...
echo.

:: Create logs directory if it doesn't exist
if not exist logs mkdir logs

:: Start the backend server in a new window
echo [INFO] Starting backend server...
start "RSI Tracker Backend" cmd /c "python run_dev.py"

:: Wait a moment for the backend to initialize
timeout /t 3 /nobreak > nul

:: Start the frontend development server
echo [INFO] Starting frontend development server...
cd frontend
start "RSI Tracker Frontend" cmd /c "npm run dev"

echo.
echo [SUCCESS] Development environment started!
echo.
echo Backend API: http://localhost:8080/api/docs
echo Frontend: http://localhost:3000
echo.
echo Press any key to stop all servers and exit...
pause

:: Kill all related processes when exiting
taskkill /f /fi "WINDOWTITLE eq RSI Tracker Backend*" > nul 2> nul
taskkill /f /fi "WINDOWTITLE eq RSI Tracker Frontend*" > nul 2> nul

echo [INFO] Development environment stopped.
exit /b 0
