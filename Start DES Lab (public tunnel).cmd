@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ---------------------------------------------------------------------------
rem  Starts DES Lab and opens a public Cloudflare quick tunnel.
rem  Keep this window open while you want to share the link.
rem  Closing the window (or shutting the PC down) ends the public address.
rem  The address changes every time you start it again.
rem ---------------------------------------------------------------------------

where "%LOCALAPPDATA%\cloudflared\cloudflared.exe" >nul 2>nul
if not exist "%LOCALAPPDATA%\cloudflared\cloudflared.exe" (
    echo cloudflared is not installed yet.
    echo Downloading it once into %LOCALAPPDATA%\cloudflared ...
    powershell -NoProfile -Command "New-Item -ItemType Directory -Force -Path (Join-Path $env:LOCALAPPDATA 'cloudflared') | Out-Null; Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile (Join-Path $env:LOCALAPPDATA 'cloudflared\cloudflared.exe') -UseBasicParsing"
    if errorlevel 1 (
        echo Download failed. Check the internet connection and try again.
        pause
        exit /b 1
    )
)

echo Starting the local app first ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start.ps1"
if errorlevel 1 (
    echo The app did not start. See .runtime\stderr.log
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Opening a public tunnel. Look for the line below:
echo.
echo      https://something-random.trycloudflare.com
echo.
echo  That is the link you can send to someone. Keep this window
echo  open; closing it takes the link offline.
echo ============================================================
echo.

"%LOCALAPPDATA%\cloudflared\cloudflared.exe" tunnel --url http://127.0.0.1:8514 --no-autoupdate

echo.
echo Tunnel closed - the public link no longer works.
pause
