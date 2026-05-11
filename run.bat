@echo off
chcp 65001 > nul
REM ===========================================================
REM Mattermost Windows Toast 실행 스크립트
REM ===========================================================
cd /d "%~dp0"

REM .venv 가 있으면 활성화, 없으면 전역 python 사용
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo [run.bat] .venv 를 찾을 수 없습니다. 아래 명령으로 생성하세요:
    echo     python -m venv .venv
    echo     .venv\Scripts\activate
    echo     pip install -r requirements.txt
    echo.
)

REM 콘솔 창 없이 실행하려면 'python' 을 'pythonw' 로 바꾸세요.
python mattermost_toast.py
pause
