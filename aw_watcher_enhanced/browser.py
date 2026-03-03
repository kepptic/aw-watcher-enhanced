"""
Browser data merging for aw-watcher-enhanced.

Queries aw-watcher-web buckets to merge URL/domain data into events
when the active app is a browser.
"""

import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from aw_client import ActivityWatchClient

logger = logging.getLogger(__name__)

# Browser app names (case-insensitive matching)
_BROWSER_APPS = frozenset({
    "google chrome", "chrome",
    "firefox", "mozilla firefox",
    "safari",
    "microsoft edge", "edge",
    "brave browser", "brave",
    "arc",
    "opera", "opera gx",
    "vivaldi",
    "chromium",
    "orion",
    "zen browser", "zen",
})


def is_browser_app(app_name: str) -> bool:
    """Check if the given app name is a known browser."""
    if not app_name:
        return False
    return app_name.lower().strip() in _BROWSER_APPS


class BrowserDataMerger:
    """Merges browser URL data from aw-watcher-web into enhanced events."""

    def __init__(self, client: ActivityWatchClient):
        self.client = client
        self._web_buckets: List[str] = []
        self._buckets_last_refresh: float = 0
        self._bucket_refresh_interval: float = 300  # 5 minutes
        self._last_result: Optional[Dict[str, str]] = None
        self._last_result_time: float = 0
        self._cache_ttl: float = 2.0  # Avoid hammering aw-server

    def _discover_web_buckets(self) -> List[str]:
        """Find aw-watcher-web-* buckets."""
        now = time.time()
        if now - self._buckets_last_refresh < self._bucket_refresh_interval:
            return self._web_buckets

        try:
            buckets = self.client.get_buckets()
            self._web_buckets = [
                bid for bid in buckets
                if bid.startswith("aw-watcher-web")
            ]
            self._buckets_last_refresh = now
            if self._web_buckets:
                logger.debug(f"Found web buckets: {self._web_buckets}")
            else:
                logger.debug("No aw-watcher-web buckets found")
        except Exception as e:
            logger.debug(f"Error discovering web buckets: {e}")

        return self._web_buckets

    def get_browser_data(self, timestamp=None) -> Optional[Dict[str, str]]:
        """Get the most recent browser URL/title data.

        Args:
            timestamp: Event timestamp (unused currently, for future time-based queries).

        Returns:
            Dict with 'url', 'domain', 'tab_title' keys, or None.
        """
        # Check cache
        now = time.time()
        if now - self._last_result_time < self._cache_ttl and self._last_result:
            return self._last_result

        buckets = self._discover_web_buckets()
        if not buckets:
            return None

        for bucket_id in buckets:
            try:
                events = self.client.get_events(bucket_id, limit=1)
                if not events:
                    continue

                event = events[0]
                data = event.data
                url = data.get("url", "")
                if not url:
                    continue

                parsed = urlparse(url)
                result = {
                    "url": url,
                    "domain": parsed.netloc or "",
                    "tab_title": data.get("title", ""),
                }

                self._last_result = result
                self._last_result_time = now
                return result

            except Exception as e:
                logger.debug(f"Error querying bucket {bucket_id}: {e}")
                continue

        return None
