# aw-watcher-enhanced

[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![ActivityWatch](https://img.shields.io/badge/ActivityWatch-compatible-orange.svg)](https://activitywatch.net/)

An enhanced [ActivityWatch](https://activitywatch.net/) watcher with deep accessibility querying, browser URL merging, meeting detection, adaptive OCR, LLM-powered context extraction, and automatic activity categorization.

## Features

### Core Enrichment
- **Deep Accessibility API Querying** - Reads the focused UI element via macOS AXFocusedUIElement to capture which terminal tab, editor pane, or text field is active, with parent chain breadcrumbs (e.g. "Terminal > zsh")
- **Browser URL Merging** - Merges URL and domain from aw-watcher-web into browser events so you know exactly which page you were on
- **Context-Switch Metrics** - Tracks `focus_duration` (seconds in current window) and `switches_last_hour` (context switches per hour)
- **Activity Level Tracking** - Reports `activity_pct` (0-100%) based on mouse/keyboard activity over a rolling 5-minute window
- **Meeting Detection** - Detects active meetings in Zoom, Teams, Google Meet, FaceTime, WebEx, Slack huddles, Discord calls, and more

### Smart Capture
- **Adaptive OCR** - Only triggers OCR when primary data sources (Accessibility API, browser extension) return thin data; always fires for remote desktop apps; 5-minute safety net fallback when data is rich
- **Transition Capture** - Captures both the outgoing and incoming window on context switches for complete coverage
- **OCR Diff Detection** - Skips redundant LLM processing when screen content hasn't changed
- **Idle Detection** - Automatically reduces polling and skips OCR when user is inactive

### Analysis & Intelligence
- **LLM Context Extraction** - Uses local LLMs (via Ollama) to extract document names, client codes, project info, and breadcrumbs from screen content
- **150+ Categorization Rules** - Automatically categorizes activities into a hierarchy (Work/Development/Coding, Personal/Social Media, etc.)
- **Privacy Controls** - Configurable app/title/URL exclusions, auto-excluded password managers, optional PII redaction

### CLI Tools
- **Daily Summary** - `aw-watcher-enhanced --summary [date]` generates time-by-app, time-by-category, meeting time, and context switch reports
- **Retroactive Reclassification** - `aw-watcher-enhanced --reclassify --start DATE --end DATE` re-runs categorization rules on historical events

## Installation

### macOS (recommended)

```bash
# Clone and install
git clone https://github.com/kepptic/aw-watcher-enhanced.git
cd aw-watcher-enhanced
pip3 install -e .

# Register with ActivityWatch
# pip install creates aw-watcher-enhanced on PATH.
# aw-qt discovers it automatically via system module search.
```

Then add `aw-watcher-enhanced` to your `aw-qt.toml` autostart:

```
~/Library/Application Support/activitywatch/aw-qt/aw-qt.toml
```

```toml
[aw-qt]
autostart_modules = ["aw-server", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]
```

Restart ActivityWatch. The watcher appears in the tray menu.

> **Survives ActivityWatch updates** - The pip-installed executable and aw-qt.toml both live outside the .app bundle, so updating ActivityWatch won't break anything.

### macOS (installer script)

```bash
cd installer/macos
./install.sh             # Interactive: installs package + registers with aw-qt
./install.sh --service   # Also installs a launchd service as fallback
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

See [docs/INSTALL-macos.md](docs/INSTALL-macos.md) or [docs/INSTALL-windows.md](docs/INSTALL-windows.md) for detailed guides.

## Requirements

- **Python 3.9+**
- **ActivityWatch** running ([download](https://activitywatch.net/downloads/))
- **macOS 11+** or **Windows 10/11**

### Optional
- **Ollama** for LLM enhancement ([download](https://ollama.ai/))
- **Qdrant** for RAG-based client detection ([Docker](https://qdrant.tech/))

## How It Works

```
┌──────────────────────────────────────────────────────────────────────┐
│                      aw-watcher-enhanced                             │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐        │
│  │  Window   │  │ AX Focused│  │  Browser  │  │  Meeting  │        │
│  │  Capture  │  │  Element  │  │ URL Merge │  │ Detection │        │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘        │
│        └───────────────┴──────────────┴──────────────┘              │
│                            │                                         │
│                 ┌──────────▼──────────┐                              │
│                 │   Adaptive OCR      │  Only fires when data       │
│                 │   (if data is thin) │  from above is insufficient │
│                 └──────────┬──────────┘                              │
│                            │                                         │
│                 ┌──────────▼──────────┐                              │
│                 │   LLM Analysis      │  Document, client, project  │
│                 │   (via Ollama)      │  extraction from OCR text   │
│                 └──────────┬──────────┘                              │
│                            │                                         │
│                 ┌──────────▼──────────┐                              │
│                 │   Categorize +      │  150+ rules, privacy        │
│                 │   Store Event       │  filters, then heartbeat    │
│                 └─────────────────────┘                              │
│                                                                      │
│  Metrics: focus_duration, switches_last_hour, activity_pct,          │
│           in_meeting, meeting_app                                    │
└──────────────────────────────────────────────────────────────────────┘
```

## Event Data

Events are stored in ActivityWatch with rich metadata:

```json
{
  "timestamp": "2026-03-03T10:30:00.000Z",
  "duration": 45.5,
  "data": {
    "app": "Code",
    "title": "main.py - aw-watcher-enhanced",
    "focused_element_role": "AXTextField",
    "focused_element_context": "Terminal > zsh",
    "url": "https://github.com/kepptic/aw-watcher-enhanced",
    "domain": "github.com",
    "focus_duration": 120.5,
    "switches_last_hour": 42,
    "activity_pct": 87.3,
    "in_meeting": false,
    "llm_document": "main.py",
    "llm_project": "aw-watcher-enhanced",
    "ocr_keywords": ["def", "capture_state", "window_data"],
    "category": "Work/Development/Coding"
  }
}
```

| Field | Source | Description |
|-------|--------|-------------|
| `app`, `title` | Window capture | Active application and window title |
| `focused_element_role` | Accessibility API | UI element type (AXTextField, AXWebArea, etc.) |
| `focused_element_context` | AX parent chain | Breadcrumb path (e.g. "Terminal > zsh") |
| `url`, `domain`, `tab_title` | aw-watcher-web merge | Browser URL data (when browser is active) |
| `focus_duration` | Context tracker | Seconds spent in current window |
| `switches_last_hour` | Context tracker | Number of app/window switches in last hour |
| `activity_pct` | Idle detector | Mouse/keyboard activity percentage (0-100) |
| `in_meeting`, `meeting_app` | Meeting detector | Whether user is in a video/voice call |
| `llm_document`, `llm_client`, `llm_project` | LLM (Ollama) | Extracted document/client/project context |
| `ocr_keywords`, `ocr_entities` | OCR engine | Keywords and entities from screen text |
| `category` | Rule engine | Activity category (Work/Development/Coding, etc.) |
| `document` | Title parser | Parsed file/document context from window title |

## Command Line

```bash
# Run the watcher
aw-watcher-enhanced                          # Normal mode (with auto-restart watchdog)
aw-watcher-enhanced --verbose                # Debug logging
aw-watcher-enhanced --no-ocr                 # Disable OCR capture
aw-watcher-enhanced --no-llm                 # Disable LLM enhancement
aw-watcher-enhanced --no-restart             # Run directly (no watchdog)

# Daily summary
aw-watcher-enhanced --summary                # Today's summary
aw-watcher-enhanced --summary yesterday      # Yesterday's summary
aw-watcher-enhanced --summary 2026-03-01     # Specific date
aw-watcher-enhanced --summary today --summary-format json  # JSON output

# Retroactive reclassification
aw-watcher-enhanced --reclassify --start 2026-03-01 --end 2026-03-03 --dry-run  # Preview
aw-watcher-enhanced --reclassify --start 2026-03-01 --end 2026-03-03            # Apply
```

## Configuration

Config file locations:
- **macOS**: `~/Library/Application Support/activitywatch/aw-watcher-enhanced/config.yaml`
- **Windows**: `%LOCALAPPDATA%\activitywatch\aw-watcher-enhanced\config.yaml`

```yaml
watcher:
  poll_time: 5.0
  pulsetime: 6.0

smart_capture:
  idle_threshold: 60.0
  remote_desktop_interval: 10.0
  ocr_diff:
    similarity_threshold: 0.85
    min_change_chars: 50

ocr:
  enabled: true
  trigger: adaptive       # adaptive, smart, window_change, periodic
  periodic_interval: 30
  adaptive_fallback_interval: 300  # 5-min safety net when data is rich
  engine: auto

browser:
  enabled: true           # Merge URL data from aw-watcher-web

meeting:
  enabled: true           # Detect Zoom, Teams, Meet, etc.
  detect_subprocess: true  # Check for Zoom CptHost, etc.

llm:
  enabled: true
  model: "gemma3:4b"
  timeout: 10.0

privacy:
  exclude_apps:
    - "1Password"
    - "Keychain Access"
  exclude_titles:
    - ".*[Pp]assword.*"
```

## OCR Engines

| Platform | Engine | Speed | Notes |
|----------|--------|-------|-------|
| macOS | Apple Vision | ~100ms | Neural Engine accelerated |
| Windows | Windows OCR | ~200ms | Built-in, no install needed |
| Windows | RapidOCR | ~400ms | Better accuracy, optional |
| All | Tesseract | ~800ms | Fallback option |

## Privacy & Security

- **100% Local Processing** - All OCR and LLM runs locally, no cloud APIs
- **Configurable Exclusions** - Exclude apps, titles, and URLs by pattern
- **Auto-Exclusions** - Password managers automatically excluded
- **Content Redaction** - Optional PII redaction (emails, phones, SSNs, credit cards)

## Performance

On Apple Silicon (M1/M2/M3):
- OCR: ~100ms per capture
- LLM: ~2-3s per analysis
- Memory: ~50-100MB
- CPU: <5% average

The watcher is designed to be lightweight with smart throttling:
- Adaptive OCR only fires when primary data sources are insufficient
- Skips LLM when screen content hasn't changed
- Reduces polling when user is idle
- Auto-restart watchdog recovers from crashes

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
