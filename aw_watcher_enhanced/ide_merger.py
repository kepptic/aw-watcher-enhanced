"""
IDE data merger for aw-watcher-enhanced.

Reads events from aw-watcher-vscode (or similar IDE watchers) and merges
the rich editor context (file, language, branch, project, cursor position,
debugging state, etc.) into our enriched events.

This gives us precise IDE context instead of title-parsing heuristics.
"""

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class IDEDataMerger:
    """Reads the latest IDE watcher event and provides it for merging."""

    # How stale an IDE event can be before we ignore it (seconds)
    MAX_EVENT_AGE = 30.0

    # IDE bucket patterns to look for
    IDE_BUCKET_PATTERNS = [
        "aw-watcher-vscode",
        "aw-watcher-sublime",
        "aw-watcher-jetbrains",
        "aw-watcher-vim",
        "aw-watcher-emacs",
    ]

    # Apps that are IDEs (to know when to query IDE buckets)
    IDE_APP_PATTERN = re.compile(
        r"code|visual\s*studio\s*code|cursor|sublime|pycharm|idea|webstorm|"
        r"phpstorm|rider|goland|clion|android\s*studio|vim|nvim|emacs|atom",
        re.IGNORECASE,
    )

    def __init__(self, client: Any, hostname: str):
        self._client = client
        self._hostname = hostname
        self._ide_buckets: Dict[str, str] = {}  # bucket_name -> bucket_id
        self._last_scan_time = 0.0
        self._scan_interval = 60.0  # Re-scan buckets every 60s
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time = 0.0
        self._cache_ttl = 2.0  # Cache for 2s to avoid hammering AW API

    def _scan_buckets(self):
        """Find IDE watcher buckets on the AW server."""
        now = time.time()
        if now - self._last_scan_time < self._scan_interval:
            return

        self._last_scan_time = now
        try:
            buckets = self._client.get_buckets()
            self._ide_buckets = {}
            for bucket_id in buckets:
                for pattern in self.IDE_BUCKET_PATTERNS:
                    if pattern in bucket_id:
                        self._ide_buckets[pattern] = bucket_id
                        break

            if self._ide_buckets:
                logger.debug(f"Found IDE buckets: {list(self._ide_buckets.values())}")
        except Exception as e:
            logger.debug(f"Error scanning IDE buckets: {e}")

    def is_ide_app(self, app_name: str) -> bool:
        """Check if the given app name is an IDE."""
        return bool(self.IDE_APP_PATTERN.search(app_name))

    def get_ide_data(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Get the latest IDE watcher event data if recent enough.

        Args:
            app_name: Current focused app name

        Returns:
            Dict with IDE context fields, or None if no recent data
        """
        if not self.is_ide_app(app_name):
            return None

        # Check cache
        now = time.time()
        if self._cache is not None and now - self._cache_time < self._cache_ttl:
            return self._cache

        self._scan_buckets()

        if not self._ide_buckets:
            return None

        # Try each IDE bucket
        for bucket_name, bucket_id in self._ide_buckets.items():
            try:
                events = self._client.get_events(bucket_id, limit=1)
                if not events:
                    continue

                event = events[0]
                event_ts = event.timestamp

                # Check freshness
                if isinstance(event_ts, datetime):
                    if event_ts.tzinfo is None:
                        event_ts = event_ts.replace(tzinfo=timezone.utc)
                    age = (datetime.now(timezone.utc) - event_ts).total_seconds()
                else:
                    age = self.MAX_EVENT_AGE + 1  # Skip non-datetime

                if age > self.MAX_EVENT_AGE:
                    continue

                data = event.data
                result = self._extract_ide_fields(data, bucket_name)
                if result:
                    self._cache = result
                    self._cache_time = now
                    return result

            except Exception as e:
                logger.debug(f"Error reading IDE bucket {bucket_id}: {e}")

        self._cache = None
        self._cache_time = now
        return None

    def _extract_ide_fields(
        self, data: Dict[str, Any], source: str
    ) -> Optional[Dict[str, Any]]:
        """Extract and normalize fields from an IDE event.

        Maps the various IDE watcher field names to our standard field names.
        """
        if not data:
            return None

        result: Dict[str, Any] = {}

        # Core fields (all IDE watchers should have these)
        if data.get("file") and data["file"] != "unknown":
            result["ide_file"] = data["file"]
        if data.get("language") and data["language"] != "unknown":
            result["ide_language"] = data["language"]
        if data.get("project") and data["project"] != "unknown":
            result["ide_project"] = data["project"]
        if data.get("branch") and data["branch"] != "unknown":
            result["ide_branch"] = data["branch"]

        # Enhanced fields (from our improved extension)
        if data.get("relative_path"):
            result["ide_relative_path"] = data["relative_path"]
        if data.get("cursor_line"):
            result["ide_cursor_line"] = data["cursor_line"]
        if data.get("lines_in_file"):
            result["ide_lines_in_file"] = data["lines_in_file"]
        if data.get("git_dirty_count") is not None:
            result["ide_git_dirty"] = data["git_dirty_count"]
        if data.get("git_remote"):
            result["ide_git_remote"] = data["git_remote"]
        if data.get("is_debugging"):
            result["ide_debugging"] = True
            if data.get("debug_type"):
                result["ide_debug_type"] = data["debug_type"]
        if data.get("open_files"):
            result["ide_open_files"] = data["open_files"]
        if data.get("open_file_count"):
            result["ide_open_file_count"] = data["open_file_count"]
        if data.get("active_terminal"):
            result["ide_active_terminal"] = data["active_terminal"]
        if data.get("terminal_count"):
            result["ide_terminal_count"] = data["terminal_count"]
        if data.get("is_terminal"):
            result["ide_is_terminal"] = True
            if data.get("terminal_name"):
                result["ide_terminal_name"] = data["terminal_name"]
        if data.get("workspace_folders"):
            result["ide_workspaces"] = data["workspace_folders"]

        # Override doc_project with IDE's more accurate project name
        if result.get("ide_project"):
            result["doc_project"] = result["ide_project"]

        result["ide_source"] = source

        return result if len(result) > 1 else None  # >1 because ide_source always set
