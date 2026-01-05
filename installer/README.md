# ActivityWatch Enhanced - Windows Installation Guide

## Quick Install

### Option 1: Automated Installer (Recommended)

1. Right-click `install.bat` and select "Run as administrator"
2. Follow the prompts

### Option 2: Manual Installation

```batch
# Install the package
pip install -e .[windows]

# Run manually
aw-watcher-enhanced
```

## Installation Options

### 1. ActivityWatch Tray Integration (Recommended)

When you select "Add to ActivityWatch tray menu" during installation, the installer:
1. Copies `aw-watcher-enhanced.exe` to the ActivityWatch program folder
2. Adds `aw-watcher-enhanced` to `aw-qt.toml` autostart modules
3. The watcher will start automatically when ActivityWatch starts

**Manual configuration:**
Edit `%LOCALAPPDATA%\activitywatch\activitywatch\aw-qt\aw-qt.toml`:
```toml
[aw-qt]
autostart_modules = ["aw-server-rust", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]
```

### 2. Windows Service (For always-on tracking)

The Windows Service runs in the background and starts automatically at boot.

**Install:**
```batch
python installer\windows_service.py install
python installer\windows_service.py start
```

**Manage:**
```batch
# Check status
sc query AWWatcherEnhanced

# Stop
sc stop AWWatcherEnhanced

# Start
sc start AWWatcherEnhanced

# View logs
type %LOCALAPPDATA%\activitywatch\logs\aw-watcher-enhanced-service.log
```

**Uninstall:**
```batch
python installer\windows_service.py stop
python installer\windows_service.py remove
```

### 3. Startup Folder (Simpler, runs in user context)

Place `startup_script.pyw` in your Startup folder:

```batch
# Copy to startup folder
copy installer\startup_script.pyw "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\"
```

Or create a shortcut:
1. Press Win+R, type `shell:startup`, press Enter
2. Create a shortcut to `pythonw.exe -m aw_watcher_enhanced`

### 4. Task Scheduler (Most flexible)

Create a scheduled task for more control:

1. Open Task Scheduler (taskschd.msc)
2. Create Basic Task:
   - Name: "ActivityWatch Enhanced Watcher"
   - Trigger: "At log on"
   - Action: Start a program
   - Program: `pythonw.exe`
   - Arguments: `-m aw_watcher_enhanced`
3. In Properties:
   - Check "Run with highest privileges" (for better process detection)
   - On "Conditions" tab, uncheck "Start only if on AC power"

## Running as Administrator

For best results (detecting elevated processes), run as Administrator:

### Service Method
The service runs as SYSTEM by default, which can access all processes.

### Manual/Startup Method
1. Create shortcut to `pythonw.exe -m aw_watcher_enhanced`
2. Right-click shortcut → Properties → Shortcut tab → Advanced
3. Check "Run as administrator"

**Note:** Running as admin will prompt UAC at each startup unless you use Task Scheduler with "Run with highest privileges".

## Troubleshooting

### "Service failed to start"
1. Check logs: `%LOCALAPPDATA%\activitywatch\logs\`
2. Ensure ActivityWatch server is running
3. Try running manually first: `aw-watcher-enhanced --verbose`

### "Module not found"
```batch
pip install -e .[windows]
```

### "pywin32" errors
```batch
pip install pywin32
python -m pywin32_postinstall -install
```

### Service doesn't start at boot
1. Check service is set to "Automatic": `sc qc AWWatcherEnhanced`
2. Set if needed: `sc config AWWatcherEnhanced start=auto`

### OCR not working
```batch
# Install OCR dependencies
pip install winocr mss Pillow

# Or use Tesseract (install from https://github.com/tesseract-ocr/tesseract)
pip install pytesseract
```

### High CPU usage
1. Increase poll interval in config:
   ```yaml
   watcher:
     poll_time: 10.0  # Increase from default 5.0
   ```
2. Disable OCR if not needed: `aw-watcher-enhanced --no-ocr`

## Configuration

Config file location: `%LOCALAPPDATA%\activitywatch\aw-watcher-enhanced\config.yaml`

Example configuration:
```yaml
watcher:
  poll_time: 5.0

ocr:
  enabled: true
  trigger: window_change

privacy:
  exclude_apps:
    - 1Password.exe
  exclude_titles:
    - ".*password.*"

categorization:
  enabled: true
  client_keywords:
    acme-corp:
      - acme
      - project-x
```

## Files

| File | Purpose |
|------|---------|
| `install.bat` | Interactive installer |
| `uninstall.bat` | Remove installation |
| `windows_service.py` | Windows Service wrapper |
| `startup_script.pyw` | Silent startup script |

## Comparison: Service vs Startup Script

| Feature | Windows Service | Startup Script |
|---------|-----------------|----------------|
| Starts before login | Yes | No |
| Runs as SYSTEM | Yes (default) | No (user context) |
| Survives logoff | Yes | No |
| Easy to manage | Via Services.msc | Task Manager |
| UAC prompts | None | If run as admin |
| Best for | Shared computers, servers | Personal use |
