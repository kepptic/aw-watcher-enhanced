"""
OCR screen content capture for aw-watcher-enhanced.

Captures the active window and extracts text using OCR.
Supports multiple OCR engines (in order of preference):
- Apple Vision (fastest and most accurate on macOS, uses Neural Engine)
- Windows OCR API (fast on Windows, uses built-in Windows.Media.Ocr)
- RapidOCR (fast cross-platform, ONNX-based PaddleOCR models)
- Tesseract (cross-platform fallback, slower)
"""

import gc
import logging
import re
import sys
import tempfile
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Check available OCR engines
OCR_AVAILABLE = False
OCR_ENGINE = None
_rapidocr_singleton = None  # Singleton to avoid memory leak from recreating engine

try:
    if sys.platform == "darwin":
        # Try Apple Vision first on macOS (fastest, uses Neural Engine)
        try:
            from ocrmac import ocrmac

            OCR_AVAILABLE = True
            OCR_ENGINE = "apple_vision"
            logger.info("Using Apple Vision OCR (Neural Engine accelerated)")
        except ImportError:
            pass

    if sys.platform == "win32" and not OCR_AVAILABLE:
        # Try Windows OCR API on Windows (built-in, fast)
        try:
            import winocr

            OCR_AVAILABLE = True
            OCR_ENGINE = "windows"
            logger.info("Using Windows OCR API (built-in)")
        except ImportError:
            pass

    if not OCR_AVAILABLE:
        # Try RapidOCR (fast, ONNX-based, cross-platform)
        try:
            from rapidocr_onnxruntime import RapidOCR

            # Test that it can initialize - keep as singleton to avoid memory leak
            _rapidocr_singleton = RapidOCR()
            OCR_AVAILABLE = True
            OCR_ENGINE = "rapidocr"
            logger.info("Using RapidOCR (ONNX-based, fast)")
        except ImportError:
            _rapidocr_singleton = None
        except Exception as e:
            _rapidocr_singleton = None
            logger.debug(f"RapidOCR initialization failed: {e}")

    if not OCR_AVAILABLE:
        # Fall back to Tesseract (slower but widely available)
        import pytesseract

        pytesseract.get_tesseract_version()
        OCR_AVAILABLE = True
        OCR_ENGINE = "tesseract"
        logger.info("Using Tesseract OCR (fallback)")

except Exception as e:
    logger.warning(f"OCR not available: {e}")
    OCR_AVAILABLE = False


def capture_screen(
    window_only: bool = True, monitor_index: Optional[int] = None, mode: str = "auto"
) -> Optional[Any]:
    """
    Capture the screen or active window.

    Args:
        window_only: If True, capture only the active window (recommended for privacy)
        monitor_index: Specific monitor to capture (None = monitor under mouse cursor)
        mode: Capture mode - "auto", "active_window", "active_monitor", "all_monitors"

    Returns:
        PIL Image object or None
    """
    try:
        import mss
        from PIL import Image
    except ImportError:
        logger.error("mss and Pillow required. Run: pip install mss Pillow")
        return None

    try:
        with mss.mss() as sct:
            if window_only:
                if sys.platform == "win32":
                    # Get active window bounds on Windows
                    monitor = _get_active_window_bounds_windows()
                    if monitor is None:
                        # Fallback to monitor under cursor
                        monitor = _get_monitor_under_cursor_windows(sct)
                    if monitor is None:
                        monitor = sct.monitors[1]  # Primary monitor

                elif sys.platform == "darwin":
                    # Get active window bounds on macOS
                    monitor = _get_active_window_bounds_macos(sct)
                    if monitor is None:
                        # Fallback to monitor under cursor
                        monitor = _get_monitor_under_cursor_macos(sct)
                    if monitor is None:
                        monitor = sct.monitors[1]  # Fallback to primary
                else:
                    monitor = sct.monitors[1]  # Primary monitor
            elif monitor_index is not None:
                # Capture specific monitor
                if monitor_index < len(sct.monitors):
                    monitor = sct.monitors[monitor_index]
                else:
                    monitor = sct.monitors[1]
            else:
                # Capture monitor under mouse cursor
                if sys.platform == "win32":
                    monitor = _get_monitor_under_cursor_windows(sct)
                elif sys.platform == "darwin":
                    monitor = _get_monitor_under_cursor_macos(sct)
                else:
                    monitor = sct.monitors[1]

                if monitor is None:
                    monitor = sct.monitors[1]  # Primary monitor

            # Capture
            screenshot = sct.grab(monitor)

            # Convert to PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

            # Clear screenshot buffer to free memory
            del screenshot

            return img

    except Exception as e:
        logger.error(f"Screen capture failed: {e}")
        return None


def _get_active_window_bounds_windows() -> Optional[Dict[str, int]]:
    """Get the bounds of the active window on Windows."""
    try:
        import win32gui

        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            rect = win32gui.GetWindowRect(hwnd)
            return {
                "left": rect[0],
                "top": rect[1],
                "width": rect[2] - rect[0],
                "height": rect[3] - rect[1],
            }
        return None
    except ImportError:
        logger.debug("win32gui not available")
        return None
    except Exception as e:
        logger.debug(f"Error getting Windows window bounds: {e}")
        return None


def _get_monitor_under_cursor_windows(sct) -> Optional[Dict[str, int]]:
    """Get the monitor under the mouse cursor on Windows."""
    try:
        import ctypes
        from ctypes import wintypes

        # Get cursor position
        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        point = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        cursor_x, cursor_y = point.x, point.y

        # Find which monitor contains the cursor
        for monitor in sct.monitors[1:]:  # Skip the virtual all-monitors monitor
            if (
                monitor["left"] <= cursor_x < monitor["left"] + monitor["width"]
                and monitor["top"] <= cursor_y < monitor["top"] + monitor["height"]
            ):
                return monitor

        return None
    except Exception as e:
        logger.debug(f"Error getting Windows monitor under cursor: {e}")
        return None


def _get_monitor_under_cursor_macos(sct) -> Optional[Dict[str, int]]:
    """Get the monitor under the mouse cursor on macOS."""
    try:
        from AppKit import NSEvent, NSScreen

        # Get mouse position in Cocoa coordinates (origin bottom-left)
        mouse_ns = NSEvent.mouseLocation()

        # Get screens and find which one contains the cursor
        screens = NSScreen.screens()
        if not screens:
            return None

        primary_height = screens[0].frame().size.height

        for i, screen in enumerate(screens):
            frame = screen.frame()
            if (
                frame.origin.x <= mouse_ns.x <= frame.origin.x + frame.size.width
                and frame.origin.y <= mouse_ns.y <= frame.origin.y + frame.size.height
            ):
                # Found the screen - now get the corresponding mss monitor
                # mss monitors are 1-indexed (0 is virtual all-monitors)
                if i + 1 < len(sct.monitors):
                    return sct.monitors[i + 1]

        return None
    except ImportError:
        logger.debug("AppKit not available for macOS cursor detection")
        return None
    except Exception as e:
        logger.debug(f"Error getting macOS monitor under cursor: {e}")
        return None


def _get_active_window_bounds_macos(sct) -> Optional[Dict[str, int]]:
    """
    Get the bounds of the active window on macOS.

    Returns:
        Dict with left, top, width, height or None
    """
    try:
        from AppKit import NSWorkspace
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListExcludeDesktopElements,
            kCGWindowListOptionOnScreenOnly,
        )

        # Get the frontmost application
        workspace = NSWorkspace.sharedWorkspace()
        active_app = workspace.frontmostApplication()

        if not active_app:
            return None

        app_pid = active_app.processIdentifier()

        # Get window list
        options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
        window_list = CGWindowListCopyWindowInfo(options, kCGNullWindowID)

        # Find the frontmost window of the active app
        for window in window_list:
            if window.get("kCGWindowOwnerPID") == app_pid:
                bounds = window.get("kCGWindowBounds", {})
                if bounds:
                    return {
                        "left": int(bounds.get("X", 0)),
                        "top": int(bounds.get("Y", 0)),
                        "width": int(bounds.get("Width", 800)),
                        "height": int(bounds.get("Height", 600)),
                    }

        return None

    except ImportError:
        logger.debug("PyObjC not available for macOS window bounds")
        return None
    except Exception as e:
        logger.debug(f"Error getting macOS window bounds: {e}")
        return None


def get_monitor_count() -> int:
    """
    Get the number of monitors connected.

    Returns:
        Number of monitors (excluding the virtual 'all monitors' monitor)
    """
    try:
        import mss

        with mss.mss() as sct:
            # monitors[0] is the virtual monitor containing all screens
            return len(sct.monitors) - 1
    except Exception:
        return 1


def capture_all_monitors() -> List[Any]:
    """
    Capture all monitors individually.

    Returns:
        List of PIL Image objects, one per monitor
    """
    try:
        import mss
        from PIL import Image
    except ImportError:
        logger.error("mss and Pillow required")
        return []

    images = []
    try:
        with mss.mss() as sct:
            # Skip monitors[0] which is the virtual 'all monitors' combined
            for i, monitor in enumerate(sct.monitors[1:], start=1):
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                images.append(img)
                logger.debug(f"Captured monitor {i}: {monitor['width']}x{monitor['height']}")
                # Clear screenshot buffer to free memory
                del screenshot
    except Exception as e:
        logger.error(f"Multi-monitor capture failed: {e}")

    return images


class TieredCaptureManager:
    """
    Smart tiered screenshot capture strategy.

    Tiers:
    1. Active window only (frequent) - every 5s when window changes
    2. Active monitor (medium) - every 30s
    3. All monitors (rare) - every 2-5 minutes for full context

    This saves CPU/memory while maintaining good context capture.
    """

    def __init__(
        self,
        active_window_interval: float = 5.0,
        active_monitor_interval: float = 30.0,
        full_capture_interval: float = 120.0,  # 2 minutes
    ):
        self.active_window_interval = active_window_interval
        self.active_monitor_interval = active_monitor_interval
        self.full_capture_interval = full_capture_interval

        self._last_active_window_capture = 0
        self._last_active_monitor_capture = 0
        self._last_full_capture = 0
        self._last_window_id = None

        # Cache for full capture result
        self._full_capture_cache = None
        self._full_capture_ocr_cache = None

    def get_capture_mode(self, window_changed: bool = False) -> str:
        """
        Determine which capture mode to use based on timing and window state.

        Returns: "active_window", "active_monitor", "full", or "skip"
        """
        import time

        now = time.time()

        # Check if full capture is due (every 2-5 minutes)
        if now - self._last_full_capture >= self.full_capture_interval:
            return "full"

        # Check if active monitor capture is due
        if now - self._last_active_monitor_capture >= self.active_monitor_interval:
            return "active_monitor"

        # Window changed - capture active window
        if window_changed:
            return "active_window"

        # Check if active window capture is due
        if now - self._last_active_window_capture >= self.active_window_interval:
            return "active_window"

        return "skip"

    def capture(self, mode: str = "auto", window_changed: bool = False) -> Dict[str, Any]:
        """
        Perform capture based on mode or automatic selection.

        Args:
            mode: "auto", "active_window", "active_monitor", "full"
            window_changed: Whether the active window changed

        Returns:
            Dict with:
            - image: PIL Image (or list for full capture)
            - mode: Capture mode used
            - monitor_count: Number of monitors captured
        """
        import time

        if mode == "auto":
            mode = self.get_capture_mode(window_changed)

        if mode == "skip":
            return {"image": None, "mode": "skip", "monitor_count": 0}

        now = time.time()
        result = {"mode": mode, "monitor_count": 0}

        if mode == "active_window":
            # Capture just the active window (smallest, fastest)
            image = capture_screen(window_only=True)
            result["image"] = image
            result["monitor_count"] = 1 if image else 0
            self._last_active_window_capture = now
            logger.debug("Captured active window")

        elif mode == "active_monitor":
            # Capture the monitor where mouse/active window is
            image = capture_screen(window_only=False)
            result["image"] = image
            result["monitor_count"] = 1 if image else 0
            self._last_active_monitor_capture = now
            self._last_active_window_capture = now
            logger.debug("Captured active monitor")

        elif mode == "full":
            # Capture all monitors
            images = capture_all_monitors()
            result["image"] = images[0] if len(images) == 1 else images
            result["monitor_count"] = len(images)
            result["all_images"] = images
            self._last_full_capture = now
            self._last_active_monitor_capture = now
            self._last_active_window_capture = now
            logger.info(f"Full capture: {len(images)} monitor(s)")

        return result

    def get_status(self) -> Dict[str, Any]:
        """Get timing status for all capture tiers."""
        import time

        now = time.time()
        return {
            "since_active_window": now - self._last_active_window_capture,
            "since_active_monitor": now - self._last_active_monitor_capture,
            "since_full_capture": now - self._last_full_capture,
            "next_active_window": max(
                0, self.active_window_interval - (now - self._last_active_window_capture)
            ),
            "next_active_monitor": max(
                0, self.active_monitor_interval - (now - self._last_active_monitor_capture)
            ),
            "next_full_capture": max(
                0, self.full_capture_interval - (now - self._last_full_capture)
            ),
        }


# Global instance for easy access
_tiered_capture_manager: Optional[TieredCaptureManager] = None


def get_tiered_capture_manager(
    active_window_interval: float = 5.0,
    active_monitor_interval: float = 30.0,
    full_capture_interval: float = 120.0,
) -> TieredCaptureManager:
    """Get or create the tiered capture manager singleton."""
    global _tiered_capture_manager
    if _tiered_capture_manager is None:
        _tiered_capture_manager = TieredCaptureManager(
            active_window_interval=active_window_interval,
            active_monitor_interval=active_monitor_interval,
            full_capture_interval=full_capture_interval,
        )
    return _tiered_capture_manager


def ocr_image(image, engine: str = "auto") -> str:
    """
    Perform OCR on an image.

    Args:
        image: PIL Image object
        engine: "auto", "apple_vision", "windows", "rapidocr", or "tesseract"

    Returns:
        Extracted text as string
    """
    if engine == "auto":
        engine = OCR_ENGINE

    if engine == "apple_vision":
        return _ocr_apple_vision(image)
    elif engine == "windows":
        return _ocr_windows(image)
    elif engine == "rapidocr":
        return _ocr_rapidocr(image)
    elif engine == "tesseract":
        return _ocr_tesseract(image)
    else:
        logger.error(f"Unknown OCR engine: {engine}")
        return ""


def ocr_image_structured(image) -> Dict[str, Any]:
    """
    Perform structured OCR on an image, extracting text by screen position.

    Only available with Apple Vision on macOS. Falls back to basic OCR on other platforms.

    Args:
        image: PIL Image object

    Returns:
        Dict with:
        - title_bar: Text from window title area (document names)
        - menu_bar: Menu and ribbon text
        - content: Main content area text
        - full_text: All text combined
        - barcodes: List of detected barcode/QR payloads
    """
    if OCR_ENGINE == "apple_vision":
        return _ocr_apple_vision_structured(image)
    else:
        # Fallback for non-Apple platforms
        text = ocr_image(image)
        return {"title_bar": "", "menu_bar": "", "content": text, "full_text": text, "barcodes": []}


def _ocr_apple_vision(image) -> str:
    """OCR using Apple Vision Framework (macOS Neural Engine accelerated)."""
    import os

    temp_path = None
    try:
        from ocrmac import ocrmac

        # Save image to temp file (ocrmac requires file path)
        # Use delete=False so we control cleanup, ensuring it happens even on error
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            image.save(f, format="PNG")
            temp_path = f.name

        # Run OCR using Apple Vision
        result = ocrmac.OCR(temp_path).recognize()

        # Extract text from results (list of tuples)
        text = " ".join([r[0] for r in result])
        return text

    except Exception as e:
        logger.error(f"Apple Vision OCR failed: {e}")
        return ""
    finally:
        # Always clean up temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _ocr_apple_vision_structured(image) -> Dict[str, Any]:
    """
    OCR using Apple Vision with position-based text extraction.

    Returns text categorized by screen position:
    - title_bar: Text from top of screen (document names, window titles)
    - menu_bar: Menu items and ribbon
    - content: Main content area
    - barcodes: Any detected barcodes/QR codes
    """
    import os

    temp_path = None
    try:
        from ocrmac import ocrmac

        # Save image to temp file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            image.save(f, format="PNG")
            temp_path = f.name

        # Run OCR with position data
        result = ocrmac.OCR(temp_path).recognize()

        # Categorize text by Y position (Vision uses normalized coords, 0=bottom, 1=top)
        title_bar = []  # y > 0.92 (top ~8% of screen)
        menu_bar = []  # 0.85 < y <= 0.92 (next ~7%)
        content = []  # y <= 0.85 (rest of screen)

        for item in result:
            text = item[0]
            # item[1] is confidence, item[2] is bounding box
            if len(item) >= 3 and item[2]:
                bbox = item[2]
                # bbox format: (x, y, width, height) - y is from bottom
                y_pos = bbox[1] if len(bbox) >= 2 else 0

                if y_pos > 0.92:
                    title_bar.append(text)
                elif y_pos > 0.85:
                    menu_bar.append(text)
                else:
                    content.append(text)
            else:
                content.append(text)

        # Try to detect barcodes/QR codes using Vision framework directly
        barcodes = _detect_barcodes_vision(temp_path) if os.path.exists(temp_path) else []

        return {
            "title_bar": " ".join(title_bar),
            "menu_bar": " ".join(menu_bar),
            "content": " ".join(content),
            "full_text": " ".join([r[0] for r in result]),
            "barcodes": barcodes,
        }

    except Exception as e:
        logger.error(f"Apple Vision structured OCR failed: {e}")
        return {"title_bar": "", "menu_bar": "", "content": "", "full_text": "", "barcodes": []}
    finally:
        # Always clean up temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _detect_barcodes_vision(image_path: str) -> List[str]:
    """
    Detect barcodes and QR codes using Apple Vision Framework.

    Returns list of detected barcode/QR code payloads.
    """
    try:
        import Quartz
        import Vision
        from Foundation import NSURL

        # Load image
        image_url = NSURL.fileURLWithPath_(image_path)
        image_source = Quartz.CGImageSourceCreateWithURL(image_url, None)
        if not image_source:
            return []

        cg_image = Quartz.CGImageSourceCreateImageAtIndex(image_source, 0, None)
        if not cg_image:
            return []

        # Create barcode detection request
        request = Vision.VNDetectBarcodesRequest.alloc().init()

        # Create handler and perform request
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
        success = handler.performRequests_error_([request], None)

        if not success:
            return []

        # Extract barcode payloads
        barcodes = []
        for observation in request.results() or []:
            if hasattr(observation, "payloadStringValue") and observation.payloadStringValue():
                barcodes.append(observation.payloadStringValue())

        return barcodes

    except ImportError:
        logger.debug("Vision framework not available for barcode detection")
        return []
    except Exception as e:
        logger.debug(f"Barcode detection failed: {e}")
        return []


def _ocr_windows(image) -> str:
    """OCR using Windows OCR API."""
    try:
        import asyncio
        from io import BytesIO

        import winocr

        # Save image to bytes
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        # Run OCR (async API)
        async def run_ocr():
            result = await winocr.recognize_pil(image, lang="en")
            return result.text

        # Run async function
        loop = asyncio.new_event_loop()
        try:
            text = loop.run_until_complete(run_ocr())
        finally:
            loop.close()

        return text

    except Exception as e:
        logger.error(f"Windows OCR failed: {e}")
        return ""


def _ocr_rapidocr(image) -> str:
    """OCR using RapidOCR (ONNX-based PaddleOCR models)."""
    global _rapidocr_singleton

    try:
        import numpy as np

        # Use singleton to avoid memory leak from recreating engine
        if _rapidocr_singleton is None:
            from rapidocr_onnxruntime import RapidOCR
            _rapidocr_singleton = RapidOCR()

        # Convert PIL Image to numpy array
        img_array = np.array(image)

        # Run OCR - returns list of (box, text, confidence) tuples
        result, _ = _rapidocr_singleton(img_array)

        # Clean up numpy array
        del img_array

        if not result:
            return ""

        # Extract text from results, sorted by vertical position (top to bottom)
        # Each result item is [box_coords, text, confidence]
        text_lines = []
        for item in result:
            if len(item) >= 2:
                text_lines.append(item[1])

        return " ".join(text_lines)

    except ImportError:
        logger.error("RapidOCR not installed. Run: pip install rapidocr_onnxruntime")
        return ""
    except Exception as e:
        logger.error(f"RapidOCR failed: {e}")
        return ""


def _ocr_tesseract(image) -> str:
    """OCR using Tesseract."""
    try:
        import pytesseract

        # Configure for speed vs accuracy
        config = "--oem 3 --psm 3"  # Default OCR engine mode, auto page segmentation

        text = pytesseract.image_to_string(image, config=config)
        return text

    except Exception as e:
        logger.error(f"Tesseract OCR failed: {e}")
        return ""


def extract_keywords(text: str, max_keywords: int = 20) -> List[str]:
    """
    Extract meaningful keywords from OCR text.

    Filters out:
    - Very short words
    - Common stop words
    - Duplicates
    """
    if not text:
        return []

    # Common stop words to filter
    STOP_WORDS = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "of",
        "for",
        "to",
        "from",
        "by",
        "with",
        "as",
        "at",
        "in",
        "on",
        "into",
        "through",
        "about",
        "above",
        "below",
        "between",
        "under",
        "over",
        "after",
        "before",
        "during",
        "while",
        "if",
        "then",
        "else",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "also",
        "now",
        "here",
        "there",
    }

    # Tokenize: split on whitespace and punctuation
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]*\b", text.lower())

    # Filter
    keywords = []
    seen = set()
    for word in words:
        if len(word) >= 3 and word not in STOP_WORDS and word not in seen and not word.isdigit():
            keywords.append(word)
            seen.add(word)
            if len(keywords) >= max_keywords:
                break

    return keywords


def extract_entities(text: str) -> Dict[str, List[str]]:
    """
    Extract named entities from OCR text.

    Extracts:
    - Email addresses
    - URLs
    - Phone numbers
    - Dates
    - Money amounts
    """
    entities: Dict[str, List[str]] = {}

    if not text:
        return entities

    # Email addresses
    emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
    if emails:
        entities["emails"] = list(set(emails))[:5]

    # URLs
    urls = re.findall(r'https?://[^\s<>"{}|\\^`\[\]]+', text)
    if urls:
        entities["urls"] = list(set(urls))[:5]

    # Phone numbers (various formats)
    phones = re.findall(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", text)
    if phones:
        entities["phones"] = list(set(phones))[:3]

    # Dates (common formats)
    dates = re.findall(
        r"\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if dates:
        entities["dates"] = list(set(dates))[:5]

    # Money amounts
    amounts = re.findall(
        r"\$[\d,]+(?:\.\d{2})?|\b\d+(?:,\d{3})*(?:\.\d{2})?\s*(?:USD|EUR|GBP)\b", text
    )
    if amounts:
        entities["amounts"] = list(set(amounts))[:5]

    return entities


def capture_and_ocr(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Main function: capture screen and extract text data.

    Args:
        config: OCR configuration dict
            - capture_all_monitors: bool - If True, OCR all monitors
            - engine: str - OCR engine to use
            - extract_mode: str - keywords, entities, or full_text
            - max_keywords: int - Maximum keywords to extract

    Returns:
        Dict with 'keywords', 'entities', and optionally 'full_text'
    """
    if not OCR_AVAILABLE:
        return None

    engine = config.get("engine", "auto")
    all_text = []

    # Check if we should capture all monitors
    if config.get("capture_all_monitors", False):
        images = capture_all_monitors()
        if not images:
            # Fallback to monitor under cursor
            image = capture_screen(window_only=False)
            if image:
                images = [image]

        # OCR each monitor and clean up images
        for i, image in enumerate(images):
            try:
                text = ocr_image(image, engine=engine)
                if text:
                    all_text.append(text)
                    logger.debug(f"OCR monitor {i + 1}: {len(text)} chars")
            finally:
                # Clean up image to prevent memory leak
                try:
                    image.close()
                except Exception:
                    pass
        del images
    else:
        # Capture monitor under mouse cursor (better for multi-monitor setups)
        # This ensures we OCR the screen the user is actually looking at
        image = capture_screen(window_only=False)
        if image is None:
            # Fallback to active window
            image = capture_screen(window_only=True)
        if image is None:
            return None

        try:
            text = ocr_image(image, engine=engine)
            if text:
                all_text.append(text)
        finally:
            # Clean up image to prevent memory leak
            try:
                image.close()
            except Exception:
                pass
            del image

    if not all_text:
        return None

    # Combine text from all sources
    combined_text = "\n\n".join(all_text)

    result: Dict[str, Any] = {}

    # Extract based on mode
    extract_mode = config.get("extract_mode", "keywords")
    max_keywords = config.get("max_keywords", 20)

    if extract_mode in ("keywords", "full_text"):
        result["keywords"] = extract_keywords(combined_text, max_keywords)

    if extract_mode in ("entities", "full_text"):
        result["entities"] = extract_entities(combined_text)

    if extract_mode == "full_text":
        # Truncate for storage
        result["text"] = combined_text[:2000]

    # Add monitor count info if multi-monitor
    if config.get("capture_all_monitors", False):
        result["monitors_captured"] = len(all_text)

    return result


def capture_and_ocr_focused_window() -> Optional[Dict[str, Any]]:
    """
    Convenience function to capture and OCR just the focused window.

    Returns:
        Dict with 'keywords' or None
    """
    return capture_and_ocr(
        {
            "capture_all_monitors": False,
            "extract_mode": "keywords",
            "max_keywords": 20,
        }
    )


def capture_and_ocr_all_screens() -> Optional[Dict[str, Any]]:
    """
    Convenience function to capture and OCR all monitors.

    Returns:
        Dict with 'keywords' and 'monitors_captured' or None
    """
    return capture_and_ocr(
        {
            "capture_all_monitors": True,
            "extract_mode": "keywords",
            "max_keywords": 30,  # More keywords for multiple screens
        }
    )


# Test the module
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print(f"OCR Available: {OCR_AVAILABLE}")
    print(f"OCR Engine: {OCR_ENGINE}")

    if OCR_AVAILABLE:
        print("\nCapturing and performing OCR...")
        config = {"extract_mode": "keywords", "max_keywords": 15}
        result = capture_and_ocr(config)
        print(f"Result: {result}")
