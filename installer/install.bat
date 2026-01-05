@echo off
setlocal EnableDelayedExpansion
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

REM Detect ActivityWatch installation
set "AW_DIR="
if exist "%LOCALAPPDATA%\Programs\activitywatch\aw-qt.exe" (
    set "AW_DIR=%LOCALAPPDATA%\Programs\activitywatch"
)
if exist "%PROGRAMFILES%\ActivityWatch\aw-qt.exe" (
    set "AW_DIR=%PROGRAMFILES%\ActivityWatch"
)
if defined AW_DIR (
    echo Found ActivityWatch at: %AW_DIR%
) else (
    echo WARNING: ActivityWatch installation not found.
    echo          Tray integration will not be available.
)
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

REM Determine the executable path
set "WATCHER_EXE="
if /i "%CREATE_VENV%"=="y" (
    set "WATCHER_EXE=%PROJECT_DIR%\venv\Scripts\aw-watcher-enhanced.exe"
    set "PYTHONW_EXE=%PROJECT_DIR%\venv\Scripts\pythonw.exe"
) else (
    REM Find exe in Python Scripts folder
    for /f "delims=" %%i in ('python -c "import sys; print(sys.prefix)"') do set "PYTHON_PREFIX=%%i"
    set "WATCHER_EXE=%PYTHON_PREFIX%\Scripts\aw-watcher-enhanced.exe"
    set "PYTHONW_EXE=%PYTHON_PREFIX%\Scripts\pythonw.exe"
)

if exist "%WATCHER_EXE%" (
    echo Found watcher executable: %WATCHER_EXE%
) else (
    echo WARNING: Watcher executable not found at expected location.
)
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

REM ActivityWatch tray integration
if defined AW_DIR (
    if exist "%WATCHER_EXE%" (
        set /p TRAY_INTEGRATE="Add to ActivityWatch tray menu? (y/n): "
        if /i "!TRAY_INTEGRATE!"=="y" (
            echo Copying executable to ActivityWatch directory...
            copy /Y "%WATCHER_EXE%" "%AW_DIR%\aw-watcher-enhanced.exe" >nul
            if !errorlevel! equ 0 (
                echo Tray integration complete.

                REM Add to aw-qt.toml autostart_modules
                set "AW_QT_CONFIG=%LOCALAPPDATA%\activitywatch\activitywatch\aw-qt\aw-qt.toml"
                if exist "!AW_QT_CONFIG!" (
                    echo Configuring automatic startup with ActivityWatch...
                    findstr /C:"aw-watcher-enhanced" "!AW_QT_CONFIG!" >nul 2>&1
                    if !errorlevel! neq 0 (
                        REM aw-watcher-enhanced not in config, add it using PowerShell
                        powershell -Command "(Get-Content '!AW_QT_CONFIG!') -replace 'autostart_modules = \[(.+?)\]', 'autostart_modules = [$1, \"aw-watcher-enhanced\"]' | Set-Content '!AW_QT_CONFIG!'"
                        if !errorlevel! equ 0 (
                            echo Added aw-watcher-enhanced to ActivityWatch autostart.
                        ) else (
                            echo WARNING: Could not update aw-qt.toml automatically.
                            echo Please add "aw-watcher-enhanced" to autostart_modules manually.
                        )
                    ) else (
                        echo aw-watcher-enhanced already in ActivityWatch autostart config.
                    )
                ) else (
                    REM Config doesn't exist, create it
                    echo Creating aw-qt.toml with autostart configuration...
                    mkdir "%LOCALAPPDATA%\activitywatch\activitywatch\aw-qt" 2>nul
                    echo [aw-qt]> "!AW_QT_CONFIG!"
                    echo autostart_modules = ["aw-server-rust", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]>> "!AW_QT_CONFIG!"
                    echo.>> "!AW_QT_CONFIG!"
                    echo [aw-qt-testing]>> "!AW_QT_CONFIG!"
                    echo autostart_modules = ["aw-server-rust", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]>> "!AW_QT_CONFIG!"
                    echo Created aw-qt.toml with aw-watcher-enhanced in autostart.
                )

                echo NOTE: Restart ActivityWatch to see the watcher in the tray menu.
            ) else (
                echo WARNING: Failed to copy executable. Try running as Administrator.
            )
        )
    )
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
    powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\AW Watcher Enhanced.lnk'); $s.TargetPath = '%PYTHONW_EXE%'; $s.Arguments = '-m aw_watcher_enhanced'; $s.WorkingDirectory = '%PROJECT_DIR%'; $s.Description = 'ActivityWatch Enhanced Watcher'; $s.Save()"
    echo Desktop shortcut created.
)
echo.

REM Create Start Menu shortcut (optional)
set /p CREATE_STARTMENU="Create Start Menu shortcut? (y/n): "
if /i "%CREATE_STARTMENU%"=="y" (
    echo Creating Start Menu shortcut...
    set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
    powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('!STARTMENU!\AW Watcher Enhanced.lnk'); $s.TargetPath = '%PYTHONW_EXE%'; $s.Arguments = '-m aw_watcher_enhanced'; $s.WorkingDirectory = '%PROJECT_DIR%'; $s.Description = 'ActivityWatch Enhanced Watcher'; $s.Save()"
    echo Start Menu shortcut created.
)
echo.

REM Create startup shortcut (if not using service)
if /i not "%INSTALL_SERVICE%"=="y" (
    set /p CREATE_STARTUP="Add to Windows startup? (y/n): "
    if /i "!CREATE_STARTUP!"=="y" (
        echo Adding to startup...
        set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
        powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('!STARTUP!\AW Watcher Enhanced.lnk'); $s.TargetPath = '%PYTHONW_EXE%'; $s.Arguments = '-m aw_watcher_enhanced'; $s.WorkingDirectory = '%PROJECT_DIR%'; $s.WindowStyle = 7; $s.Description = 'ActivityWatch Enhanced Watcher'; $s.Save()"
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
if defined AW_DIR (
    if /i "!TRAY_INTEGRATE!"=="y" (
        echo Tray Integration:
        echo   The watcher appears in the ActivityWatch tray menu.
        echo   Restart ActivityWatch if it doesn't appear immediately.
        echo.
    )
)
echo Configuration:
echo   %LOCALAPPDATA%\activitywatch\aw-watcher-enhanced\config.yaml
echo.
echo Logs:
echo   %LOCALAPPDATA%\activitywatch\logs\
echo.
echo Executable:
echo   %WATCHER_EXE%
echo.

pause
endlocal
