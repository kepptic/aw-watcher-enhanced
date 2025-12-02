# macOS Installation Guide

This guide covers installing aw-watcher-enhanced on macOS (Intel and Apple Silicon).

## Prerequisites

- **macOS 11.0 (Big Sur) or later** (for Apple Vision OCR)
- **Python 3.9+** (3.11 or 3.12 recommended)
- **ActivityWatch** installed and running ([download](https://activitywatch.net/downloads/))
- **Homebrew** (recommended for Python installation)

## Quick Install

```bash
# Clone the repository
git clone https://github.com/kepptic/aw-watcher-enhanced.git
cd aw-watcher-enhanced

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install with macOS dependencies
pip install -e ".[macos]"

# Run the watcher
aw-watcher-enhanced
```

## Detailed Installation

### Step 1: Install Python (if needed)

```bash
# Using Homebrew (recommended)
brew install python@3.12

# Verify installation
python3 --version  # Should be 3.9+
```

### Step 2: Clone and Setup

```bash
# Clone the repository
git clone https://github.com/kepptic/aw-watcher-enhanced.git
cd aw-watcher-enhanced

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### Step 3: Install Dependencies

```bash
# Install with macOS-specific dependencies
pip install -e ".[macos]"
```

This installs:
- `pyobjc-framework-Cocoa` - macOS window detection
- `pyobjc-framework-Quartz` - Screen capture and idle detection
- `ocrmac` - Apple Vision OCR (Neural Engine accelerated)

### Step 4: Grant Permissions

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

### Step 5: Verify Installation

```bash
# Activate virtual environment
source venv/bin/activate

# Test the watcher
aw-watcher-enhanced --verbose

# You should see:
# Using Apple Vision OCR (Neural Engine accelerated)
# Idle detection enabled
# OCR diff detection enabled
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

To start automatically on login:

### Create Launch Agent

```bash
# Create the plist file
cat > ~/Library/LaunchAgents/net.activitywatch.aw-watcher-enhanced.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>net.activitywatch.aw-watcher-enhanced</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/your/venv/bin/aw-watcher-enhanced</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/aw-watcher-enhanced.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/aw-watcher-enhanced.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
EOF

# Update the path to your venv
# Then load the service
launchctl load ~/Library/LaunchAgents/net.activitywatch.aw-watcher-enhanced.plist
```

### Service Management

```bash
# Start
launchctl start net.activitywatch.aw-watcher-enhanced

# Stop
launchctl stop net.activitywatch.aw-watcher-enhanced

# Unload (disable)
launchctl unload ~/Library/LaunchAgents/net.activitywatch.aw-watcher-enhanced.plist

# Check status
launchctl list | grep aw-watcher

# View logs
tail -f /tmp/aw-watcher-enhanced.log
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
  trigger: smart
  engine: auto  # Uses Apple Vision automatically
  extract_mode: full_text

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
- Increase `poll_time` to 10.0 or higher
- Set `ocr.trigger` to `window_change` instead of `smart`
- Disable LLM if not needed: `--no-llm`

### Ollama not connecting
- Ensure Ollama is running: `ollama serve`
- Check if model is pulled: `ollama list`
- Test connection: `curl http://localhost:11434/api/tags`

### Permission denied for Python
If using a system Python, consider using pyenv or Homebrew Python instead.

## Performance on Apple Silicon

On M1/M2/M3 Macs, the watcher is highly optimized:

| Component | Performance |
|-----------|-------------|
| Apple Vision OCR | ~100ms (Neural Engine) |
| LLM (gemma3:4b) | ~2-3s per query |
| Idle Detection | Native Quartz API |
| Memory Usage | ~50-100MB |

## Uninstallation

```bash
# Stop the service
launchctl unload ~/Library/LaunchAgents/net.activitywatch.aw-watcher-enhanced.plist

# Remove the plist
rm ~/Library/LaunchAgents/net.activitywatch.aw-watcher-enhanced.plist

# Remove the package
pip uninstall aw-watcher-enhanced

# Remove config (optional)
rm -rf ~/Library/Application\ Support/activitywatch/aw-watcher-enhanced
```
