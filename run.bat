@echo off
REM ===========================================================
REM Mattermost Windows Toast launcher
REM ===========================================================
cd /d "%~dp0"

REM Activate venv if it exists
if exist ".venv\Scriptsctivate.bat" (
    call ".venv\Scriptsctivate.bat"
)

REM To run without a console window, replace 'python' with 'pythonw'
python mattermost_toast.py
pause
