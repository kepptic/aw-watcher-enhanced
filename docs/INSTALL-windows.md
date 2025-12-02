# Windows Installation Guide

This guide covers installing aw-watcher-enhanced on Windows 10/11.

## Prerequisites

- **Windows 10 (1903+) or Windows 11**
- **Python 3.9+** (3.11 or 3.12 recommended)
- **ActivityWatch** installed and running ([download](https://activitywatch.net/downloads/))

## Quick Install

```powershell
# Clone the repository
git clone https://github.com/kepptic/aw-watcher-enhanced.git
cd aw-watcher-enhanced

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install with Windows dependencies
pip install -e ".[windows]"

# Run the watcher
aw-watcher-enhanced
```

## Detailed Installation

### Step 1: Install Python

1. Download Python 3.12 from [python.org](https://www.python.org/downloads/)
2. Run the installer
3. **Important:** Check "Add Python to PATH"
4. Click "Install Now"

Verify installation:
```powershell
python --version  # Should be 3.9+
```

### Step 2: Clone and Setup

```powershell
# Clone the repository
git clone https://github.com/kepptic/aw-watcher-enhanced.git
cd aw-watcher-enhanced

# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Upgrade pip
python -m pip install --upgrade pip
```

### Step 3: Install Dependencies

```powershell
# Install with Windows-specific dependencies
pip install -e ".[windows]"
```

This installs:
- `pywin32` - Windows API access for window tracking
- `winocr` - Windows.Media.Ocr for fast built-in OCR
- `mss` - Screen capture
- `Pillow` - Image processing

### Step 4: Install OCR Language Pack (if needed)

Windows OCR requires language packs. English is usually pre-installed, but you can add more:

```powershell
# Run as Administrator
Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"
```

### Step 5: Verify Installation

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Test the watcher
aw-watcher-enhanced --verbose

# You should see:
# Using Windows OCR API (built-in)
# Idle detection enabled
# OCR diff detection enabled
```

## Optional: RapidOCR (Better Accuracy)

For improved OCR accuracy on complex documents:

```powershell
pip install rapidocr_onnxruntime
```

RapidOCR will be used automatically if Windows OCR is unavailable, or you can force it:

```yaml
# In config.yaml
ocr:
  engine: rapidocr
```

## Optional: LLM Enhancement (Ollama)

For intelligent document/client extraction using local LLM:

### Install Ollama for Windows

1. Download from [ollama.ai](https://ollama.ai/download/windows)
2. Run the installer
3. Ollama starts automatically as a service

### Pull a Model

```powershell
# Open PowerShell
ollama pull gemma3:4b  # Recommended: fast and accurate
```

### Configure LLM

Edit the config file:
```
%LOCALAPPDATA%\activitywatch\aw-watcher-enhanced\config.yaml
```

```yaml
llm:
  enabled: true
  model: "gemma3:4b"
  timeout: 10.0
```

## Optional: RAG Database (Qdrant)

For client detection from your knowledge base:

### Using Docker Desktop

```powershell
# Install Docker Desktop first from docker.com

# Start Qdrant
docker run -d --name qdrant `
  -p 6333:6333 -p 6334:6334 `
  -v qdrant_storage:/qdrant/storage `
  qdrant/qdrant:latest
```

## Running as a Windows Service

### Option 1: Task Scheduler (Recommended)

1. Open **Task Scheduler** (search in Start menu)
2. Click **Create Basic Task**
3. Name: `aw-watcher-enhanced`
4. Trigger: **When I log on**
5. Action: **Start a program**
6. Program: `C:\path\to\venv\Scripts\pythonw.exe`
7. Arguments: `-m aw_watcher_enhanced`
8. Start in: `C:\path\to\aw-watcher-enhanced`
9. Check **Open Properties dialog** and click Finish
10. In Properties, check **Run whether user is logged on or not** (optional)

### Option 2: NSSM (Non-Sucking Service Manager)

```powershell
# Download NSSM from nssm.cc
# Extract and add to PATH

# Install as service
nssm install aw-watcher-enhanced "C:\path\to\venv\Scripts\python.exe" "-m aw_watcher_enhanced"

# Start the service
nssm start aw-watcher-enhanced

# Check status
nssm status aw-watcher-enhanced
```

### Option 3: Startup Folder

1. Press `Win+R`, type `shell:startup`, press Enter
2. Create a shortcut to run the watcher:
   - Target: `C:\path\to\venv\Scripts\pythonw.exe -m aw_watcher_enhanced`
   - Start in: `C:\path\to\aw-watcher-enhanced`

## Configuration

Config file location:
```
%LOCALAPPDATA%\activitywatch\aw-watcher-enhanced\config.yaml
```

Or in PowerShell:
```powershell
notepad $env:LOCALAPPDATA\activitywatch\aw-watcher-enhanced\config.yaml
```

### Recommended Windows Config

```yaml
watcher:
  poll_time: 5.0
  pulsetime: 6.0

smart_capture:
  idle_threshold: 60.0
  idle_poll_time: 30.0
  remote_desktop_interval: 10.0
  remote_desktop_apps:
    - "Microsoft Remote Desktop"
    - "Windows App"
    - "mstsc"
    - "Remote Desktop Connection"
    - "Citrix Workspace"
    - "VMware Horizon"
    - "TeamViewer"
    - "AnyDesk"
  ocr_diff:
    similarity_threshold: 0.85
    min_change_chars: 50

ocr:
  enabled: true
  trigger: smart
  engine: auto  # Uses Windows OCR API
  extract_mode: full_text

llm:
  enabled: false  # Set to true if Ollama is installed
  model: gemma3:4b
  timeout: 10.0

privacy:
  exclude_apps:
    - "1Password.exe"
    - "KeePass.exe"
    - "LastPass.exe"
    - "Bitwarden.exe"
  exclude_titles:
    - ".*[Pp]assword.*"
    - ".*[Pp]rivate.*"
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'win32api'"

```powershell
pip install pywin32
# Then run post-install script
python -m pywin32_postinstall -install
```

### Windows OCR not working

1. Check if OCR language pack is installed:
```powershell
Get-WindowsCapability -Online | Where-Object Name -like "Language.OCR*"
```

2. Install if missing:
```powershell
# As Administrator
Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"
```

### Many apps showing as "unknown"

Run ActivityWatch and aw-watcher-enhanced as Administrator for full process detection.

### High CPU usage

- Increase `poll_time` to 10.0 or higher
- Set `ocr.trigger` to `window_change` instead of `smart`
- Disable OCR: `aw-watcher-enhanced --no-ocr`

### Ollama not connecting

1. Check if Ollama is running:
```powershell
curl http://localhost:11434/api/tags
```

2. If not, start it:
```powershell
ollama serve
```

### Permission errors

- Run PowerShell as Administrator for installation
- Ensure Python is in PATH
- Try running from the project directory

### Virtual environment not activating

If `.\venv\Scripts\Activate.ps1` fails:
```powershell
# Allow script execution
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then try again
.\venv\Scripts\Activate.ps1
```

## Performance on Windows

| Component | Performance |
|-----------|-------------|
| Windows OCR | ~200-500ms |
| RapidOCR | ~300-800ms |
| LLM (gemma3:4b) | ~3-5s per query |
| Memory Usage | ~80-150MB |

## OCR Engine Comparison

| Engine | Speed | Accuracy | GPU | Install Size |
|--------|-------|----------|-----|--------------|
| Windows OCR | Fast | Good | No | Built-in |
| RapidOCR | Medium | Very Good | Optional | ~50MB |
| Tesseract | Slow | OK | No | ~30MB |

Windows OCR is recommended for most users. Use RapidOCR for better accuracy on complex documents.

## Uninstallation

```powershell
# Stop any running instances
taskkill /IM python.exe /F

# Remove from Task Scheduler (if added)
# Open Task Scheduler and delete the task

# Remove the package
pip uninstall aw-watcher-enhanced

# Remove config (optional)
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\activitywatch\aw-watcher-enhanced"

# Remove the repository
cd ..
Remove-Item -Recurse -Force aw-watcher-enhanced
```

## Running Without LLM

The watcher works perfectly fine without LLM enhancement. You'll still get:
- Window tracking (app, title)
- OCR text extraction
- Keyword extraction
- Entity detection (emails, URLs, dates)
- Idle detection
- Remote desktop support
- Privacy filtering

LLM adds intelligent extraction of:
- Document names
- Client codes
- Project names
- URLs from screen content
- Breadcrumb navigation paths
