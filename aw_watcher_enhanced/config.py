"""
Configuration management for aw-watcher-enhanced.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CONFIG: Dict[str, Any] = {
    "watcher": {
        "poll_time": 5.0,
        "pulsetime": 6.0,
    },
    "smart_capture": {
        "idle_threshold": 60.0,  # seconds before considered idle
        "idle_poll_time": 30.0,  # poll interval when idle
        "min_ocr_interval": 5.0,  # minimum seconds between OCR captures
        # Tiered capture intervals
        "active_window_interval": 5.0,  # capture active window on change
        "active_monitor_interval": 30.0,  # capture full monitor every 30s
        "full_capture_interval": 120.0,  # capture all monitors every 2 min
        # OCR diff detection - skip LLM calls when content hasn't changed
        "ocr_diff": {
            "similarity_threshold": 0.85,  # 0-1, higher = more similar required to skip
            "min_change_chars": 50,  # minimum char diff to trigger LLM
        },
        # Remote desktop - force frequent OCR since internal window changes aren't detectable
        "remote_desktop_interval": 10.0,  # OCR every 10s when in remote desktop
        "remote_desktop_apps": [
            "Microsoft Remote Desktop",
            "Windows App",
            "Citrix Viewer",
            "Citrix Workspace",
            "VMware Horizon",
            "Parallels Desktop",
            "TeamViewer",
            "AnyDesk",
            "Chrome Remote Desktop",
            "Royal TSX",
            "Jump Desktop",
            "Screens",
            "VNC Viewer",
            "RealVNC",
        ],
    },
    "ocr": {
        "enabled": True,
        "trigger": "smart",  # "window_change", "periodic", "both", or "smart"
        "periodic_interval": 30,  # seconds between OCR when same window
        "engine": "auto",  # "auto", "apple_vision", "windows", "rapidocr", "tesseract"
        "extract_mode": "keywords",  # "keywords", "entities", "full_text"
        "max_keywords": 20,
    },
    "llm": {
        "model": "gemma3:4b",
        "timeout": 10.0,
        "enabled": True,
    },
    "browser": {
        "enabled": False,  # Requires browser extension
        "merge_with_window": True,
    },
    "privacy": {
        "exclude_apps": [
            "1Password.exe",
            "KeePass.exe",
            "LastPass.exe",
            "Bitwarden.exe",
        ],
        "exclude_titles": [
            r".*[Pp]assword.*",
            r".*[Pp]rivate.*",
            r".*[Ss]ecret.*",
        ],
        "exclude_urls": [
            r".*bank.*",
            r".*paypal.*",
        ],
        "redact_patterns": [],  # Applied to OCR text
    },
    "categorization": {
        "enabled": True,
        "rules": [],  # Loaded from rules file or defined here
        "client_keywords": {},  # client_name -> list of keywords
        "use_rag": True,  # Use RAG database for client detection
    },
    "qdrant": {
        "enabled": True,
        "host": "localhost",
        "port": 6333,
        "cache_ttl_minutes": 30,
    },
}


def get_config_dir() -> Path:
    """Get the configuration directory for aw-watcher-enhanced."""
    if os.name == "nt":  # Windows
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif os.name == "posix":
        if "darwin" in os.uname().sysname.lower():  # macOS
            base = Path.home() / "Library" / "Application Support"
        else:  # Linux
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    else:
        base = Path.home()

    config_dir = base / "activitywatch" / "aw-watcher-enhanced"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def load_config() -> Dict[str, Any]:
    """Load configuration from file or return defaults."""
    config_dir = get_config_dir()
    config_file = config_dir / "config.yaml"

    config = DEFAULT_CONFIG.copy()

    if config_file.exists():
        try:
            import yaml

            with open(config_file, "r") as f:
                user_config = yaml.safe_load(f)

            if user_config:
                # Deep merge user config into defaults
                config = deep_merge(config, user_config)
                logger.info(f"Loaded config from {config_file}")
        except ImportError:
            logger.warning("PyYAML not installed, using default config")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    else:
        # Create default config file
        try:
            import yaml

            with open(config_file, "w") as f:
                yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
            logger.info(f"Created default config at {config_file}")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Could not create default config: {e}")

    return config


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
