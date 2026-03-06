"""
File activity tracking for aw-watcher-enhanced.

Monitors file system changes in key directories to track which files
the user is editing. Uses watchdog for cross-platform FSEvents support.
"""

import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# File extensions we care about (code, documents, config)
_TRACKED_EXTENSIONS = frozenset(
    {
        # Code
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".java",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".c",
        ".cpp",
        ".h",
        ".cs",
        ".swift",
        ".kt",
        ".scala",
        ".r",
        ".sql",
        ".sh",
        ".bash",
        ".zsh",
        # Web
        ".html",
        ".css",
        ".scss",
        ".less",
        ".vue",
        ".svelte",
        # Config
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".env",
        ".xml",
        # Documents
        ".md",
        ".txt",
        ".rst",
        ".tex",
        ".csv",
        # Notebooks
        ".ipynb",
    }
)

# Directories/patterns to ignore
_IGNORE_PATTERNS = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "target",
    }
)


class FileActivityTracker:
    """Tracks file modifications in watched directories.

    Uses watchdog to monitor filesystem events (FSEvents on macOS,
    inotify on Linux). Records recently modified files with timestamps.
    """

    def __init__(self, max_events: int = 50):
        self._max_events = max_events
        self._recent_files: deque = deque(maxlen=max_events)
        self._lock = threading.Lock()
        self._observer = None
        self._running = False
        self._available = False

        try:
            import watchdog  # noqa: F401

            self._available = True
        except ImportError:
            logger.info(
                "watchdog not available for file tracking. "
                "Install: pip install watchdog"
            )

    def start(self, watch_dirs: Optional[List[str]] = None):
        """Start watching directories for file changes.

        Args:
            watch_dirs: Directories to watch. Defaults to ~/Documents,
                       ~/Desktop, and common project dirs.
        """
        if not self._available:
            return

        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            return

        if watch_dirs is None:
            home = str(Path.home())
            watch_dirs = [
                os.path.join(home, "Documents"),
                os.path.join(home, "Desktop"),
                os.path.join(home, "Projects"),
                os.path.join(home, "Developer"),
                os.path.join(home, "Code"),
            ]

        # Filter to existing directories
        watch_dirs = [d for d in watch_dirs if os.path.isdir(d)]
        if not watch_dirs:
            logger.info("No valid watch directories found")
            return

        class Handler(FileSystemEventHandler):
            def __init__(self, tracker):
                self.tracker = tracker

            def on_modified(self, event):
                if not event.is_directory:
                    self.tracker._on_file_change(
                        event.src_path, "modified"
                    )

            def on_created(self, event):
                if not event.is_directory:
                    self.tracker._on_file_change(
                        event.src_path, "created"
                    )

        handler = Handler(self)
        self._observer = Observer()
        self._running = True

        for watch_dir in watch_dirs:
            try:
                self._observer.schedule(
                    handler, watch_dir, recursive=True
                )
                logger.debug(f"Watching directory: {watch_dir}")
            except Exception as e:
                logger.debug(f"Cannot watch {watch_dir}: {e}")

        self._observer.daemon = True
        self._observer.start()
        logger.info(
            f"File activity tracker started ({len(watch_dirs)} dirs)"
        )

    def stop(self):
        """Stop watching for file changes."""
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2.0)

    def get_recent_files(self, limit: int = 10) -> List[Dict]:
        """Get recently modified files (thread-safe).

        Returns:
            List of {path, action, timestamp} dicts, most recent first.
        """
        with self._lock:
            files = list(self._recent_files)
        # Most recent first
        files.reverse()
        return files[:limit]

    def _on_file_change(self, path: str, action: str):
        """Handle a file change event."""
        # Check extension
        ext = os.path.splitext(path)[1].lower()
        if ext not in _TRACKED_EXTENSIONS:
            return

        # Check if in an ignored directory
        parts = path.split(os.sep)
        if any(p in _IGNORE_PATTERNS for p in parts):
            return

        # Shorten path for storage (relative to home)
        home = str(Path.home())
        display_path = path
        if path.startswith(home):
            display_path = "~" + path[len(home) :]

        entry = {
            "path": display_path,
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        with self._lock:
            # Deduplicate: don't add if same file was just recorded
            if self._recent_files:
                last = self._recent_files[-1]
                if last["path"] == display_path:
                    # Update timestamp instead of duplicating
                    self._recent_files[-1] = entry
                    return

            self._recent_files.append(entry)
