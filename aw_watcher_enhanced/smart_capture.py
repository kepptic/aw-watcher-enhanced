"""
Smart capture system for aw-watcher-enhanced.

Features:
- Async queue for OCR/LLM processing (non-blocking)
- Idle detection (mouse/keyboard inactivity)
- Smart throttling (adjust polling based on activity)
- OCR diff detection (skip LLM if content unchanged)
- Efficient resource usage
"""

import hashlib
import logging
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CaptureTask:
    """A capture task to be processed."""

    timestamp: datetime
    window_data: Dict[str, Any]
    image: Any  # PIL Image
    priority: int = 0  # Higher = more important


class OCRDiffDetector:
    """
    Detect significant changes in OCR text to avoid redundant LLM calls.

    Uses multiple strategies:
    1. Text hash comparison (fast, detects any change)
    2. Similarity ratio (detects meaningful changes)
    3. Keyword extraction diff (semantic change detection)
    """

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        min_change_chars: int = 50,
        max_history: int = 5,
    ):
        """
        Args:
            similarity_threshold: Minimum similarity (0-1) to consider "same content"
            min_change_chars: Minimum character difference to trigger LLM
            max_history: Number of previous OCR results to keep
        """
        self.similarity_threshold = similarity_threshold
        self.min_change_chars = min_change_chars
        self.max_history = max_history

        self._history: List[Tuple[str, str, float]] = []  # (hash, text, timestamp)
        self._last_text: Optional[str] = None
        self._last_hash: Optional[str] = None
        self._last_keywords: set = set()

        # Stats
        self.stats = {
            "total_checks": 0,
            "skipped_identical": 0,
            "skipped_similar": 0,
            "triggered_different": 0,
        }

    def _normalize_text(self, text: str) -> str:
        """Normalize OCR text for comparison."""
        if not text:
            return ""
        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text.strip())
        # Remove common OCR noise (single chars, repeated punctuation)
        text = re.sub(r"\b[a-zA-Z]\b", "", text)
        text = re.sub(r"[.]{3,}", "...", text)
        text = re.sub(r"[-]{3,}", "---", text)
        return text.lower()

    def _hash_text(self, text: str) -> str:
        """Create hash of normalized text."""
        normalized = self._normalize_text(text)
        return hashlib.md5(normalized.encode()).hexdigest()

    def _extract_keywords(self, text: str) -> set:
        """Extract significant keywords for semantic comparison."""
        if not text:
            return set()

        # Extract words 4+ chars, excluding common words
        words = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())

        stop_words = {
            "this",
            "that",
            "with",
            "from",
            "have",
            "been",
            "were",
            "they",
            "will",
            "would",
            "could",
            "should",
            "about",
            "which",
            "their",
            "there",
            "what",
            "when",
            "where",
            "your",
            "more",
            "some",
            "than",
            "into",
            "also",
            "just",
            "only",
            "very",
            "after",
            "before",
            "between",
        }

        return {w for w in words if w not in stop_words}

    def _get_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity ratio between two texts."""
        if not text1 or not text2:
            return 0.0

        norm1 = self._normalize_text(text1)
        norm2 = self._normalize_text(text2)

        # Use SequenceMatcher for efficient similarity calculation
        return SequenceMatcher(None, norm1, norm2).ratio()

    def should_run_llm(self, ocr_text: str, window_data: Optional[Dict] = None) -> Tuple[bool, str]:
        """
        Determine if LLM should be run based on OCR text changes.

        Args:
            ocr_text: Current OCR text
            window_data: Optional window context (app, title) for smarter detection

        Returns:
            Tuple of (should_run: bool, reason: str)
        """
        self.stats["total_checks"] += 1

        if not ocr_text:
            return False, "empty_ocr"

        current_hash = self._hash_text(ocr_text)

        # First check: identical hash (fastest)
        if current_hash == self._last_hash:
            self.stats["skipped_identical"] += 1
            logger.debug("OCR identical (hash match), skipping LLM")
            return False, "identical_hash"

        # Second check: similarity ratio
        if self._last_text:
            similarity = self._get_similarity(ocr_text, self._last_text)

            if similarity >= self.similarity_threshold:
                # Check if character difference is meaningful
                char_diff = abs(len(ocr_text) - len(self._last_text))

                if char_diff < self.min_change_chars:
                    self.stats["skipped_similar"] += 1
                    logger.debug(
                        f"OCR similar ({similarity:.2%}), diff={char_diff} chars, skipping LLM"
                    )
                    return False, f"similar_{similarity:.2f}"

        # Third check: keyword diff (semantic changes)
        current_keywords = self._extract_keywords(ocr_text)

        if self._last_keywords:
            new_keywords = current_keywords - self._last_keywords
            removed_keywords = self._last_keywords - current_keywords

            # If very few keywords changed, might still be same context
            total_changed = len(new_keywords) + len(removed_keywords)
            if total_changed <= 2 and len(current_keywords) > 10:
                # Only 1-2 keywords changed in a large text - likely minor change
                logger.debug(
                    f"Minor keyword change ({total_changed} words), but running LLM for accuracy"
                )

        # Update state
        self._last_text = ocr_text
        self._last_hash = current_hash
        self._last_keywords = current_keywords

        # Add to history
        self._history.append((current_hash, ocr_text[:500], time.time()))
        if len(self._history) > self.max_history:
            self._history.pop(0)

        self.stats["triggered_different"] += 1
        logger.debug("OCR content changed, running LLM")
        return True, "content_changed"

    def force_next_llm(self):
        """Force LLM to run on next check (e.g., after window change)."""
        self._last_hash = None
        self._last_text = None
        self._last_keywords = set()

    def get_stats(self) -> Dict[str, Any]:
        """Get diff detection statistics."""
        total = self.stats["total_checks"]
        if total == 0:
            return self.stats

        return {
            **self.stats,
            "skip_rate": (self.stats["skipped_identical"] + self.stats["skipped_similar"]) / total,
            "history_size": len(self._history),
        }


class IdleDetector:
    """Detect user idle time (no mouse/keyboard activity)."""

    def __init__(self):
        self._last_activity = time.time()
        self._idle_threshold = 60  # seconds
        self._setup_platform()

    def _setup_platform(self):
        """Setup platform-specific idle detection."""
        self._get_idle_time = self._get_idle_time_fallback

        if sys.platform == "darwin":
            try:
                from Quartz import (
                    CGEventSourceSecondsSinceLastEventType,
                    kCGEventSourceStateHIDSystemState,
                )

                def get_idle_macos():
                    # Get seconds since last HID event (mouse/keyboard)
                    return CGEventSourceSecondsSinceLastEventType(
                        kCGEventSourceStateHIDSystemState,
                        0xFFFFFFFF,  # All event types
                    )

                self._get_idle_time = get_idle_macos
                logger.info("Using macOS Quartz for idle detection")
            except ImportError:
                logger.warning("Quartz not available, using fallback idle detection")

        elif sys.platform == "win32":
            try:
                import ctypes
                from ctypes import Structure, byref, sizeof, windll

                class LASTINPUTINFO(Structure):
                    _fields_ = [
                        ("cbSize", ctypes.c_uint),
                        ("dwTime", ctypes.c_uint),
                    ]

                def get_idle_windows():
                    lii = LASTINPUTINFO()
                    lii.cbSize = sizeof(LASTINPUTINFO)
                    windll.user32.GetLastInputInfo(byref(lii))
                    millis = windll.kernel32.GetTickCount() - lii.dwTime
                    return millis / 1000.0

                self._get_idle_time = get_idle_windows
                logger.info("Using Windows API for idle detection")
            except Exception as e:
                logger.warning(f"Windows idle detection failed: {e}")

    def _get_idle_time_fallback(self) -> float:
        """Fallback: always return 0 (assume active)."""
        return 0.0

    def get_idle_seconds(self) -> float:
        """Get seconds since last user activity."""
        return self._get_idle_time()

    def is_idle(self, threshold_seconds: float = None) -> bool:
        """Check if user is idle."""
        threshold = threshold_seconds or self._idle_threshold
        return self.get_idle_seconds() > threshold

    def set_threshold(self, seconds: float):
        """Set idle threshold in seconds."""
        self._idle_threshold = seconds


class ProcessingQueue:
    """Async queue for OCR/LLM processing."""

    def __init__(self, processor: Callable, max_size: int = 10):
        self._queue: queue.Queue = queue.Queue(maxsize=max_size)
        self._processor = processor
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._last_result: Optional[Dict[str, Any]] = None
        self._result_lock = threading.Lock()
        self._processing = False

    def start(self):
        """Start the background worker thread."""
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return

        self._running = True
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        logger.info("Processing queue started")

    def stop(self):
        """Stop the background worker thread."""
        self._running = False
        # Add sentinel to unblock the queue
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        logger.info("Processing queue stopped")

    def submit(self, task: CaptureTask) -> bool:
        """Submit a task for processing. Returns False if queue is full."""
        try:
            # Drop old tasks if queue is full (keep most recent)
            if self._queue.full():
                try:
                    self._queue.get_nowait()  # Drop oldest
                except queue.Empty:
                    pass

            self._queue.put_nowait(task)
            return True
        except queue.Full:
            logger.warning("Processing queue full, dropping task")
            return False

    def _worker(self):
        """Background worker that processes tasks."""
        while self._running:
            try:
                task = self._queue.get(timeout=1.0)

                if task is None:  # Sentinel
                    continue

                self._processing = True
                try:
                    result = self._processor(task)

                    with self._result_lock:
                        self._last_result = result

                except Exception as e:
                    logger.error(f"Error processing task: {e}")
                finally:
                    self._processing = False
                    self._queue.task_done()

            except queue.Empty:
                continue

    def get_last_result(self) -> Optional[Dict[str, Any]]:
        """Get the last processed result."""
        with self._result_lock:
            return self._last_result

    def is_processing(self) -> bool:
        """Check if currently processing a task."""
        return self._processing

    def queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()


class SmartCaptureManager:
    """
    Manages smart capture with:
    - Idle detection
    - Adaptive polling
    - Background processing
    """

    def __init__(
        self,
        ocr_processor: Callable,
        base_poll_time: float = 5.0,
        idle_threshold: float = 60.0,
        idle_poll_time: float = 30.0,
        max_queue_size: int = 5,
    ):
        self.base_poll_time = base_poll_time
        self.idle_threshold = idle_threshold
        self.idle_poll_time = idle_poll_time

        self.idle_detector = IdleDetector()
        self.idle_detector.set_threshold(idle_threshold)

        self.processing_queue = ProcessingQueue(processor=ocr_processor, max_size=max_queue_size)

        # State tracking
        self._last_window = None
        self._last_capture_time = 0
        self._consecutive_idle_count = 0

        # Stats
        self.stats = {
            "captures": 0,
            "skipped_idle": 0,
            "skipped_same_window": 0,
            "queue_drops": 0,
        }

    def start(self):
        """Start the processing queue."""
        self.processing_queue.start()

    def stop(self):
        """Stop the processing queue."""
        self.processing_queue.stop()

    def get_poll_time(self) -> float:
        """Get adaptive poll time based on activity."""
        idle_seconds = self.idle_detector.get_idle_seconds()

        if idle_seconds > self.idle_threshold * 5:
            # Very idle - poll very slowly
            return self.idle_poll_time * 2
        elif idle_seconds > self.idle_threshold:
            # Idle - poll slowly
            return self.idle_poll_time
        else:
            # Active - normal polling
            return self.base_poll_time

    def should_capture(self, window_data: Dict[str, Any]) -> bool:
        """
        Determine if we should capture OCR for this window.

        Returns False if:
        - User is idle
        - Same window as last capture (no change)
        - Too soon since last capture
        """
        now = time.time()

        # Check idle
        if self.idle_detector.is_idle():
            self._consecutive_idle_count += 1

            # After 5 consecutive idle checks, stop capturing
            if self._consecutive_idle_count >= 5:
                self.stats["skipped_idle"] += 1
                logger.debug(
                    f"Skipping capture - user idle ({self.idle_detector.get_idle_seconds():.0f}s)"
                )
            if self._consecutive_idle_count >= 5:
                self.stats["skipped_idle"] += 1
                logger.debug(
                    f"Skipping capture - user idle ({self.idle_detector.get_idle_seconds():.0f}s)"
                )
                return False
        else:
            self._consecutive_idle_count = 0

        # Check if window changed
        current_window = (window_data.get("app"), window_data.get("title"))
        if current_window == self._last_window:
            # Same window - only capture periodically
            if now - self._last_capture_time < 30:  # Min 30s between same-window captures
                self.stats["skipped_same_window"] += 1
                return False

        self._last_window = current_window
        self._last_capture_time = now
        return True

    def submit_capture(self, window_data: Dict[str, Any], image: Any) -> bool:
        """Submit a capture for background processing."""
        task = CaptureTask(
            timestamp=datetime.now(timezone.utc),
            window_data=window_data,
            image=image,
        )

        success = self.processing_queue.submit(task)
        if success:
            self.stats["captures"] += 1
        else:
            self.stats["queue_drops"] += 1

        return success

    def get_last_result(self) -> Optional[Dict[str, Any]]:
        """Get the last OCR/LLM result."""
        return self.processing_queue.get_last_result()

    def get_status(self) -> Dict[str, Any]:
        """Get current status."""
        return {
            "idle_seconds": self.idle_detector.get_idle_seconds(),
            "is_idle": self.idle_detector.is_idle(),
            "poll_time": self.get_poll_time(),
            "queue_size": self.processing_queue.queue_size(),
            "is_processing": self.processing_queue.is_processing(),
            "stats": self.stats,
        }


# Convenience function
def create_smart_capture(
    ocr_processor: Callable,
    config: Dict[str, Any] = None,
) -> SmartCaptureManager:
    """Create a SmartCaptureManager with config."""
    config = config or {}

    return SmartCaptureManager(
        ocr_processor=ocr_processor,
        base_poll_time=config.get("poll_time", 5.0),
        idle_threshold=config.get("idle_threshold", 60.0),
        idle_poll_time=config.get("idle_poll_time", 30.0),
        max_queue_size=config.get("max_queue_size", 5),
    )
