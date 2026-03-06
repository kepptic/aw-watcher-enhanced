"""
Background enrichment worker for aw-watcher-enhanced.

Runs the full capture pipeline (AX, browser, meeting, OCR, LLM, etc.)
in a background thread, triggered by window changes or periodic timer.
Never blocks the fast heartbeat loop.

Stores enriched data in a shared variable that the heartbeat loop
reads and merges into its events — single bucket, no separate writes.
"""

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .main import EnhancedWatcher

logger = logging.getLogger(__name__)


class EnrichmentWorker:
    """Background worker that captures enriched window state.

    Triggered by window changes from the heartbeat loop, or
    periodically (every periodic_interval seconds) for the same window.
    Stores result in watcher's shared state for the heartbeat to pick up.
    """

    def __init__(
        self,
        watcher: "EnhancedWatcher",
        periodic_interval: float = 15.0,
    ):
        self.watcher = watcher
        self.periodic_interval = periodic_interval
        self._window_changed = threading.Event()
        self._thread = None
        self._running = False

    def start(self):
        """Start the enrichment worker thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="enrichment", daemon=True
        )
        self._thread.start()
        logger.info(
            f"Enrichment worker started (periodic={self.periodic_interval}s)"
        )

    def stop(self):
        """Stop the enrichment worker thread."""
        self._running = False
        self._window_changed.set()  # Wake up the thread
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("Enrichment worker stopped")

    def notify_window_change(self):
        """Signal that the active window has changed."""
        self._window_changed.set()

    def _run(self):
        """Main enrichment loop."""
        while self._running and self.watcher.running:
            try:
                # Wait for window change or periodic timeout
                changed = self._window_changed.wait(
                    timeout=self.periodic_interval
                )
                if not self._running or not self.watcher.running:
                    break

                if changed:
                    self._window_changed.clear()

                # Capture enriched state using the watcher's full pipeline
                data = self.watcher.capture_state()
                if data:
                    app = data.get("app", "")
                    title = data.get("title", "")

                    # Store enriched data for heartbeat loop to pick up
                    with self.watcher._enriched_state_lock:
                        self.watcher._enriched_state = data
                        self.watcher._enriched_window_key = (app, title)

                    # Update watcher's state tracking for OCR change detection
                    self.watcher.last_window_data = data

                    logger.debug(
                        f"Enrichment: {app} - {title[:50]} "
                        f"({'change' if changed else 'periodic'}) "
                        f"keys={sorted(data.keys())}"
                    )

            except Exception as e:
                logger.error(f"Enrichment error: {e}", exc_info=True)
