# ActivityWatch Enhanced - Windows Installation Guide

## Quick Install

1. Open Command Prompt (or PowerShell)
2. Run `install.bat`

Or with options:
```batch
install.bat --service     REM Also create startup task
install.bat --prebuilt    REM Skip compilation
```

## Requirements

- **Windows 10+**
- **Rust toolchain** — install from [rustup.rs](https://rustup.rs)
- **ActivityWatch** — installed and running

## What Gets Installed

1. **Binary**: `%LOCALAPPDATA%\Programs\activitywatch\aw-watcher-enhanced.exe`
2. **Configuration**: `%LOCALAPPDATA%\activitywatch\aw-watcher-enhanced\config.toml`
3. **aw-qt registration**: Added to `aw-qt.toml` autostart modules
4. **Startup task** (optional): Windows Task Scheduler entry

## Running

```batch
REM Standard
aw-watcher-enhanced

REM Debug logging
set RUST_LOG=debug & aw-watcher-enhanced

REM Test mode (port 5666)
aw-watcher-enhanced --testing
```

## Configuration

Config file: `%LOCALAPPDATA%\activitywatch\aw-watcher-enhanced\config.toml`

```toml
[watcher]
poll_time = 5.0
heartbeat_time = 1.0

[ocr]
enabled = false        # Windows OCR not yet implemented

[llm]
enabled = false        # Requires Ollama

[privacy]
exclude_apps = ["1Password"]
exclude_titles = [".*[Pp]assword.*"]
```

## Features (Windows)

- **Window tracking** — app name + title via Win32 GetForegroundWindow
- **Idle detection** — GetLastInputInfo
- **OS events** — app switch detection, screen lock/unlock
- **Document context** — file, project, language from IDE titles
- **Activity categorization** — category rules for 30+ app types
- **Remote Desktop detection** — Microsoft Remote Desktop, AnyDesk, TeamViewer, etc.
- **Meeting detection** — Zoom, Teams, 8x8, WebEx
- **Browser URL merge** — integrates with aw-watcher-web extension

### Not yet available on Windows
- OCR screen capture (macOS only — uses Apple Vision)
- Calendar integration (macOS only — uses EventKit)

## Uninstall

```batch
uninstall.bat
```
