@echo off
setlocal EnableExtensions

cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python launcher py.exe was not found.
    echo Install Python, then retry.
    pause
    exit /b 1
)

echo Installing runtime dependencies...
py -3 -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 exit /b 1

echo.
echo Installing build dependencies...
py -3 -m pip install -r "%~dp0requirements-build.txt"
if errorlevel 1 exit /b 1

echo.
echo Building JetsonToolPanel.exe...
py -3 -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --onefile ^
    --name JetsonToolPanel ^
    --distpath "%~dp0dist" ^
    --workpath "%~dp0build\pyinstaller" ^
    --specpath "%~dp0build\pyinstaller" ^
    --add-data "%~dp0scripts;scripts" ^
    "%~dp0app.py"

if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build complete:
echo   %~dp0dist\JetsonToolPanel.exe
pause
