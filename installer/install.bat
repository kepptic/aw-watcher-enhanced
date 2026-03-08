@echo off
setlocal EnableDelayedExpansion
REM ============================================================================
REM ActivityWatch Enhanced Watcher v1.0.0 - Windows Installer (Rust)
REM ============================================================================
REM Compiles the Rust watcher and installs the binary.
REM
REM Requirements:
REM   - Rust toolchain (https://rustup.rs)
REM   - ActivityWatch installed and running
REM
REM Usage:
REM   install.bat              Build and install
REM   install.bat --prebuilt   Skip build, use existing binary
REM   install.bat --service    Also register as a startup task
REM ============================================================================

echo.
echo ============================================================
echo   ActivityWatch Enhanced Watcher v1.0.0 - Windows Installer
echo ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "RUST_DIR=%PROJECT_DIR%\rust-watcher"
set "BINARY_NAME=aw-watcher-enhanced.exe"
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\activitywatch"
set "CONFIG_DIR=%LOCALAPPDATA%\activitywatch\aw-watcher-enhanced"
set "SKIP_BUILD=0"
set "INSTALL_SERVICE=0"

REM Parse arguments
:parse_args
if "%~1"=="" goto :done_args
if /i "%~1"=="--prebuilt" set "SKIP_BUILD=1"
if /i "%~1"=="--service" set "INSTALL_SERVICE=1"
if /i "%~1"=="--help" goto :show_help
shift
goto :parse_args
:done_args

REM ── Check requirements ──────────────────────────────────────────────────────

echo [INFO] Checking requirements...

REM Check Rust
where rustc >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Rust toolchain not found.
    echo Install from: https://rustup.rs
    pause
    exit /b 1
)
rustc --version
echo [OK] Rust found
echo.

REM Check ActivityWatch
curl -s http://localhost:5600/api/0/info >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] ActivityWatch server is running
) else (
    echo [WARN] ActivityWatch server not running.
    echo        Start ActivityWatch before using this watcher.
)
echo.

REM ── Build ───────────────────────────────────────────────────────────────────

if "%SKIP_BUILD%"=="1" (
    echo [INFO] Using prebuilt binary...
    if not exist "%RUST_DIR%\target\release\%BINARY_NAME%" (
        echo [ERROR] No prebuilt binary found. Run without --prebuilt.
        pause
        exit /b 1
    )
) else (
    echo [INFO] Building aw-watcher-enhanced (release mode^)...
    echo        This may take a few minutes on first build.
    echo.
    cd "%RUST_DIR%"
    cargo build --release
    if %errorlevel% neq 0 (
        echo [ERROR] Build failed.
        pause
        exit /b 1
    )
    echo.
    echo [OK] Build complete
)
echo.

REM ── Install binary ──────────────────────────────────────────────────────────

echo [INFO] Installing binary...

REM Stop running instance
tasklist /FI "IMAGENAME eq %BINARY_NAME%" 2>nul | find /i "%BINARY_NAME%" >nul
if %errorlevel% equ 0 (
    echo [WARN] Stopping running instance...
    taskkill /IM "%BINARY_NAME%" /F >nul 2>&1
    timeout /t 1 /nobreak >nul
)

REM Install to ActivityWatch directory if it exists, otherwise to a local dir
if exist "%INSTALL_DIR%" (
    copy /Y "%RUST_DIR%\target\release\%BINARY_NAME%" "%INSTALL_DIR%\%BINARY_NAME%" >nul
    echo [OK] Installed to %INSTALL_DIR%\%BINARY_NAME%
) else (
    set "INSTALL_DIR=%LOCALAPPDATA%\aw-watcher-enhanced"
    mkdir "%INSTALL_DIR%" 2>nul
    copy /Y "%RUST_DIR%\target\release\%BINARY_NAME%" "%INSTALL_DIR%\%BINARY_NAME%" >nul
    echo [OK] Installed to %INSTALL_DIR%\%BINARY_NAME%
    echo [WARN] Not in PATH. Add %INSTALL_DIR% to your PATH or use full path.
)
echo.

REM ── Create config ───────────────────────────────────────────────────────────

echo [INFO] Setting up configuration...
mkdir "%CONFIG_DIR%" 2>nul

if not exist "%CONFIG_DIR%\config.toml" (
    (
        echo # ActivityWatch Enhanced Watcher Configuration
        echo.
        echo [watcher]
        echo poll_time = 5.0
        echo heartbeat_time = 1.0
        echo.
        echo [ocr]
        echo enabled = false
        echo min_interval = 10.0
        echo max_keywords = 20
        echo.
        echo [llm]
        echo enabled = false
        echo model = "gemma3:1b"
        echo timeout = 10.0
        echo.
        echo [privacy]
        echo exclude_apps = ["1Password"]
        echo exclude_titles = [".*[Pp]assword.*"]
    ) > "%CONFIG_DIR%\config.toml"
    echo [OK] Created config: %CONFIG_DIR%\config.toml
) else (
    echo [INFO] Config already exists: %CONFIG_DIR%\config.toml
)
echo.

REM ── Register with aw-qt ─────────────────────────────────────────────────────

echo [INFO] Registering with ActivityWatch...
set "AW_QT_CONFIG=%LOCALAPPDATA%\activitywatch\activitywatch\aw-qt\aw-qt.toml"

if exist "%AW_QT_CONFIG%" (
    findstr /C:"aw-watcher-enhanced" "%AW_QT_CONFIG%" >nul 2>&1
    if !errorlevel! neq 0 (
        powershell -Command "(Get-Content '%AW_QT_CONFIG%') -replace 'autostart_modules = \[(.+?)\]', 'autostart_modules = [$1, \"aw-watcher-enhanced\"]' | Set-Content '%AW_QT_CONFIG%'"
        echo [OK] Added to aw-qt autostart
    ) else (
        echo [INFO] Already registered in aw-qt.toml
    )
) else (
    mkdir "%LOCALAPPDATA%\activitywatch\activitywatch\aw-qt" 2>nul
    (
        echo [aw-qt]
        echo autostart_modules = ["aw-server-rust", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]
        echo.
        echo [aw-qt-testing]
        echo autostart_modules = ["aw-server-rust", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]
    ) > "%AW_QT_CONFIG%"
    echo [OK] Created aw-qt.toml
)
echo.

REM ── Startup task ────────────────────────────────────────────────────────────

if "%INSTALL_SERVICE%"=="1" (
    echo [INFO] Creating startup task...
    schtasks /Create /TN "AW Watcher Enhanced" /TR "\"%INSTALL_DIR%\%BINARY_NAME%\"" /SC ONLOGON /RL LIMITED /F >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK] Startup task created
    ) else (
        echo [WARN] Failed to create startup task. Try running as administrator.
    )
    echo.
)

REM ── Done ────────────────────────────────────────────────────────────────────

echo ============================================================
echo   Installation Complete!
echo ============================================================
echo.
echo Binary: %INSTALL_DIR%\%BINARY_NAME%
echo Config: %CONFIG_DIR%\config.toml
echo.
echo Usage:
echo   Run manually:  aw-watcher-enhanced
echo   With debug:    set RUST_LOG=debug ^& aw-watcher-enhanced
echo   Test mode:     aw-watcher-enhanced --testing
echo.
echo Restart ActivityWatch to activate the watcher.
echo.
pause
exit /b 0

:show_help
echo Usage: install.bat [options]
echo.
echo Options:
echo   --prebuilt     Skip compilation, use existing binary
echo   --service      Register as startup task (runs at login)
echo   --help         Show this help
echo.
echo Requires: Rust toolchain (https://rustup.rs)
pause
exit /b 0
