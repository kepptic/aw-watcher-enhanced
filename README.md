# aw-watcher-enhanced

[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![ActivityWatch](https://img.shields.io/badge/ActivityWatch-compatible-orange.svg)](https://activitywatch.net/)

An enhanced [ActivityWatch](https://activitywatch.net/) watcher with OCR screen content capture, LLM-powered context extraction, smart idle detection, and automatic activity categorization.

## Features

- **Smart OCR Capture** - Extracts text from your screen using platform-native OCR (Apple Vision on macOS, Windows OCR API on Windows)
- **LLM Context Extraction** - Uses local LLMs (via Ollama) to intelligently extract document names, client codes, and project info from screen content
- **Idle Detection** - Automatically detects user inactivity and reduces resource usage
- **Remote Desktop Support** - Tracks activity inside remote desktop sessions (RDP, Citrix, TeamViewer, etc.)
- **OCR Diff Detection** - Skips redundant processing when screen content hasn't changed
- **Multi-Monitor Support** - Captures and processes all connected displays
- **Privacy Controls** - Configurable app/title exclusions and content redaction
- **150+ Categorization Rules** - Automatically categorizes activities

## Quick Start

### macOS

```bash
git clone https://github.com/kepptic/aw-watcher-enhanced.git
cd aw-watcher-enhanced
python3 -m venv venv && source venv/bin/activate
pip install -e ".[macos]"
aw-watcher-enhanced
```

### Windows

```powershell
git clone https://github.com/kepptic/aw-watcher-enhanced.git
cd aw-watcher-enhanced
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e ".[windows]"
aw-watcher-enhanced
```

See [docs/INSTALL-macos.md](docs/INSTALL-macos.md) or [docs/INSTALL-windows.md](docs/INSTALL-windows.md) for detailed installation guides.

## Requirements

- **Python 3.9+**
- **ActivityWatch** running ([download](https://activitywatch.net/downloads/))
- **macOS 11+** or **Windows 10/11**

### Optional
- **Ollama** for LLM enhancement ([download](https://ollama.ai/))
- **Qdrant** for RAG-based client detection ([Docker](https://qdrant.tech/))

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                     aw-watcher-enhanced                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │  Window  │   │   OCR    │   │   LLM    │   │  Event   │    │
│  │ Capture  │──▶│ Extract  │──▶│ Analyze  │──▶│  Store   │    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘    │
│       │              │              │              │           │
│       ▼              ▼              ▼              ▼           │
│   App/Title     Screen Text    Document,      ActivityWatch   │
│                 Keywords       Client,         Database       │
│                               Project                         │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                    Smart Features                         │ │
│  ├──────────────────────────────────────────────────────────┤ │
│  │  • Idle Detection (skip when inactive)                   │ │
│  │  • OCR Diff (skip when content unchanged)                │ │
│  │  • Remote Desktop (periodic capture inside RDP)          │ │
│  │  • Privacy Filters (exclude sensitive apps/content)      │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Configuration

Config file locations:
- **macOS**: `~/Library/Application Support/activitywatch/aw-watcher-enhanced/config.yaml`
- **Windows**: `%LOCALAPPDATA%\activitywatch\aw-watcher-enhanced\config.yaml`

### Example Configuration

```yaml
watcher:
  poll_time: 5.0

smart_capture:
  idle_threshold: 60.0        # Seconds before considered idle
  remote_desktop_interval: 10.0  # OCR interval inside RDP
  ocr_diff:
    similarity_threshold: 0.85   # Skip LLM if content >85% similar

ocr:
  enabled: true
  trigger: smart              # "window_change", "periodic", or "smart"
  engine: auto               # "auto", "apple_vision", "windows", "rapidocr"

llm:
  enabled: true
  model: "gemma3:4b"         # Ollama model to use
  timeout: 10.0

privacy:
  exclude_apps:
    - "1Password"
    - "Keychain Access"
  exclude_titles:
    - ".*[Pp]assword.*"
```

## Data Captured

Events are stored in ActivityWatch with rich metadata:

```json
{
  "timestamp": "2024-12-02T10:30:00.000Z",
  "duration": 45.5,
  "data": {
    "app": "Microsoft Excel",
    "title": "Budget Report.xlsx - Excel",
    "llm_document": "Budget Report.xlsx",
    "llm_client": "ACME01",
    "llm_project": "Q4 Planning",
    "ocr_keywords": ["budget", "revenue", "forecast"],
    "category": "Work/Data/Spreadsheets"
  }
}
```

## OCR Engines

| Platform | Engine | Speed | Notes |
|----------|--------|-------|-------|
| macOS | Apple Vision | ~100ms | Neural Engine accelerated |
| Windows | Windows OCR | ~200ms | Built-in, no install needed |
| Windows | RapidOCR | ~400ms | Better accuracy, optional |
| All | Tesseract | ~800ms | Fallback option |

## Command Line Options

```bash
aw-watcher-enhanced [OPTIONS]

Options:
  --verbose, -v    Enable debug logging
  --no-ocr         Disable OCR capture
  --no-llm         Disable LLM enhancement
  --testing        Use test server (port 5666)
  --help           Show help message
```

## Privacy & Security

- **100% Local Processing** - All OCR and LLM runs locally, no cloud APIs
- **Configurable Exclusions** - Exclude apps, titles, and URLs by pattern
- **Auto-Exclusions** - Password managers automatically excluded
- **Content Redaction** - Optional PII redaction (emails, phones, etc.)

## Performance

On Apple Silicon (M1/M2/M3):
- OCR: ~100ms per capture
- LLM: ~2-3s per analysis
- Memory: ~50-100MB
- CPU: <5% average

The watcher is designed to be lightweight with smart throttling:
- Skips OCR when user is idle
- Skips LLM when screen content hasn't changed
- Adaptive polling (slower when idle)

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the Mozilla Public License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [ActivityWatch](https://activitywatch.net/) - The amazing open-source time tracking foundation
- [Ollama](https://ollama.ai/) - Local LLM inference
- [ocrmac](https://github.com/straussmaximilian/ocrmac) - Apple Vision OCR wrapper
- [RapidOCR](https://github.com/RapidAI/RapidOCR) - Fast ONNX-based OCR

## Related Projects

- [aw-watcher-window](https://github.com/ActivityWatch/aw-watcher-window) - Standard window watcher
- [aw-watcher-afk](https://github.com/ActivityWatch/aw-watcher-afk) - AFK detection
- [aw-client](https://github.com/ActivityWatch/aw-client) - Python client library
