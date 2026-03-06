@echo off
REM OpenClaw Gateway Service Installation (Admin Required)
REM Right-click this file and select "Run as administrator"

echo.
echo ============================================================
echo OpenClaw Gateway Service Installation
echo ============================================================
echo.
echo This script will install OpenClaw Gateway as a Windows service.
echo Administrator privileges are required.
echo.

REM Refresh PATH to include npm global bin
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v PATH') do set "USERPATH=%%B"
for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH') do set "SYSPATH=%%B"
set "PATH=%USERPATH%;%SYSPATH%;%APPDATA%\npm;%USERPROFILE%\npm-global"

echo [*] Checking for OpenClaw...
openclaw --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] OpenClaw not found in PATH
    echo Please ensure OpenClaw is installed: npm install -g openclaw
    pause
    exit /b 1
)

echo [OK] OpenClaw found
echo.
echo [*] Installing Gateway service...
openclaw gateway install --force

if errorlevel 1 (
    echo [ERROR] Gateway installation failed
    pause
    exit /b 1
)

echo.
echo [OK] Gateway service installed successfully
echo.
echo [*] Verifying Gateway status...
openclaw gateway status

echo.
echo ============================================================
echo Installation complete!
echo ============================================================
echo.
echo Next steps:
echo 1. Gateway is now running as a Windows service
echo 2. Access OpenClaw at: http://127.0.0.1:18789
echo 3. Your gateway token: d72d7837cb2a6b63c2924e6a328733c316bd17ec171a081a5771ef9f9ce1910b
echo.
pause
