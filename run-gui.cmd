@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0gui.py" %*
) else if exist "%~dp0..\.venv\Scripts\python.exe" (
    "%~dp0..\.venv\Scripts\python.exe" "%~dp0gui.py" %*
) else (
    python "%~dp0gui.py" %*
)
if errorlevel 1 (
    echo GUI failed to start. See GUI-README.md for setup instructions.
    pause
    exit /b 1
)
