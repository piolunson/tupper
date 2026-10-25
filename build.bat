@echo off
setlocal
cd /d "%~dp0"

echo [ TUPPER ] build starting
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ 1/5 ] creating venv on Python 3.12
    py -3.12 -m venv .venv 2>nul
    if errorlevel 1 python -m venv .venv
) else (
    echo [ 1/5 ] venv present
)

set PY=.venv\Scripts\python.exe

echo [ 2/5 ] installing dependencies
"%PY%" -m pip install --disable-pip-version-check -q -r requirements-dev.txt
if errorlevel 1 goto :failed

echo [ 3/5 ] running tests
"%PY%" -m pytest -q
if errorlevel 1 goto :failed

echo [ 4/5 ] packaging one-file windowed exe
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name TUPPER ^
    --icon assets\tupper.ico ^
    --add-data "assets;assets" ^
    --paths . ^
    run.py
if errorlevel 1 goto :failed

if not exist "dist\TUPPER.exe" goto :failed

echo.
echo [ 5/5 ] BUILD OK
echo         dist\TUPPER.exe
echo.
exit /b 0

:failed
echo.
echo [ BUILD FAILED ] see the output above.
exit /b 1
