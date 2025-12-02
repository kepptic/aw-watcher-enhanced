#!/usr/bin/env python3
"""
aw-watcher-enhanced - Enhanced ActivityWatch Watcher

This watcher extends the standard window watcher with:
- Rich document/file context from window titles
- OCR-based screen content capture (optional)
- Semantic categorization of activities
- Client/project attribution

Usage:
    python -m aw_watcher_enhanced [--testing] [--verbose] [--no-ocr]
"""

import argparse
import logging
import signal
import sys
from datetime import datetime, timezone
from time import sleep
from typing import Optional

from aw_client import ActivityWatchClient
from aw_core.models import Event

from .categorizer import categorize_event
from .config import load_config
from .document import parse_document_context
from .privacy import apply_privacy_filters
from .window import get_current_window

# Try to import OCR module (optional)
try:
    from .ocr import OCR_AVAILABLE, capture_and_ocr, capture_screen, ocr_image_structured
except ImportError:
    OCR_AVAILABLE = False

# Try to import LLM enhancement (optional)
try:
    from .llm_ocr import summarize_ocr_with_llm

    LLM_OCR_AVAILABLE = True
except ImportError:
    LLM_OCR_AVAILABLE = False

# Try to import smart capture (optional)
try:
    from .smart_capture import IdleDetector, OCRDiffDetector, SmartCaptureManager

    SMART_CAPTURE_AVAILABLE = True
except ImportError:
    SMART_CAPTURE_AVAILABLE = False
    OCRDiffDetector = None

logger = logging.getLogger(__name__)

WATCHER_NAME = "aw-watcher-enhanced"


class EnhancedWatcher:
    """Main watcher class that orchestrates all capture modules."""

    def __init__(self, testing: bool = False, enable_ocr: bool = True, enable_llm: bool = True):
        self.testing = testing
        self.enable_ocr = enable_ocr and OCR_AVAILABLE
        self.enable_llm = enable_llm and LLM_OCR_AVAILABLE
        self.running = False
        self.config = load_config()

        # Initialize AW client
        self.client = ActivityWatchClient(WATCHER_NAME, testing=testing)
        self.bucket_id = f"{WATCHER_NAME}_{self.client.client_hostname}"

        # Track state for change detection
        self.last_window_data = None
        self.last_ocr_time = None
        self.last_ocr_result = None  # Cache last OCR/LLM result

        # LLM config
        self.llm_model = self.config.get("llm", {}).get("model", "gemma3:4b")
        self.llm_timeout = self.config.get("llm", {}).get("timeout", 10.0)

        # Smart capture config
        self.idle_threshold = self.config.get("smart_capture", {}).get("idle_threshold", 60.0)
        self.idle_poll_time = self.config.get("smart_capture", {}).get("idle_poll_time", 30.0)

        # Initialize idle detector
        self.idle_detector = None
        if SMART_CAPTURE_AVAILABLE:
            self.idle_detector = IdleDetector()
            self.idle_detector.set_threshold(self.idle_threshold)
            logger.info(f"Idle detection enabled (threshold: {self.idle_threshold}s)")

        # Initialize OCR diff detector to skip redundant LLM calls
        self.ocr_diff_detector = None
        if SMART_CAPTURE_AVAILABLE and OCRDiffDetector:
            diff_config = self.config.get("smart_capture", {}).get("ocr_diff", {})
            self.ocr_diff_detector = OCRDiffDetector(
                similarity_threshold=diff_config.get("similarity_threshold", 0.85),
                min_change_chars=diff_config.get("min_change_chars", 50),
            )
            logger.info("OCR diff detection enabled (skips LLM for unchanged content)")

        logger.info(f"Initialized {WATCHER_NAME}")
        logger.info(f"OCR enabled: {self.enable_ocr}")
        logger.info(f"LLM enhancement enabled: {self.enable_llm}")
        logger.info(f"Testing mode: {self.testing}")

    def setup(self):
        """Create bucket and prepare for capture."""
        event_type = "enhanced_window"
        self.client.create_bucket(self.bucket_id, event_type, queued=True)
        logger.info(f"Created bucket: {self.bucket_id}")

    def capture_state(self) -> Optional[dict]:
        """Capture current window state with all enhancements."""
        # Step 1: Get basic window info
        window_data = get_current_window()
        if not window_data:
            return None

        # Step 2: Parse document context from title
        document_context = parse_document_context(
            app=window_data.get("app", ""), title=window_data.get("title", "")
        )
        if document_context:
            window_data["document"] = document_context

        # Step 3: OCR capture (if enabled and triggered)
        if self.enable_ocr and self._should_capture_ocr(window_data):
            ocr_config = self.config.get("ocr", {})

            # Use structured OCR to get position-based text extraction
            image = capture_screen(window_only=False)
            structured_ocr = None
            if image:
                structured_ocr = ocr_image_structured(image)

            # Also get standard OCR data for keywords/entities
            ocr_config_with_text = {**ocr_config, "extract_mode": "full_text"}
            ocr_data = capture_and_ocr(ocr_config_with_text)
            if ocr_data:
                window_data["ocr_keywords"] = ocr_data.get("keywords", [])
                if ocr_data.get("entities"):
                    window_data["ocr_entities"] = ocr_data["entities"]

                # Add barcode data if detected
                if structured_ocr and structured_ocr.get("barcodes"):
                    window_data["barcodes"] = structured_ocr["barcodes"]

                # Step 3b: LLM enhancement of OCR text
                if self.enable_llm and ocr_data.get("text"):
                    # Prepare enhanced context for LLM including title bar text
                    ocr_text = ocr_data["text"]
                    if structured_ocr and structured_ocr.get("title_bar"):
                        # Prepend title bar text for better document detection
                        title_bar_text = structured_ocr["title_bar"]
                        ocr_text = f"[TITLE BAR: {title_bar_text}]\n\n{ocr_text}"

                    # Check if OCR content changed enough to warrant LLM call
                    should_run_llm = True
                    if self.ocr_diff_detector:
                        should_run_llm, diff_reason = self.ocr_diff_detector.should_run_llm(
                            ocr_text, window_data
                        )
                        if not should_run_llm:
                            # Reuse cached LLM result if content unchanged
                            if self.last_ocr_result:
                                llm_result = self.last_ocr_result
                                logger.debug(f"Reusing cached LLM result ({diff_reason})")
                            else:
                                llm_result = None
                        else:
                            llm_result = None  # Will run LLM below

                    if should_run_llm:
                        llm_result = summarize_ocr_with_llm(
                            ocr_text,
                            model=self.llm_model,
                            timeout=self.llm_timeout,
                        )
                        # Cache result for potential reuse
                        if llm_result:
                            self.last_ocr_result = llm_result
                    else:
                        llm_result = self.last_ocr_result
                    if llm_result:
                        # Merge LLM insights into window_data
                        # Filter out null/None values and prompt echoes
                        def is_valid(val):
                            if not val:
                                return False
                            val_str = str(val).lower()
                            return (
                                val_str not in ("null", "none", "") and "otherwise" not in val_str
                            )

                        doc = llm_result.get("document")
                        if is_valid(doc):
                            window_data["llm_document"] = doc
                        client = llm_result.get("client")
                        if is_valid(client):
                            window_data["llm_client"] = client
                        project = llm_result.get("project")
                        if is_valid(project):
                            window_data["llm_project"] = project
                        url = llm_result.get("url")
                        if is_valid(url):
                            window_data["llm_url"] = url
                        breadcrumb = llm_result.get("breadcrumb")
                        if is_valid(breadcrumb):
                            window_data["llm_breadcrumb"] = breadcrumb
                        page = llm_result.get("page")
                        if is_valid(page):
                            window_data["llm_page"] = page
                        if llm_result.get("keywords"):
                            # Merge LLM keywords with OCR keywords
                            llm_keywords = llm_result["keywords"]
                            if isinstance(llm_keywords, list):
                                llm_keywords = [k for k in llm_keywords if is_valid(k)]
                                window_data["ocr_keywords"] = list(
                                    set(window_data.get("ocr_keywords", []) + llm_keywords)
                                )[:25]
                        logger.debug(
                            f"LLM: doc={llm_result.get('document')}, client={llm_result.get('client')}, page={llm_result.get('page')}"
                        )
            self.last_ocr_time = datetime.now(timezone.utc)

        # Step 4: Apply privacy filters
        window_data = apply_privacy_filters(window_data, self.config.get("privacy", {}))
        if window_data is None:
            # Event was filtered out entirely
            return None

        # Step 5: Categorize the activity
        category = categorize_event(window_data, self.config.get("categorization", {}))
        if category:
            window_data["category"] = category

        return window_data

    def _is_remote_desktop_app(self, app_name: str) -> bool:
        """Check if the current app is a remote desktop application."""
        if not app_name:
            return False

        smart_config = self.config.get("smart_capture", {})
        remote_apps = smart_config.get("remote_desktop_apps", [])

        app_lower = app_name.lower()
        for remote_app in remote_apps:
            if remote_app.lower() in app_lower:
                return True
        return False

    def _should_capture_ocr(self, current_data: dict) -> bool:
        """
        Determine if OCR capture should be triggered.

        Smart capture logic:
        1. Skip if user is idle (no mouse/keyboard for idle_threshold seconds)
        2. Capture on window/app change
        3. Capture more frequently if in remote desktop (can't detect internal changes)
        4. Capture periodically if same window (but less frequently)
        """
        # Check if user is idle - skip OCR to save resources
        if self.idle_detector and self.idle_detector.is_idle():
            idle_secs = self.idle_detector.get_idle_seconds()
            logger.debug(f"User idle ({idle_secs:.0f}s), skipping OCR")
            return False

        ocr_config = self.config.get("ocr", {})
        smart_config = self.config.get("smart_capture", {})
        trigger = ocr_config.get("trigger", "window_change")

        current_app = current_data.get("app", "")

        # Check if window changed
        window_changed = False
        if self.last_window_data is None:
            window_changed = True
        elif current_data.get("app") != self.last_window_data.get("app") or current_data.get(
            "title"
        ) != self.last_window_data.get("title"):
            window_changed = True

        # Reset OCR diff detector on window change to force fresh LLM analysis
        if window_changed and self.ocr_diff_detector:
            self.ocr_diff_detector.force_next_llm()
            logger.debug("Window changed, resetting OCR diff detector")

        # Special handling for remote desktop apps - capture more frequently
        # since we can't detect window changes inside the remote session
        if self._is_remote_desktop_app(current_app):
            remote_interval = smart_config.get("remote_desktop_interval", 10.0)
            if self.last_ocr_time is None:
                logger.debug(f"Remote desktop detected ({current_app}), capturing")
                return True
            elapsed = (datetime.now(timezone.utc) - self.last_ocr_time).total_seconds()
            if elapsed >= remote_interval:
                logger.debug(
                    f"Remote desktop ({current_app}), periodic capture after {elapsed:.0f}s"
                )
                return True
            return False

        if trigger == "window_change":
            return window_changed

        elif trigger == "periodic":
            # Capture on interval
            interval = ocr_config.get("periodic_interval", 30)
            if self.last_ocr_time is None:
                return True
            elapsed = (datetime.now(timezone.utc) - self.last_ocr_time).total_seconds()
            return elapsed >= interval

        elif trigger == "both" or trigger == "smart":
            # Smart: capture on window change OR periodic (longer interval for same window)
            if window_changed:
                return True

            # Same window - use longer interval
            interval = ocr_config.get("periodic_interval", 30)
            if self.last_ocr_time is None:
                return True
            elapsed = (datetime.now(timezone.utc) - self.last_ocr_time).total_seconds()
            return elapsed >= interval

        return False

    def _get_adaptive_poll_time(self) -> float:
        """Get adaptive poll time based on user activity."""
        base_poll = self.config.get("watcher", {}).get("poll_time", 5.0)

        if self.idle_detector:
            idle_secs = self.idle_detector.get_idle_seconds()

            if idle_secs > self.idle_threshold * 5:
                # Very idle (5+ minutes) - poll very slowly
                return self.idle_poll_time * 2
            elif idle_secs > self.idle_threshold:
                # Idle (1+ minute) - poll slowly
                return self.idle_poll_time

        # Active - normal polling
        return base_poll

    def run(self):
        """Main watcher loop with adaptive polling."""
        self.running = True
        base_poll_time = self.config.get("watcher", {}).get("poll_time", 5.0)
        pulsetime = self.config.get("watcher", {}).get("pulsetime", base_poll_time + 1.0)

        logger.info(
            f"Starting main loop (base_poll_time={base_poll_time}s, idle_threshold={self.idle_threshold}s)"
        )

        with self.client:
            while self.running:
                try:
                    # Get adaptive poll time based on activity
                    poll_time = self._get_adaptive_poll_time()

                    # Log idle status periodically
                    if self.idle_detector:
                        idle_secs = self.idle_detector.get_idle_seconds()
                        if idle_secs > self.idle_threshold:
                            logger.debug(
                                f"User idle ({idle_secs:.0f}s), polling every {poll_time:.0f}s"
                            )

                    # Capture current state
                    data = self.capture_state()

                    if data:
                        event = Event(timestamp=datetime.now(timezone.utc), data=data)

                        self.client.heartbeat(
                            self.bucket_id, event, pulsetime=pulsetime, queued=True
                        )

                        logger.debug(f"Heartbeat: {data.get('app')} - {data.get('title', '')[:50]}")

                        # Update state tracking
                        self.last_window_data = data

                except KeyboardInterrupt:
                    logger.info("Interrupted, shutting down...")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}", exc_info=True)

                sleep(poll_time)

        logger.info("Watcher stopped")

    def stop(self):
        """Stop the watcher loop."""
        self.running = False


def main():
    parser = argparse.ArgumentParser(description="Enhanced ActivityWatch Watcher")
    parser.add_argument("--testing", action="store_true", help="Use testing server (port 5666)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR capture")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM enhancement of OCR")
    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Create and run watcher
    watcher = EnhancedWatcher(
        testing=args.testing,
        enable_ocr=not args.no_ocr,
        enable_llm=not args.no_llm,
    )

    # Handle signals for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, stopping...")
        watcher.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Setup and run
    watcher.setup()
    watcher.run()


if __name__ == "__main__":
    main()
