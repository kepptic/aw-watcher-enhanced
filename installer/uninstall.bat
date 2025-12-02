@echo off
REM ============================================================================
REM ActivityWatch Enhanced Watcher - Windows Uninstaller
REM ============================================================================
REM Run as Administrator to remove Windows service.
REM ============================================================================

echo.
echo ============================================================
echo   ActivityWatch Enhanced Watcher - Uninstaller
echo ============================================================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo WARNING: Not running as Administrator.
    echo Service removal may fail.
    echo.
)

set "SCRIPT_DIR=%~dp0"

REM Stop and remove service
echo Stopping service...
sc stop AWWatcherEnhanced >nul 2>&1

echo Removing service...
python "%SCRIPT_DIR%windows_service.py" remove >nul 2>&1
sc delete AWWatcherEnhanced >nul 2>&1
echo.

REM Remove shortcuts
echo Removing shortcuts...

REM Desktop shortcut
if exist "%USERPROFILE%\Desktop\AW Watcher Enhanced.lnk" (
    del "%USERPROFILE%\Desktop\AW Watcher Enhanced.lnk"
    echo Removed desktop shortcut.
)

REM Start Menu shortcut
set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
if exist "%STARTMENU%\AW Watcher Enhanced.lnk" (
    del "%STARTMENU%\AW Watcher Enhanced.lnk"
    echo Removed Start Menu shortcut.
)

REM Startup shortcut
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if exist "%STARTUP%\AW Watcher Enhanced.lnk" (
    del "%STARTUP%\AW Watcher Enhanced.lnk"
    echo Removed startup shortcut.
)

echo.

REM Ask about data removal
set /p REMOVE_DATA="Remove configuration and logs? (y/n): "
if /i "%REMOVE_DATA%"=="y" (
    echo Removing data...
    rmdir /s /q "%LOCALAPPDATA%\activitywatch\aw-watcher-enhanced" >nul 2>&1
    echo Configuration removed.
    echo.
    echo NOTE: ActivityWatch data (events) are stored separately and not removed.
    echo To remove watcher data, delete the bucket in ActivityWatch web UI.
)
echo.

REM Ask about package removal
set /p REMOVE_PACKAGE="Uninstall Python package? (y/n): "
if /i "%REMOVE_PACKAGE%"=="y" (
    echo Uninstalling package...
    pip uninstall -y aw-watcher-enhanced
    echo Package removed.
)
echo.

echo ============================================================
echo   Uninstallation Complete!
echo ============================================================
echo.
echo Note: The virtual environment (if created) was not removed.
echo You can manually delete the 'venv' folder if desired.
echo.

pause
