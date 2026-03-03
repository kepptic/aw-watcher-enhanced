# macOS Installation Guide

This guide covers installing aw-watcher-enhanced on macOS (Intel and Apple Silicon).

## Prerequisites

- **macOS 11.0 (Big Sur) or later** (for Apple Vision OCR)
- **Python 3.9+** (3.11+ recommended)
- **ActivityWatch** installed and running ([download](https://activitywatch.net/downloads/))
- **Homebrew** (recommended for Python installation)

## Quick Install

```bash
# Clone the repository
git clone https://github.com/kepptic/aw-watcher-enhanced.git
cd aw-watcher-enhanced

# Install the package (creates aw-watcher-enhanced on PATH)
pip3 install -e .

# Verify it's on PATH
which aw-watcher-enhanced

# Run the watcher
aw-watcher-enhanced
```

That's it. `pip install` creates an `aw-watcher-enhanced` executable on PATH via the `[project.scripts]` entry point. aw-qt discovers it automatically.

### Register with ActivityWatch

Add `aw-watcher-enhanced` to aw-qt's autostart config:

```bash
# Edit the config
nano ~/Library/Application\ Support/activitywatch/aw-qt/aw-qt.toml
```

```toml
[aw-qt]
autostart_modules = ["aw-server", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]

[aw-qt-testing]
autostart_modules = ["aw-server", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]
```

Restart ActivityWatch. The watcher will appear in the tray menu and start automatically.

> **Survives ActivityWatch updates**: Both the pip-installed executable and `aw-qt.toml` live outside the `.app` bundle. aw-qt finds watchers on PATH via its system module discovery — no wrapper scripts inside the bundle needed.

### Using the Installer Script

For a guided installation that handles everything:

```bash
cd installer/macos
./install.sh             # Installs package + registers with aw-qt
./install.sh --service   # Also creates a launchd service as fallback
```

## Detailed Installation

### Step 1: Install Python (if needed)

```bash
# Using Homebrew (recommended)
brew install python@3.13

# Verify installation
python3 --version  # Should be 3.9+
```

### Step 2: Clone and Install

```bash
# Clone the repository
git clone https://github.com/kepptic/aw-watcher-enhanced.git
cd aw-watcher-enhanced

# Install the package
pip3 install -e .

# Verify the executable is on PATH
which aw-watcher-enhanced
# Should show something like /opt/homebrew/bin/aw-watcher-enhanced
```

### Step 3: Grant Permissions

macOS requires explicit permissions for accessibility and screen recording.

#### Accessibility Permission (required for window tracking)
1. Open **System Settings** > **Privacy & Security** > **Accessibility**
2. Click the **+** button
3. Add **Terminal** (or your terminal app: iTerm, Warp, etc.)
4. If running from an IDE, add that too (VS Code, PyCharm, etc.)

#### Screen Recording Permission (required for OCR)
1. Open **System Settings** > **Privacy & Security** > **Screen Recording**
2. Click the **+** button
3. Add the same applications as above

> **Note:** You may need to restart your terminal after granting permissions.

### Step 4: Register with aw-qt

Edit `~/Library/Application Support/activitywatch/aw-qt/aw-qt.toml` and add `aw-watcher-enhanced` to the `autostart_modules` list (see Quick Install above).

### Step 5: Verify Installation

```bash
# Test the watcher
aw-watcher-enhanced --verbose

# You should see:
# Initialized aw-watcher-enhanced
# OCR enabled: True
# Idle detection enabled
# Meeting detection enabled
# Browser URL merging enabled

# Test daily summary (requires ActivityWatch to be running)
aw-watcher-enhanced --summary today
```

## Optional: LLM Enhancement (Ollama)

For intelligent document/client extraction using local LLM:

### Install Ollama

```bash
# Download from https://ollama.ai or use Homebrew
brew install ollama

# Start Ollama service
ollama serve

# Pull a model (in another terminal)
ollama pull gemma3:4b  # Recommended: fast and accurate
```

### Configure LLM

The watcher auto-detects Ollama. To customize, edit the config:

```bash
# Config location
~/Library/Application Support/activitywatch/aw-watcher-enhanced/config.yaml
```

```yaml
llm:
  enabled: true
  model: "gemma3:4b"  # or qwen2.5:7b for better accuracy
  timeout: 10.0
```

## Optional: RAG Database (Qdrant)

For client detection from your knowledge base:

```bash
# Start Qdrant in Docker
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v ~/qdrant_storage:/qdrant/storage \
  qdrant/qdrant:latest
```

## Running as a Service (launchd)

The installer script can set up a launchd service:

```bash
./installer/macos/install.sh --service
```

Or manually:

```bash
# Create the plist
cat > ~/Library/LaunchAgents/com.kepptic.aw-watcher-enhanced.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kepptic.aw-watcher-enhanced</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(which aw-watcher-enhanced)</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>Crashed</key>
        <true/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>30</integer>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/activitywatch/aw-watcher-enhanced.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/activitywatch/aw-watcher-enhanced.error.log</string>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
EOF

# Load it
launchctl load ~/Library/LaunchAgents/com.kepptic.aw-watcher-enhanced.plist
```

### Service Management

```bash
# Check status
launchctl list | grep aw-watcher

# Stop
launchctl unload ~/Library/LaunchAgents/com.kepptic.aw-watcher-enhanced.plist

# Start
launchctl load ~/Library/LaunchAgents/com.kepptic.aw-watcher-enhanced.plist

# View logs
tail -f ~/Library/Logs/activitywatch/aw-watcher-enhanced.log
```

## Configuration

Config file location:
```
~/Library/Application Support/activitywatch/aw-watcher-enhanced/config.yaml
```

### Recommended macOS Config

```yaml
watcher:
  poll_time: 5.0
  pulsetime: 6.0

smart_capture:
  idle_threshold: 60.0
  idle_poll_time: 30.0
  remote_desktop_interval: 10.0
  ocr_diff:
    similarity_threshold: 0.85
    min_change_chars: 50

ocr:
  enabled: true
  trigger: adaptive     # Only fires OCR when primary data is thin
  engine: auto          # Uses Apple Vision automatically

browser:
  enabled: true         # Merge URL data from aw-watcher-web

meeting:
  enabled: true
  detect_subprocess: true

llm:
  enabled: true
  model: gemma3:4b
  timeout: 10.0

privacy:
  exclude_apps:
    - "1Password 7"
    - "Keychain Access"
    - "Secrets"
  exclude_titles:
    - ".*[Pp]assword.*"
    - ".*[Pp]rivate.*"
```

## Troubleshooting

### "Operation not permitted" error
- Grant Accessibility permission in System Settings
- Grant Screen Recording permission in System Settings
- Restart your terminal after granting permissions

### OCR not detecting text
- Ensure Screen Recording permission is granted
- Check that Apple Vision is available: `python3 -c "from ocrmac import ocrmac; print('OK')"`

### High CPU usage
- The default `adaptive` OCR trigger minimizes unnecessary captures
- Increase `poll_time` to 10.0 or higher
- Disable LLM if not needed: `--no-llm`

### Ollama not connecting
- Ensure Ollama is running: `ollama serve`
- Check if model is pulled: `ollama list`
- Test connection: `curl http://localhost:11434/api/tags`

### Watcher not showing in aw-qt tray
- Verify the executable is on PATH: `which aw-watcher-enhanced`
- Verify aw-qt.toml has it in `autostart_modules`
- Restart ActivityWatch completely (quit + reopen)

### Permission denied for pip install
If using system Python on macOS 14+, use `--break-system-packages` or install via Homebrew Python.

## Performance on Apple Silicon

On M1/M2/M3/M4 Macs, the watcher is highly optimized:

| Component | Performance |
|-----------|-------------|
| Apple Vision OCR | ~100ms (Neural Engine) |
| LLM (gemma3:4b) | ~2-3s per query |
| Idle Detection | Native Quartz API |
| Memory Usage | ~50-100MB |

## Uninstallation

```bash
# Uninstall the package (removes executable from PATH)
pip3 uninstall aw-watcher-enhanced

# Remove launchd service (if installed)
launchctl unload ~/Library/LaunchAgents/com.kepptic.aw-watcher-enhanced.plist
rm ~/Library/LaunchAgents/com.kepptic.aw-watcher-enhanced.plist

# Remove config (optional)
rm -rf ~/Library/Application\ Support/activitywatch/aw-watcher-enhanced

# Remove aw-watcher-enhanced from aw-qt.toml autostart_modules
```
