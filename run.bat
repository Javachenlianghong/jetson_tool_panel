@echo off
setlocal

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0app.py"
) else (
    python "%~dp0app.py"
)

if errorlevel 1 (
    echo.
    echo Jetson Tool Panel failed to start.
    echo Make sure Python and PyQt5 are installed:
    echo   py -3 -m pip install -r "%~dp0requirements.txt"
    pause
)
