@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM ActivityWatch Enhanced Watcher - Windows Uninstaller
REM ============================================================================

echo.
echo ============================================================
echo   ActivityWatch Enhanced Watcher - Uninstaller
echo ============================================================
echo.

set "BINARY_NAME=aw-watcher-enhanced.exe"

REM Stop running instance
echo Stopping watcher...
taskkill /IM "%BINARY_NAME%" /F >nul 2>&1

REM Remove startup task
echo Removing startup task...
schtasks /Delete /TN "AW Watcher Enhanced" /F >nul 2>&1

REM Remove binary from ActivityWatch directory
if exist "%LOCALAPPDATA%\Programs\activitywatch\%BINARY_NAME%" (
    del "%LOCALAPPDATA%\Programs\activitywatch\%BINARY_NAME%"
    echo Removed binary from ActivityWatch directory.
)
if exist "%LOCALAPPDATA%\aw-watcher-enhanced\%BINARY_NAME%" (
    del "%LOCALAPPDATA%\aw-watcher-enhanced\%BINARY_NAME%"
    rmdir "%LOCALAPPDATA%\aw-watcher-enhanced" 2>nul
    echo Removed binary from local directory.
)

REM Remove from aw-qt.toml
set "AW_QT_CONFIG=%LOCALAPPDATA%\activitywatch\activitywatch\aw-qt\aw-qt.toml"
if exist "%AW_QT_CONFIG%" (
    findstr /C:"aw-watcher-enhanced" "%AW_QT_CONFIG%" >nul 2>&1
    if !errorlevel! equ 0 (
        powershell -Command "(Get-Content '%AW_QT_CONFIG%') -replace ', \"aw-watcher-enhanced\"', '' -replace '\"aw-watcher-enhanced\", ', '' -replace '\"aw-watcher-enhanced\"', '' | Set-Content '%AW_QT_CONFIG%'"
        echo Removed from ActivityWatch autostart.
    )
)

echo.
set /p REMOVE_DATA="Remove configuration files? (y/n): "
if /i "%REMOVE_DATA%"=="y" (
    rmdir /s /q "%LOCALAPPDATA%\activitywatch\aw-watcher-enhanced" >nul 2>&1
    echo Configuration removed.
)

echo.
echo ============================================================
echo   Uninstallation Complete!
echo ============================================================
echo.
echo ActivityWatch event data is stored separately and was not removed.
echo.
pause
