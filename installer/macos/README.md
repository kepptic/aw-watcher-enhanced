# ActivityWatch Enhanced - macOS Installation Guide

## Quick Install

```bash
cd installer/macos
./install.sh
```

Or with options:
```bash
./install.sh --service --venv
```

## Installation Options

| Option | Description |
|--------|-------------|
| `--service`, `-s` | Install as launchd service (auto-start at login) |
| `--venv`, `-v` | Create and use a Python virtual environment |
| `--help`, `-h` | Show help message |

## What Gets Installed

1. **Python Package**: `aw-watcher-enhanced` with macOS dependencies
2. **Configuration**: `~/Library/Application Support/activitywatch/aw-watcher-enhanced/config.yaml`
3. **Logs**: `~/Library/Logs/activitywatch/`
4. **LaunchAgent** (optional): `~/Library/LaunchAgents/com.dagtech.aw-watcher-enhanced.plist`

## Permissions Required

### Accessibility Access (Required)
Window title capture requires Accessibility permissions:

1. Open **System Preferences** > **Security & Privacy** > **Privacy**
2. Select **Accessibility** in the left panel
3. Click the lock icon and enter your password
4. Add **Terminal.app** (or your terminal app) to the list
5. If using the launchd service, also add **Python**

### Screen Recording (Required for OCR)
Screen capture for OCR requires Screen Recording permissions:

1. Open **System Preferences** > **Security & Privacy** > **Privacy**
2. Select **Screen Recording** in the left panel
3. Add **Terminal.app** and/or **Python** to the list

## Running Manually

```bash
# Basic usage
aw-watcher-enhanced

# With verbose logging
aw-watcher-enhanced --verbose

# Without OCR (less CPU usage)
aw-watcher-enhanced --no-ocr

# Test mode (uses port 5666)
aw-watcher-enhanced --testing
```

## LaunchD Service Management

### Check Status
```bash
launchctl list | grep aw-watcher
```

### View Logs
```bash
# Standard output
tail -f ~/Library/Logs/activitywatch/aw-watcher-enhanced.log

# Errors
tail -f ~/Library/Logs/activitywatch/aw-watcher-enhanced.error.log
```

### Stop Service
```bash
launchctl unload ~/Library/LaunchAgents/com.dagtech.aw-watcher-enhanced.plist
```

### Start Service
```bash
launchctl load ~/Library/LaunchAgents/com.dagtech.aw-watcher-enhanced.plist
```

### Restart Service
```bash
launchctl unload ~/Library/LaunchAgents/com.dagtech.aw-watcher-enhanced.plist
launchctl load ~/Library/LaunchAgents/com.dagtech.aw-watcher-enhanced.plist
```

### Remove Service
```bash
launchctl unload ~/Library/LaunchAgents/com.dagtech.aw-watcher-enhanced.plist
rm ~/Library/LaunchAgents/com.dagtech.aw-watcher-enhanced.plist
```

## Multi-Monitor Support

The watcher supports multiple monitors for OCR capture. To enable:

Edit `~/Library/Application Support/activitywatch/aw-watcher-enhanced/config.yaml`:

```yaml
ocr:
  enabled: true
  capture_all_monitors: true  # Enable multi-monitor OCR
  trigger: window_change
```

**Note**: Multi-monitor OCR uses more CPU. Consider using `window_change` trigger instead of `periodic` to reduce load.

## RAG Database Integration

The watcher automatically integrates with your RAG database for client detection. It looks for the database at:

```
~/Library/CloudStorage/Dropbox/Documents++/Work documents/DAG Tech/Time Tracking/AW-Watcher Logs/cache/
```

Features:
- **Domain-based detection**: Recognizes clients from website domains
- **Email-based detection**: Identifies clients from email addresses
- **Text-based detection**: Finds client codes in window titles and OCR content
- **Project code detection**: Extracts project codes (e.g., P202502-539)

To disable RAG integration, edit config.yaml:

```yaml
categorization:
  use_rag: false
```

## Configuration

Full configuration file location:
```
~/Library/Application Support/activitywatch/aw-watcher-enhanced/config.yaml
```

### Example Configuration

```yaml
watcher:
  poll_time: 5.0      # Seconds between checks
  pulsetime: 6.0      # Heartbeat merge window

ocr:
  enabled: true
  trigger: window_change  # window_change, periodic, or both
  periodic_interval: 30   # Seconds (if periodic)
  capture_all_monitors: false  # Set true for multi-monitor
  engine: auto            # auto or tesseract
  extract_mode: keywords  # keywords, entities, or full_text
  max_keywords: 20

privacy:
  exclude_apps:
    - "1Password 7"
    - "Keychain Access"
    - "System Preferences"
  exclude_titles:
    - ".*[Pp]assword.*"
    - ".*[Pp]rivate.*"
  exclude_urls:
    - ".*bank.*"

categorization:
  enabled: true
  use_rag: true  # Use RAG database for client detection
```

## Troubleshooting

### "Operation not permitted" errors
Grant Accessibility and Screen Recording permissions as described above.

### Service doesn't start
1. Check logs: `tail -f ~/Library/Logs/activitywatch/aw-watcher-enhanced.error.log`
2. Verify ActivityWatch is running: `curl http://localhost:5600/api/0/info`
3. Try running manually first: `aw-watcher-enhanced --verbose`

### OCR not working
1. Grant Screen Recording permission
2. Install Tesseract: `brew install tesseract`
3. Install Python OCR deps: `pip install pytesseract Pillow mss`

### High CPU usage
1. Disable multi-monitor OCR
2. Change trigger to `window_change` instead of `periodic`
3. Increase `poll_time` to 10 seconds
4. Disable OCR entirely with `--no-ocr`

### RAG database not found
Ensure the path exists:
```bash
ls ~/Library/CloudStorage/Dropbox/Documents++/Work\ documents/DAG\ Tech/Time\ Tracking/AW-Watcher\ Logs/cache/
```

## Uninstall

```bash
./uninstall.sh
```

Or manually:
```bash
# Stop and remove service
launchctl unload ~/Library/LaunchAgents/com.dagtech.aw-watcher-enhanced.plist
rm ~/Library/LaunchAgents/com.dagtech.aw-watcher-enhanced.plist

# Remove config (optional)
rm -rf ~/Library/Application\ Support/activitywatch/aw-watcher-enhanced

# Uninstall package (optional)
pip uninstall aw-watcher-enhanced
```
