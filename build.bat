@echo off
chcp 65001 > nul
REM ===========================================================
REM Mattermost Windows Toast - one-shot build script
REM ===========================================================
REM 더블클릭 한 번으로:
REM   1) .venv 가 없으면 만든다
REM   2) requirements.txt + pyinstaller 를 설치한다
REM   3) PyInstaller 로 dist\mattermost_toast.exe 를 만든다
REM 결과물은 dist\mattermost_toast.exe 하나. config.yaml 을 옆에 두고 실행.
REM ===========================================================
setlocal
cd /d "%~dp0"

echo === Mattermost Toast build ===

REM 1) venv
if not exist ".venv\Scripts\activate.bat" (
    echo [build] .venv 생성 중...
    python -m venv .venv
    if errorlevel 1 goto :err
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :err

REM 2) deps
echo [build] pip / 의존성 업데이트...
python -m pip install --upgrade pip
if errorlevel 1 goto :err
pip install -r requirements.txt
if errorlevel 1 goto :err
pip install pyinstaller
if errorlevel 1 goto :err

REM 3) 이전 빌드 산출물 정리
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist mattermost_toast.spec del mattermost_toast.spec

REM 4) PyInstaller
echo [build] PyInstaller 실행...
pyinstaller ^
  --noconfirm ^
  --onefile ^
  --noconsole ^
  --name mattermost_toast ^
  --collect-all windows_toasts ^
  --collect-submodules winsdk ^
  --hidden-import websocket ^
  mattermost_toast.py
if errorlevel 1 goto :err

if not exist "dist\mattermost_toast.exe" goto :err

echo.
echo === 빌드 성공 ===
echo  결과물 : dist\mattermost_toast.exe
echo.
echo 사용법:
echo   1) dist\mattermost_toast.exe 와 config.yaml 을 같은 폴더에 둡니다.
echo   2) config.yaml 에 server.url / server.token 을 채웁니다.
echo   3) mattermost_toast.exe 를 더블클릭하면 백그라운드로 실행됩니다.
echo.
pause
endlocal
exit /b 0

:err
echo.
echo === 빌드 실패 ===
echo 위 메시지를 확인하세요.
pause
endlocal
exit /b 1
