@echo off
:: 주의: 메모장에서 [다른 이름으로 저장]할 때 인코딩을 반드시 [ANSI]로 선택하세요!

:: 현재 배치파일이 있는 폴더 경로를 자동으로 인식하여 파일명을 붙입니다.
set "progPath=%~dp0mattermost_toast.exe"
set "progName=mattermost_toast.exe"
set "regName=MattermostToastAutoRun"

:MENU
cls
echo ===========================================
echo    Mattermost Toast 통합 관리 도구
echo ===========================================
echo    현재 파일 위치: "%progPath%"
echo ===========================================
echo  1. 프로그램 시작
echo  2. 프로그램 종료 (프로세스 강제 종료)
echo  3. 프로그램 재시작
echo  4. 윈도우 시작 시 자동 실행 등록
echo  5. 윈도우 시작 시 자동 실행 삭제
echo  6. 종료
echo ===========================================
set /p choice="원하시는 번호를 입력하고 엔터를 누르세요 (1-6): "

if "%choice%"=="1" goto START_PROG
if "%choice%"=="2" goto STOP_PROG
if "%choice%"=="3" goto RESTART_PROG
if "%choice%"=="4" goto REG_STARTUP
if "%choice%"=="5" goto DEL_STARTUP
if "%choice%"=="6" exit
goto MENU

:START_PROG
echo 프로그램을 실행합니다...
if exist "%progPath%" (
    start "" "%progPath%"
) else (
    echo [오류] 파일을 찾을 수 없습니다. 경로를 확인해주세요.
    pause
)
goto MENU

:STOP_PROG
echo 프로그램을 종료하는 중...
taskkill /f /im "%progName%" /t 2>nul
if %errorlevel% equ 0 (
    echo 성공적으로 종료되었습니다.
) else (
    echo 실행 중인 프로그램을 찾을 수 없습니다.
)
timeout /t 2 >nul
goto MENU

:RESTART_PROG
echo 프로그램을 재시작합니다...
taskkill /f /im "%progName%" /t 2>nul
timeout /t 1 >nul
if exist "%progPath%" (
    start "" "%progPath%"
)
goto MENU

:REG_STARTUP
echo 윈도우 시작 프로그램에 등록 중...
:: 경로에 공백이 있어도 인식되도록 따옴표 처리(\")가 포함되어 있습니다.
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%regName%" /t REG_SZ /d "\"%progPath%\"" /f
if %errorlevel% equ 0 (
    echo [성공] 이제 부팅 시 프로그램이 자동 실행됩니다.
) else (
    echo [실패] 관리자 권한으로 실행해 보시기 바랍니다.
)
pause
goto MENU

:DEL_STARTUP
echo 자동 실행 항목을 삭제 중...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%regName%" /f
if %errorlevel% equ 0 (
    echo [성공] 자동 실행 목록에서 삭제되었습니다.
) else (
    echo [알림] 등록된 항목이 없거나 삭제에 실패했습니다.
)
pause
goto MENU