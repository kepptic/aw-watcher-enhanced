@echo off
REM ============================================================================
REM ActivityWatch Enhanced Watcher - Windows Installer
REM ============================================================================
REM This script installs aw-watcher-enhanced and optionally sets it up as a
REM Windows service for automatic startup.
REM
REM Run as Administrator for service installation.
REM ============================================================================

echo.
echo ============================================================
echo   ActivityWatch Enhanced Watcher - Installer
echo ============================================================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo WARNING: Not running as Administrator.
    echo Some features like Windows Service may not install correctly.
    echo.
    echo Right-click this script and select "Run as administrator"
    echo for full installation.
    echo.
    pause
)

REM Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

echo Found Python:
python --version
echo.

REM Get script directory
set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."

echo Project directory: %PROJECT_DIR%
echo.

REM Create virtual environment (optional)
set /p CREATE_VENV="Create virtual environment? (y/n): "
if /i "%CREATE_VENV%"=="y" (
    echo Creating virtual environment...
    python -m venv "%PROJECT_DIR%\venv"
    call "%PROJECT_DIR%\venv\Scripts\activate.bat"
    echo Virtual environment created and activated.
    echo.
)

REM Install package
echo Installing aw-watcher-enhanced...
pip install -e "%PROJECT_DIR%[windows]"
if %errorlevel% neq 0 (
    echo ERROR: Failed to install package.
    pause
    exit /b 1
)
echo.

REM Install pywin32 for service support
echo Installing Windows service support...
pip install pywin32
python -m pywin32_postinstall -install >nul 2>&1
echo.

REM Check if ActivityWatch server is running
echo Checking ActivityWatch server...
curl -s http://localhost:5600/api/0/info >nul 2>&1
if %errorlevel% neq 0 (
    echo WARNING: ActivityWatch server is not running.
    echo Make sure to start ActivityWatch before using this watcher.
) else (
    echo ActivityWatch server is running.
)
echo.

REM Ask about service installation
set /p INSTALL_SERVICE="Install as Windows Service (auto-start)? (y/n): "
if /i "%INSTALL_SERVICE%"=="y" (
    echo.
    echo Installing Windows Service...
    python "%SCRIPT_DIR%windows_service.py" install
    if %errorlevel% neq 0 (
        echo WARNING: Service installation may have failed.
        echo You can still run manually with: aw-watcher-enhanced
    ) else (
        echo.
        set /p START_SERVICE="Start service now? (y/n): "
        if /i "%START_SERVICE%"=="y" (
            python "%SCRIPT_DIR%windows_service.py" start
        )
    )
)
echo.

REM Create desktop shortcut (optional)
set /p CREATE_SHORTCUT="Create desktop shortcut? (y/n): "
if /i "%CREATE_SHORTCUT%"=="y" (
    echo Creating desktop shortcut...
    powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\AW Watcher Enhanced.lnk'); $s.TargetPath = 'pythonw'; $s.Arguments = '-m aw_watcher_enhanced'; $s.WorkingDirectory = '%PROJECT_DIR%'; $s.Description = 'ActivityWatch Enhanced Watcher'; $s.Save()"
    echo Desktop shortcut created.
)
echo.

REM Create Start Menu shortcut (optional)
set /p CREATE_STARTMENU="Create Start Menu shortcut? (y/n): "
if /i "%CREATE_STARTMENU%"=="y" (
    echo Creating Start Menu shortcut...
    set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
    powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTMENU%\AW Watcher Enhanced.lnk'); $s.TargetPath = 'pythonw'; $s.Arguments = '-m aw_watcher_enhanced'; $s.WorkingDirectory = '%PROJECT_DIR%'; $s.Description = 'ActivityWatch Enhanced Watcher'; $s.Save()"
    echo Start Menu shortcut created.
)
echo.

REM Create startup shortcut (if not using service)
if /i not "%INSTALL_SERVICE%"=="y" (
    set /p CREATE_STARTUP="Add to Windows startup? (y/n): "
    if /i "%CREATE_STARTUP%"=="y" (
        echo Adding to startup...
        set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
        powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%STARTUP%\AW Watcher Enhanced.lnk'); $s.TargetPath = 'pythonw'; $s.Arguments = '-m aw_watcher_enhanced'; $s.WorkingDirectory = '%PROJECT_DIR%'; $s.WindowStyle = 7; $s.Description = 'ActivityWatch Enhanced Watcher'; $s.Save()"
        echo Added to startup folder.
    )
)
echo.

echo ============================================================
echo   Installation Complete!
echo ============================================================
echo.
echo Usage:
echo   - Run manually: aw-watcher-enhanced
echo   - With verbose: aw-watcher-enhanced --verbose
echo   - Without OCR:  aw-watcher-enhanced --no-ocr
echo.
if /i "%INSTALL_SERVICE%"=="y" (
    echo Service commands:
    echo   - Start:   sc start AWWatcherEnhanced
    echo   - Stop:    sc stop AWWatcherEnhanced
    echo   - Status:  sc query AWWatcherEnhanced
    echo   - Remove:  python "%SCRIPT_DIR%windows_service.py" remove
    echo.
)
echo Configuration:
echo   %LOCALAPPDATA%\activitywatch\aw-watcher-enhanced\config.yaml
echo.
echo Logs:
echo   %LOCALAPPDATA%\activitywatch\logs\
echo.

pause
