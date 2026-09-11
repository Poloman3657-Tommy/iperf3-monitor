@echo off
setlocal
set "PYTHON=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo ERROR: Python environment missing. Follow README.md setup instructions.
    exit /b 2
)
"%PYTHON%" "%~dp0monitor.py" %*
exit /b %errorlevel%
