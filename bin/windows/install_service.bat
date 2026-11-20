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

rem --- 2. Read configuration (inherit from environment, override with service.env) ---
set "CUSTOM_VENV_DIR=%DENODO_AI_SDK_SERVICE_VENV_DIR%"
set "STARTUP_TYPE=%DENODO_AI_SDK_SERVICE_STARTUP%"
set "PAUSE_ON_ERROR=%DENODO_AI_SDK_SERVICE_PAUSE_ON_ERROR%"

if exist "%~dp0service.env" (
    for /f "usebackq eol=# tokens=1* delims==" %%A in ("%~dp0service.env") do (
        for /f "tokens=* delims= " %%K in ("%%A") do set "KEY=%%K"
        for /f "tokens=* delims= " %%V in ("%%B") do (
            if /i "!KEY!"=="DENODO_AI_SDK_SERVICE_VENV_DIR" set "CUSTOM_VENV_DIR=%%V"
            if /i "!KEY!"=="DENODO_AI_SDK_SERVICE_STARTUP" set "STARTUP_TYPE=%%V"
            if /i "!KEY!"=="DENODO_AI_SDK_SERVICE_PAUSE_ON_ERROR" set "PAUSE_ON_ERROR=%%V"
        )
    )
)

rem Strip quotes
if defined CUSTOM_VENV_DIR set "CUSTOM_VENV_DIR=%CUSTOM_VENV_DIR:"=%"
if defined STARTUP_TYPE set "STARTUP_TYPE=%STARTUP_TYPE:"=%"
if defined PAUSE_ON_ERROR set "PAUSE_ON_ERROR=%PAUSE_ON_ERROR:"=%"

rem Whitelist validation to prevent injection
set "VALID_STARTUP=0"
if /i "%STARTUP_TYPE%"=="auto" set "VALID_STARTUP=1"
if /i "%STARTUP_TYPE%"=="manual" set "VALID_STARTUP=1"
if /i "%STARTUP_TYPE%"=="disabled" set "VALID_STARTUP=1"
if /i "%STARTUP_TYPE%"=="delayed" set "VALID_STARTUP=1"

if "%VALID_STARTUP%"=="0" (
    set "STARTUP_TYPE=manual"
)

rem --- 3. Locate virtual environment ---
set "VENV_DIR="
if defined CUSTOM_VENV_DIR (
    if exist "%CUSTOM_VENV_DIR%\Scripts\python.exe" set "VENV_DIR=%CUSTOM_VENV_DIR%"
    if exist "%~dp0..\..\%CUSTOM_VENV_DIR%\Scripts\python.exe" set "VENV_DIR=%~dp0..\..\%CUSTOM_VENV_DIR%"
)

if "%VENV_DIR%"=="" (
    if exist "%~dp0..\..\venv\Scripts\python.exe" set "VENV_DIR=%~dp0..\..\venv"
    if exist "%~dp0..\..\.venv\Scripts\python.exe" set "VENV_DIR=%~dp0..\..\.venv"
)

if "%VENV_DIR%"=="" (
    echo [ERROR] Virtual environment not found.
    goto :fail
)

set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

rem --- 4. Install Windows Service ---
echo Installing service (startup mode: %STARTUP_TYPE%)...
"%PYTHON_EXE%" "%~dp0service.py" --startup "%STARTUP_TYPE%" install
if %errorlevel% neq 0 goto :fail

rem --- 5. Start Windows Service with polling ---
if /i "%STARTUP_TYPE%"=="disabled" goto :done

echo Starting service...
net start DenodoAISDK >nul 2>&1

echo Waiting for service to report RUNNING...
set "SERVICE_RUNNING=0"

for /l %%I in (1,1,15) do (
    sc query DenodoAISDK | findstr /i "RUNNING" >nul
    if not errorlevel 1 (
        set "SERVICE_RUNNING=1"
        goto :service_ready
    )
    timeout /t 1 /nobreak >nul
)

:service_ready
if "!SERVICE_RUNNING!"=="0" (
    echo [ERROR] The service did not reach RUNNING status within 15 seconds.
    echo Check the Windows Event Viewer ^(Application^) and <AI_SDK_DATA_DIR>\windows_service\logs\service_*.log
    goto :fail
)

:done
echo.
echo ===================================================
echo Denodo AI SDK Service installed successfully!
echo ===================================================
exit /b 0

:fail
echo.
echo [ERROR] Installation failed.
if "%PAUSE_ON_ERROR%"=="1" (
    echo.
    pause
)
exit /b 1
