@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run.py %*
    goto :end
)

where python >nul 2>nul
if errorlevel 1 (
    echo [ TUPPER ] Python not found. Install Python 3.12 first.
    pause
    exit /b 1
)

python run.py %*

:end
if errorlevel 1 (
    echo.
    echo [ TUPPER ] exited with an error. See the traceback above.
    pause
)
