@echo off
REM ===========================================================
REM Mattermost Windows Toast launcher
REM ===========================================================
cd /d "%~dp0"

REM Activate venv if it exists, otherwise fall back to global python
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo [run.bat] .venv not found. Create one with:
    echo     python -m venv .venv
    echo     .venv\Scripts\activate
    echo     pip install -r requirements.txt
    echo.
)

REM To run without a console window, replace 'python' with 'pythonw'
python mattermost_toast.py
pause
