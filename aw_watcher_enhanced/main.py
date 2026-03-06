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
import gc
import logging
import re
import signal
import sys
import threading
from datetime import datetime, timezone
from time import sleep
from typing import Optional

from aw_client import ActivityWatchClient
from aw_core.models import Event

from .categorizer import categorize_event
from .config import load_config
from .document import (
    extract_project_from_cwd,
    get_shell_sessions,
    get_terminal_cwd,
    parse_document_context,
)
from .enrichment import EnrichmentWorker
from .privacy import apply_privacy_filters
from .window import get_all_windows, get_current_window, get_window_fast

# Try to import browser data merger (optional)
try:
    from .browser import BrowserDataMerger, is_browser_app

    BROWSER_MERGE_AVAILABLE = True
except ImportError:
    BROWSER_MERGE_AVAILABLE = False

# Try to import meeting detection (optional)
try:
    from .meeting import detect_camera_mic, detect_meeting

    MEETING_AVAILABLE = True
except ImportError:
    MEETING_AVAILABLE = False

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

# Try to import OS event listener (optional, macOS only)
try:
    from .os_events import OSEventListener

    OS_EVENTS_AVAILABLE = True
except ImportError:
    OS_EVENTS_AVAILABLE = False

# Try to import calendar monitor (optional, macOS only)
try:
    from .calendar_events import CalendarMonitor

    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False

# Try to import file activity tracker (optional)
try:
    from .file_events import FileActivityTracker

    FILE_EVENTS_AVAILABLE = True
except ImportError:
    FILE_EVENTS_AVAILABLE = False

# Try to import IDE data merger (optional)
try:
    from .ide_merger import IDEDataMerger

    IDE_MERGER_AVAILABLE = True
except ImportError:
    IDE_MERGER_AVAILABLE = False

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

        # Fast heartbeat state
        self._last_fast_window = None

        # Shared enriched state (written by enrichment thread, read by heartbeat)
        self._enriched_state = None
        self._enriched_state_lock = threading.Lock()
        self._enriched_window_key = None  # (app, title) the enriched state belongs to

        # Track state for change detection (used by enrichment)
        self.last_window_data = None
        self.last_ocr_time = None
        self.last_ocr_result = None  # Cache last OCR/LLM result
        self._last_ocr_result_time = None  # TTL for cached LLM result
        self._ocr_result_ttl = 300.0  # Clear cached LLM result after 5 min
        self._transition_pending = False  # F6: capture incoming window after switch

        # Memory management - run gc.collect() periodically
        self._last_gc_time = None
        self._gc_interval = 60  # Run garbage collection every 60 seconds

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

        # Initialize browser data merger
        self.browser_merger = None
        browser_config = self.config.get("browser", {})
        if BROWSER_MERGE_AVAILABLE and browser_config.get("enabled", False):
            self.browser_merger = BrowserDataMerger(self.client)
            logger.info("Browser URL merging enabled")

        # Meeting detection config
        meeting_config = self.config.get("meeting", {})
        self.enable_meeting = MEETING_AVAILABLE and meeting_config.get("enabled", True)
        self.meeting_detect_subprocess = meeting_config.get("detect_subprocess", True)
        if self.enable_meeting:
            logger.info("Meeting detection enabled")

        # OS event listener (macOS: app lifecycle, music, clipboard, screen lock)
        self.os_event_listener = None
        if OS_EVENTS_AVAILABLE:
            self.os_event_listener = OSEventListener()
            logger.info("OS event listener available")

        # Calendar monitor (macOS: EventKit)
        self.calendar_monitor = None
        if CALENDAR_AVAILABLE:
            self.calendar_monitor = CalendarMonitor()
            logger.info("Calendar monitoring available")

        # File activity tracker
        self.file_tracker = None
        if FILE_EVENTS_AVAILABLE:
            self.file_tracker = FileActivityTracker()
            logger.info("File activity tracking available")

        # IDE data merger (reads from aw-watcher-vscode etc.)
        self.ide_merger = None
        if IDE_MERGER_AVAILABLE:
            self.ide_merger = IDEDataMerger(self.client, self.client.client_hostname)
            logger.info("IDE data merger available")

        logger.info(f"Initialized {WATCHER_NAME}")
        logger.info(f"OCR enabled: {self.enable_ocr}")
        logger.info(f"LLM enhancement enabled: {self.enable_llm}")
        logger.info(f"Testing mode: {self.testing}")

    def setup(self):
        """Create bucket and prepare for capture."""
        self.client.create_bucket(
            self.bucket_id, "currentwindow", queued=True
        )
        logger.info(f"Created bucket: {self.bucket_id}")

    def capture_state(self) -> Optional[dict]:
        """Capture current window state with all enhancements.

        Returns a stable data dict (no volatile fields) so that
        the heartbeat loop can merge events cleanly. Focus duration
        and switch counts are computable from event timestamps.
        """
        # Step 1: Get basic window info (full AX details)
        window_data = get_current_window()
        if not window_data:
            return None

        # Step 2: Parse document context from title (flatten to string fields)
        document_context = parse_document_context(
            app=window_data.get("app", ""), title=window_data.get("title", "")
        )
        if document_context:
            if document_context.get("filename"):
                window_data["doc_file"] = document_context["filename"]
            if document_context.get("project"):
                window_data["doc_project"] = document_context["project"]
            if document_context.get("type"):
                window_data["doc_type"] = document_context["type"]
            if document_context.get("file_type"):
                window_data["doc_file_type"] = document_context["file_type"]
            if document_context.get("extension"):
                window_data["doc_ext"] = document_context["extension"]
            if document_context.get("path"):
                window_data["doc_path"] = document_context["path"]
            if document_context.get("page_title"):
                window_data["doc_page_title"] = document_context["page_title"]

        # Step 2.2: Terminal / IDE shell session detection
        app_name = window_data.get("app", "")
        title = window_data.get("title", "")
        pid = window_data.get("pid")

        if self._is_terminal_app(app_name):
            # Standalone terminal app — get CWD of child shell
            if pid:
                cwd = self._get_terminal_project_cwd(pid)
                if cwd:
                    window_data["cwd"] = cwd
                    project = extract_project_from_cwd(cwd)
                    if project:
                        window_data["terminal_project"] = project
                        if "doc_project" not in window_data:
                            window_data["doc_project"] = project
                            window_data["doc_type"] = "terminal"

        elif self._is_ide_with_terminal(app_name) and pid:
            # IDE with integrated terminal (VS Code, Cursor, etc.)
            # Get all shell sessions to know every project being worked on
            sessions = get_shell_sessions(pid)
            if sessions:
                # Deduplicate by project name, flatten to strings for AW compatibility
                seen_projects = set()
                projects = []
                for s in sessions:
                    proj = s.get("project", "")
                    if proj and proj not in seen_projects:
                        seen_projects.add(proj)
                        projects.append(proj)
                if projects:
                    window_data["shell_projects"] = "; ".join(sorted(projects))

        # Detect AI coding assistant sessions from title
        title_lower = title.lower()
        if "claude" in title_lower or "claude code" in title_lower:
            window_data["ai_assistant"] = "claude_code"
        elif "copilot" in title_lower:
            window_data["ai_assistant"] = "github_copilot"
        elif "aider" in title_lower:
            window_data["ai_assistant"] = "aider"
        elif "cursor" in app_name.lower():
            window_data["ai_assistant"] = "cursor"

        # Step 2.3: Merge IDE watcher data (aw-watcher-vscode, etc.)
        if self.ide_merger:
            ide_data = self.ide_merger.get_ide_data(app_name)
            if ide_data:
                window_data.update(ide_data)
                logger.debug(
                    f"IDE merge: {ide_data.get('ide_project', '')} "
                    f"file={ide_data.get('ide_file', '')}"
                )

        # Step 2.4: All-windows snapshot (compact: app+title only, capped)
        all_windows = get_all_windows()
        if all_windows:
            # Keep only essential fields and limit count to prevent bloat
            compact = [
                {"app": w.get("app", ""), "title": w.get("title", "")}
                for w in all_windows[:20]
            ]
            window_data["open_windows"] = compact

        # Step 2.5: Merge browser URL data (if active app is a browser)
        if self.browser_merger and BROWSER_MERGE_AVAILABLE:
            app_name = window_data.get("app", "")
            if is_browser_app(app_name):
                browser_data = self.browser_merger.get_browser_data()
                if browser_data:
                    window_data["url"] = browser_data["url"]
                    window_data["domain"] = browser_data["domain"]
                    if browser_data.get("tab_title"):
                        window_data["tab_title"] = browser_data["tab_title"]

        # Step 2.6: Merge OS event data (music, clipboard)
        if self.os_event_listener:
            # Now-playing music
            music = self.os_event_listener.get_music_state()
            if music and music.get("state") == "playing":
                window_data["music_artist"] = music.get("artist", "")
                window_data["music_track"] = music.get("track", "")
                if music.get("album"):
                    window_data["music_album"] = music["album"]
                window_data["music_player"] = music.get("player", "")

            # Clipboard changes
            clipboard = self.os_event_listener.get_clipboard_data()
            if clipboard:
                window_data["clipboard_type"] = clipboard.get(
                    "clipboard_type", ""
                )
                if clipboard.get("clipboard_text"):
                    window_data["clipboard_text"] = clipboard[
                        "clipboard_text"
                    ]

        # Step 2.65: Calendar context
        if self.calendar_monitor:
            cal_event = self.calendar_monitor.get_current_event()
            if cal_event:
                window_data.update(cal_event)

        # Step 2.68: Recent file activity
        if self.file_tracker:
            recent_files = self.file_tracker.get_recent_files(limit=10)
            if recent_files:
                window_data["recent_files"] = recent_files

        # Step 2.7: Meeting detection
        if self.enable_meeting:
            in_meeting, meeting_app = detect_meeting(
                app_name=window_data.get("app", ""),
                title=window_data.get("title", ""),
                url=window_data.get("url", ""),
                detect_subprocess=self.meeting_detect_subprocess,
            )
            window_data["in_meeting"] = in_meeting
            if meeting_app:
                window_data["meeting_app"] = meeting_app
            # Camera/mic active detection (strengthens meeting confidence)
            if in_meeting:
                cam_mic = detect_camera_mic()
                window_data["camera_active"] = cam_mic["camera_active"]
                window_data["mic_active"] = cam_mic["mic_active"]

        # Step 3: OCR capture (if enabled and triggered)
        if self.enable_ocr and self._should_capture_ocr(window_data):
            ocr_config = self.config.get("ocr", {})

            # Use structured OCR to get position-based text extraction
            image = capture_screen(window_only=False)
            structured_ocr = None
            if image:
                try:
                    structured_ocr = ocr_image_structured(image)
                finally:
                    # Explicitly close and delete image to prevent memory leak
                    try:
                        image.close()
                    except Exception:
                        pass
                    del image

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

                    # Expire stale cached LLM result
                    if (
                        self.last_ocr_result
                        and self._last_ocr_result_time
                        and (datetime.now(timezone.utc) - self._last_ocr_result_time).total_seconds()
                        > self._ocr_result_ttl
                    ):
                        self.last_ocr_result = None
                        self._last_ocr_result_time = None

                    if should_run_llm:
                        llm_result = summarize_ocr_with_llm(
                            ocr_text,
                            model=self.llm_model,
                            timeout=self.llm_timeout,
                        )
                        # Cache result for potential reuse (with TTL)
                        if llm_result:
                            self.last_ocr_result = llm_result
                            self._last_ocr_result_time = datetime.now(timezone.utc)
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

        # Remove internal fields not needed in event data
        window_data.pop("pid", None)

        return window_data

    # Terminal app patterns
    _TERMINAL_APPS = re.compile(
        r"terminal|iterm|iterm2|alacritty|kitty|wezterm|warp|hyper|"
        r"cmd\.exe|powershell|windowsterminal|konsole|gnome-terminal",
        re.IGNORECASE,
    )

    # IDEs with integrated terminals
    _IDE_WITH_TERMINAL = re.compile(
        r"code|visual studio code|cursor|windsurf|pycharm|intellij|webstorm|"
        r"phpstorm|rider|goland|clion|datagrip|rubymine",
        re.IGNORECASE,
    )

    def _is_terminal_app(self, app_name: str) -> bool:
        """Check if the app is a terminal emulator."""
        if not app_name:
            return False
        return bool(self._TERMINAL_APPS.search(app_name))

    def _is_ide_with_terminal(self, app_name: str) -> bool:
        """Check if the app is an IDE that has an integrated terminal."""
        if not app_name:
            return False
        return bool(self._IDE_WITH_TERMINAL.search(app_name))

    def _get_terminal_project_cwd(self, terminal_pid: int) -> Optional[str]:
        """Get the CWD of the shell running inside a terminal app.

        Terminal apps (iTerm2, Terminal.app) spawn a child shell process
        (zsh, bash, fish). We need the shell's CWD, not the terminal's.
        """
        from .document import _get_child_shell_pid

        # First try to get the child shell's CWD (more accurate)
        shell_pid = _get_child_shell_pid(terminal_pid)
        if shell_pid:
            cwd = get_terminal_cwd(shell_pid)
            if cwd:
                return cwd

        # Fallback: get the terminal app's own CWD
        cwd = get_terminal_cwd(terminal_pid)
        return cwd

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

    def _is_data_rich(self, current_data: dict) -> bool:
        """Check if we already have rich data from primary sources (AX, browser, etc.).

        When primary data sources provide enough context, OCR is unnecessary.
        Returns True if data is rich enough to skip OCR.
        """
        has_ax = bool(current_data.get("focused_element_role"))
        has_document = bool(current_data.get("doc_project") or current_data.get("doc_file"))

        # Browser app without URL means web extension is missing — data is thin
        app_name = current_data.get("app", "")
        is_browser = BROWSER_MERGE_AVAILABLE and is_browser_app(app_name)
        if is_browser and not current_data.get("url"):
            return False

        # If AX returned role info, we have good visibility into the app
        if has_ax:
            return True

        # If we have document context from the title, that's useful too
        if has_document:
            return True

        return False

    def _should_capture_ocr(self, current_data: dict) -> bool:
        """
        Determine if OCR capture should be triggered.

        Trigger modes:
        - "adaptive" (default): Only fire OCR when primary data sources return
          thin data. Always fires for remote desktop apps. Uses a long-interval
          safety net (5 min) even when data is rich.
        - "smart"/"both": Capture on window change + periodic for same window.
        - "window_change": Only on window/title change.
        - "periodic": On a fixed interval regardless of changes.

        Common logic across all modes:
        1. Skip if user is idle
        2. Handle transition capture (incoming window after a switch)
        3. Always capture for remote desktop apps
        """
        # Check if user is idle - skip OCR to save resources
        if self.idle_detector and self.idle_detector.is_idle():
            idle_secs = self.idle_detector.get_idle_seconds()
            logger.debug(f"User idle ({idle_secs:.0f}s), skipping OCR")
            return False

        ocr_config = self.config.get("ocr", {})
        smart_config = self.config.get("smart_capture", {})
        trigger = ocr_config.get("trigger", "adaptive")
        transition_capture = ocr_config.get("transition_capture", True)

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

        # Transition capture: if we just switched windows, capture the incoming window
        if self._transition_pending and not window_changed:
            self._transition_pending = False
            current_data["transition"] = True
            logger.debug("Transition capture: capturing incoming window")
            return True

        # If window changed, mark for transition capture on next poll
        if window_changed and transition_capture:
            self._transition_pending = True

        # Remote desktop apps always get frequent OCR — we can't see inside them
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

        # --- Adaptive mode: OCR only when primary data is thin ---
        if trigger == "adaptive":
            data_rich = self._is_data_rich(current_data)

            if not data_rich:
                # Data is thin — use smart capture logic (window change + periodic)
                if window_changed:
                    logger.debug("Adaptive OCR: thin data + window changed, capturing")
                    return True
                interval = ocr_config.get("periodic_interval", 30)
                if self.last_ocr_time is None:
                    return True
                elapsed = (datetime.now(timezone.utc) - self.last_ocr_time).total_seconds()
                if elapsed >= interval:
                    logger.debug(
                        f"Adaptive OCR: thin data, periodic capture after {elapsed:.0f}s"
                    )
                    return True
                return False

            # Data is rich — only fire on the long safety-net interval
            fallback_interval = ocr_config.get("adaptive_fallback_interval", 300)
            if self.last_ocr_time is None:
                # First capture ever — do one baseline OCR
                logger.debug("Adaptive OCR: initial baseline capture")
                return True
            elapsed = (datetime.now(timezone.utc) - self.last_ocr_time).total_seconds()
            if elapsed >= fallback_interval:
                logger.debug(
                    f"Adaptive OCR: rich data, safety-net capture after {elapsed:.0f}s"
                )
                return True
            return False

        # --- Legacy trigger modes ---
        if trigger == "window_change":
            return window_changed

        elif trigger == "periodic":
            interval = ocr_config.get("periodic_interval", 30)
            if self.last_ocr_time is None:
                return True
            elapsed = (datetime.now(timezone.utc) - self.last_ocr_time).total_seconds()
            return elapsed >= interval

        elif trigger in ("both", "smart"):
            if window_changed:
                return True
            default_interval = 60 if transition_capture else 30
            interval = ocr_config.get("periodic_interval", default_interval)
            if self.last_ocr_time is None:
                return True
            elapsed = (datetime.now(timezone.utc) - self.last_ocr_time).total_seconds()
            return elapsed >= interval

        return False

    def _heartbeat_loop(self, enrichment_worker: EnrichmentWorker):
        """Fast heartbeat loop - sends {app, title} every 1s. Never blocked.

        Runs in a dedicated thread. Only sends the two stable fields
        (app, title) so events merge cleanly via ActivityWatch's
        heartbeat mechanism. Signals the enrichment worker on window change.
        """
        heartbeat_interval = self.config.get("watcher", {}).get(
            "heartbeat_interval", 1.0
        )
        pulsetime = heartbeat_interval + 1.0

        logger.info(
            f"Heartbeat loop started (interval={heartbeat_interval}s, "
            f"pulsetime={pulsetime}s)"
        )

        while self.running:
            try:
                window = get_window_fast()
                if window is None:
                    # Use last known window (never skip a heartbeat)
                    window = self._last_fast_window or {
                        "app": "unknown",
                        "title": "",
                    }

                app = window.get("app", "unknown")
                title = window.get("title", "")

                # Merge enriched data if available for current window
                with self._enriched_state_lock:
                    if (
                        self._enriched_state is not None
                        and self._enriched_window_key == (app, title)
                    ):
                        data = self._enriched_state.copy()
                    else:
                        data = {"app": app, "title": title}

                event = Event(
                    timestamp=datetime.now(timezone.utc), data=data
                )
                self.client.heartbeat(
                    self.bucket_id,
                    event,
                    pulsetime=pulsetime,
                    queued=True,
                )

                # Detect window change → signal enrichment
                window_key = (app, title)
                if (
                    self._last_fast_window is None
                    or window_key != self._last_fast_window
                ):
                    # Clear stale enriched state for old window
                    with self._enriched_state_lock:
                        self._enriched_state = None
                        self._enriched_window_key = None
                    enrichment_worker.notify_window_change()
                    logger.debug(
                        f"Window changed: {app} - {title[:50]}"
                    )

                self._last_fast_window = window_key

                # Periodic garbage collection
                now = datetime.now(timezone.utc)
                if (
                    self._last_gc_time is None
                    or (now - self._last_gc_time).total_seconds()
                    >= self._gc_interval
                ):
                    collected = gc.collect()
                    if collected > 0:
                        logger.debug(
                            f"Garbage collected {collected} objects"
                        )
                    self._last_gc_time = now

            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

            sleep(heartbeat_interval)

        logger.info("Heartbeat loop stopped")

    def run(self):
        """Start the two-thread architecture: heartbeat + enrichment.

        Thread 1 (heartbeat): Sends {app, title} every 1s for gap-free timeline.
        Thread 2 (enrichment): Captures rich context on window change / periodic.
        """
        self.running = True

        logger.info("Starting two-thread architecture")

        with self.client:
            # Start background services
            if self.os_event_listener:
                self.os_event_listener.start()
            if self.calendar_monitor:
                self.calendar_monitor.start()
            if self.file_tracker:
                self.file_tracker.start()

            enrichment_worker = EnrichmentWorker(
                watcher=self,
                periodic_interval=15.0,
            )
            enrichment_worker.start()

            heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                args=(enrichment_worker,),
                name="heartbeat",
                daemon=True,
            )
            heartbeat_thread.start()

            # Main thread waits for stop signal
            try:
                while self.running:
                    sleep(1.0)
            except KeyboardInterrupt:
                logger.info("Interrupted, shutting down...")
                self.running = False

            enrichment_worker.stop()
            heartbeat_thread.join(timeout=5.0)
            if self.os_event_listener:
                self.os_event_listener.stop()
            if self.calendar_monitor:
                self.calendar_monitor.stop()
            if self.file_tracker:
                self.file_tracker.stop()

        logger.info("Watcher stopped")

    def stop(self):
        """Stop the watcher loop."""
        self.running = False


def _hide_dock_icon():
    """Hide the dock icon on macOS using Accessory policy (not Prohibited).

    Uses NSApplicationActivationPolicyAccessory which hides the dock icon
    while still allowing the process to query the window server.
    NSApplicationActivationPolicyProhibited was previously used but it
    interfered with NSWorkspace.frontmostApplication() in long-running
    background processes, causing it to return 'loginwindow'.
    """
    if sys.platform != "darwin":
        return

    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except ImportError:
        pass
    except Exception as e:
        print(f"Warning: Failed to hide dock icon: {e}", flush=True)


def _run_watcher(args):
    """Run the watcher directly in the current process (child mode)."""
    watcher = EnhancedWatcher(
        testing=args.testing,
        enable_ocr=not args.no_ocr,
        enable_llm=not args.no_llm,
    )

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, stopping...")
        watcher.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    watcher.setup()
    watcher.run()


def main():
    """Entry point with auto-restart on crash.

    Runs the watcher as a subprocess so we can detect and recover from
    any kind of crash (Python exceptions, SIGKILL, OOM, segfault).

    Intentional stops (SIGTERM, SIGINT) propagate to the child and
    cause a clean exit with no restart. Unexpected exits trigger a
    restart after a short delay, with backoff if crashes repeat.
    """
    import subprocess

    _hide_dock_icon()

    parser = argparse.ArgumentParser(description="Enhanced ActivityWatch Watcher")
    parser.add_argument("--testing", action="store_true", help="Use testing server (port 5666)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR capture")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM enhancement of OCR")
    parser.add_argument(
        "--no-restart", action="store_true",
        help="Disable auto-restart (run directly without watchdog)",
    )
    parser.add_argument(
        "--_child", action="store_true", help=argparse.SUPPRESS,
    )

    # Reclassification CLI
    parser.add_argument(
        "--reclassify", action="store_true",
        help="Re-run categorization on existing events",
    )
    parser.add_argument("--start", type=str, help="Start date for reclassify (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date for reclassify (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Preview reclassify changes only")

    # Summary CLI
    parser.add_argument(
        "--summary", nargs="?", const="today", type=str,
        help="Generate daily summary (default: today, or YYYY-MM-DD / yesterday)",
    )
    parser.add_argument(
        "--summary-format", choices=["text", "json"], default="text",
        help="Summary output format (default: text)",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Reclassification mode
    if args.reclassify:
        if not args.start or not args.end:
            parser.error("--reclassify requires --start and --end dates (YYYY-MM-DD)")
        from .reclassify import run_reclassify
        run_reclassify(
            start_str=args.start,
            end_str=args.end,
            dry_run=args.dry_run,
            testing=args.testing,
        )
        return

    # Summary mode
    if args.summary is not None:
        from .summary import run_summary
        run_summary(
            date_str=args.summary,
            output_format=args.summary_format,
            testing=args.testing,
        )
        return

    # Child mode: run the watcher directly (spawned by the watchdog below)
    if args._child or args.no_restart:
        _run_watcher(args)
        return

    # Watchdog mode: spawn the watcher as a child and restart on crash
    RESTART_DELAY = 5
    MAX_RAPID_RESTARTS = 5
    RAPID_WINDOW = 60
    restart_times = []
    child_proc = None
    intentional_stop = False

    def watchdog_signal_handler(sig, frame):
        nonlocal intentional_stop
        intentional_stop = True
        if child_proc and child_proc.poll() is None:
            child_proc.send_signal(sig)

    signal.signal(signal.SIGINT, watchdog_signal_handler)
    signal.signal(signal.SIGTERM, watchdog_signal_handler)

    # Build the child command with --_child flag
    child_cmd = [sys.executable, "-m", "aw_watcher_enhanced", "--_child"]
    if args.testing:
        child_cmd.append("--testing")
    if args.verbose:
        child_cmd.append("--verbose")
    if args.no_ocr:
        child_cmd.append("--no-ocr")
    if args.no_llm:
        child_cmd.append("--no-llm")

    logger.info("Watchdog started, managing watcher subprocess")

    while True:
        child_proc = subprocess.Popen(child_cmd)
        exit_code = child_proc.wait()

        if intentional_stop or exit_code == 0:
            logger.info(f"Watcher exited (code={exit_code}), not restarting")
            break

        logger.warning(f"Watcher exited unexpectedly (code={exit_code})")

        # Guard against crash loops
        now = datetime.now(timezone.utc).timestamp()
        restart_times = [t for t in restart_times if now - t < RAPID_WINDOW]
        if len(restart_times) >= MAX_RAPID_RESTARTS:
            logger.error(
                f"Crashed {MAX_RAPID_RESTARTS} times in {RAPID_WINDOW}s, "
                f"backing off 60s"
            )
            sleep(60)
            restart_times.clear()

        restart_times.append(now)
        logger.info(f"Restarting in {RESTART_DELAY}s...")
        sleep(RESTART_DELAY)


if __name__ == "__main__":
    main()
