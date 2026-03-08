# ActivityWatch Enhanced - macOS Installation Guide

## Quick Install

```bash
cd installer/macos
./install.sh
```

Or with options:
```bash
./install.sh --service    # Also install launchd auto-start service
./install.sh --prebuilt   # Skip compilation, use existing binary
```

## Requirements

- **macOS 12+** (Monterey or later)
- **Rust toolchain** — install from [rustup.rs](https://rustup.rs)
- **ActivityWatch** — installed and running

## What Gets Installed

1. **Binary**: `/usr/local/bin/aw-watcher-enhanced` (~6.5MB native binary)
2. **Configuration**: `~/Library/Application Support/activitywatch/aw-watcher-enhanced/config.toml`
3. **aw-qt registration**: Added to `aw-qt.toml` autostart modules
4. **LaunchAgent** (optional): `~/Library/LaunchAgents/com.kepptic.aw-watcher-enhanced.plist`

## Permissions Required

### Accessibility Access (Required)
Window title and app detection:
1. Open **System Settings** > **Privacy & Security** > **Accessibility**
2. Add your terminal app (Terminal.app, iTerm, etc.)
3. If using launchd service, also add the binary

### Screen Recording (Required for OCR)
Screen capture for text extraction:
1. Open **System Settings** > **Privacy & Security** > **Screen Recording**
2. Add your terminal app and/or the binary

## Running

```bash
# Standard
aw-watcher-enhanced

# Debug logging
RUST_LOG=debug aw-watcher-enhanced

# Test mode (port 5666)
aw-watcher-enhanced --testing
```

## LaunchD Service

```bash
# Status
launchctl list | grep aw-watcher

# Logs
tail -f ~/Library/Logs/activitywatch/aw-watcher-enhanced.log

# Stop / Start / Restart
launchctl unload ~/Library/LaunchAgents/com.kepptic.aw-watcher-enhanced.plist
launchctl load ~/Library/LaunchAgents/com.kepptic.aw-watcher-enhanced.plist
```

## Configuration

Config file: `~/Library/Application Support/activitywatch/aw-watcher-enhanced/config.toml`

```toml
[watcher]
poll_time = 5.0        # Enrichment frequency (seconds)
heartbeat_time = 1.0   # Heartbeat interval (seconds)

[ocr]
enabled = true
min_interval = 10.0    # Min seconds between OCR captures
max_keywords = 20

[llm]
enabled = true
model = "gemma3:1b"    # Ollama model (requires Ollama running)
timeout = 10.0

[privacy]
exclude_apps = ["1Password", "Keychain Access"]
exclude_titles = [".*[Pp]assword.*"]
```

## Features

- **Window tracking** — app name, title, category via AXUIElement API
- **OCR** — focused-window capture via ScreenCaptureKit + Apple Vision
- **LLM enrichment** — Ollama-powered keyword/project/client extraction
- **Document context** — file, project, language from IDE titles
- **Browser integration** — URL merge from aw-watcher-web extension
- **Remote Desktop detection** — Microsoft Remote Desktop, AnyDesk, TeamViewer, etc.
- **Meeting detection** — Zoom, Teams, 8x8, WebEx context awareness
- **IT management** — Datto RMM, ConnectWise, NinjaOne client extraction
- **Calendar integration** — EventKit current meeting detection
- **Snapshot bucket** — volatile OCR/LLM data separated for clean timeline

## Uninstall

```bash
./uninstall.sh
```
