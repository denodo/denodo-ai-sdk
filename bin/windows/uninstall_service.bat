@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem --- 1. Require administrator privileges (secure elevation) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo This script requires administrator privileges. Requesting elevation...
    set "SCRIPT_PATH=%~f0"
    powershell -NoProfile -Command "Start-Process -FilePath $env:COMSPEC -ArgumentList ('/c \"\"' + $env:SCRIPT_PATH + '\"\"') -Verb RunAs"
    exit /b
)

rem --- 2. Check if service is installed ---
sc query DenodoAISDK >nul 2>&1
if %errorlevel% neq 0 (
    echo Service 'DenodoAISDK' is not installed.
    exit /b 0
)

rem --- 3. Stop service only if currently running ---
sc query DenodoAISDK | findstr /i "RUNNING" >nul
if %errorlevel% equ 0 (
    echo Stopping service...
    net stop DenodoAISDK >nul 2>&1
)

rem --- 4. Read configuration (inherit from environment, override with service.env) ---
set "CUSTOM_VENV_DIR=%DENODO_AI_SDK_SERVICE_VENV_DIR%"
set "PAUSE_ON_ERROR=%DENODO_AI_SDK_SERVICE_PAUSE_ON_ERROR%"

if exist "%~dp0service.env" (
    for /f "usebackq eol=# tokens=1* delims==" %%A in ("%~dp0service.env") do (
        for /f "tokens=* delims= " %%K in ("%%A") do set "KEY=%%K"
        for /f "tokens=* delims= " %%V in ("%%B") do (
            if /i "!KEY!"=="DENODO_AI_SDK_SERVICE_VENV_DIR"        set "CUSTOM_VENV_DIR=%%V"
            if /i "!KEY!"=="DENODO_AI_SDK_SERVICE_PAUSE_ON_ERROR" set "PAUSE_ON_ERROR=%%V"
        )
    )
)

rem Strip quotes
if defined CUSTOM_VENV_DIR set "CUSTOM_VENV_DIR=%CUSTOM_VENV_DIR:"=%"
if defined PAUSE_ON_ERROR  set "PAUSE_ON_ERROR=%PAUSE_ON_ERROR:"=%"

rem --- 5. Locate virtual environment ---
set "VENV_DIR="
if defined CUSTOM_VENV_DIR (
    if exist "%CUSTOM_VENV_DIR%\Scripts\python.exe" set "VENV_DIR=%CUSTOM_VENV_DIR%"
    if exist "%~dp0..\..\%CUSTOM_VENV_DIR%\Scripts\python.exe" set "VENV_DIR=%~dp0..\..\%CUSTOM_VENV_DIR%"
)

if "%VENV_DIR%"=="" (
    if exist "%~dp0..\..\venv\Scripts\python.exe" set "VENV_DIR=%~dp0..\..\venv"
    if exist "%~dp0..\..\.venv\Scripts\python.exe" set "VENV_DIR=%~dp0..\..\.venv"
)

rem --- 6. Remove Windows Service ---
echo Removing service...
if not "%VENV_DIR%"=="" (
    "%VENV_DIR%\Scripts\python.exe" "%~dp0service.py" remove && goto :success
)

echo Attempting removal via Windows Service Control Manager...
sc delete DenodoAISDK
if %errorlevel% neq 0 goto :fail

:success
echo.
echo Service DenodoAISDK removed successfully.
exit /b 0

:fail
echo.
echo [ERROR] Uninstallation failed. Check Windows Event Viewer ^(Application^).
if "%PAUSE_ON_ERROR%"=="1" (
    echo.
    pause
)
exit /b 1
