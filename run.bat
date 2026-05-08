@echo off
REM ===========================================================
REM Mattermost Windows Toast 실행 스크립트
REM ===========================================================
cd /d "%~dp0"

REM 가상환경이 있으면 활성화
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

REM 콘솔 창 없이 실행하고 싶다면 pythonw.exe 로 변경
python mattermost_toast.py
pause
