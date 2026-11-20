@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo This script requires administrator privileges. Requesting elevation...
    set "SCRIPT_PATH=%~f0"
    powershell -NoProfile -Command "Start-Process -FilePath $env:COMSPEC -ArgumentList ('/c \"\"' + $env:SCRIPT_PATH + '\"\"') -Verb RunAs"
    exit /b
)

rem --- Read configuration from service.env if present ---
set "PAUSE_ON_ERROR=%DENODO_AI_SDK_SERVICE_PAUSE_ON_ERROR%"

if exist "%~dp0service.env" (
    for /f "usebackq eol=# tokens=1* delims==" %%A in ("%~dp0service.env") do (
        for /f "tokens=* delims= " %%K in ("%%A") do set "KEY=%%K"
        for /f "tokens=* delims= " %%V in ("%%B") do (
            if /i "!KEY!"=="DENODO_AI_SDK_SERVICE_PAUSE_ON_ERROR" set "PAUSE_ON_ERROR=%%V"
        )
    )
)

if defined PAUSE_ON_ERROR set "PAUSE_ON_ERROR=%PAUSE_ON_ERROR:"=%"

sc query DenodoAISDK >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Service 'DenodoAISDK' is not installed.
    goto :fail
)

sc query DenodoAISDK | findstr /i "STOPPED" >nul
if %errorlevel% equ 0 (
    echo Service 'DenodoAISDK' is already stopped.
    exit /b 0
)

echo Stopping Denodo AI SDK service...
net stop DenodoAISDK
if %errorlevel% neq 0 (
    echo [ERROR] Could not stop the service. It may already be stopped or not installed.
    echo Check <AI_SDK_DATA_DIR>\windows_service\logs\service_*.log and Windows Event Viewer ^(Application^).
    goto :fail
)

echo Service stopped successfully.
exit /b 0

:fail
echo.
if "%PAUSE_ON_ERROR%"=="1" (
    pause
)
exit /b 1
