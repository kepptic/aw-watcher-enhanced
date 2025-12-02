"""
Cross-platform window capture for aw-watcher-enhanced.

Captures the currently active window's app name and title.
"""

import logging
import os
import sys
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def get_current_window() -> Optional[Dict[str, str]]:
    """
    Get the currently active window's app and title.

    Returns:
        Dict with 'app' and 'title' keys, or None if capture fails.
    """
    if sys.platform == "win32":
        return _get_window_windows()
    elif sys.platform == "darwin":
        return _get_window_macos()
    else:
        return _get_window_linux()


def _get_window_windows() -> Optional[Dict[str, str]]:
    """Windows implementation using Win32 API with multi-monitor support."""
    try:
        import win32api
        import win32con
        import win32gui
        import win32process
    except ImportError:
        logger.error("pywin32 not installed. Run: pip install pywin32")
        return None

    try:
        # First check window under mouse cursor (for multi-monitor)
        window_under_cursor = _get_window_under_cursor_windows()

        # Get foreground window
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            if window_under_cursor:
                return window_under_cursor
            return {"app": "unknown", "title": ""}

        # Get window title
        title = win32gui.GetWindowText(hwnd)

        # Get process ID and app name
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        app = _get_app_name_windows(pid)

        # If window under cursor is different app, prefer that (multi-monitor case)
        if window_under_cursor and window_under_cursor.get("app") != app:
            if window_under_cursor.get("title"):
                return window_under_cursor

        return {"app": app, "title": title}

    except Exception as e:
        logger.error(f"Error getting window (Windows): {e}")
        return None


def _get_app_name_windows(pid: int) -> str:
    """Get app name from process ID on Windows."""
    try:
        import win32api
        import win32con
        import win32process

        process = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        try:
            exe_path = win32process.GetModuleFileNameEx(process, 0)
            return os.path.basename(exe_path)
        finally:
            win32api.CloseHandle(process)
    except Exception:
        return _get_app_via_wmi(pid)


def _get_window_under_cursor_windows() -> Optional[Dict[str, str]]:
    """Get the window under the mouse cursor on Windows (for multi-monitor)."""
    try:
        import ctypes
        from ctypes import wintypes

        import win32gui
        import win32process

        # Get cursor position
        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        point = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(point))

        # Get window at cursor position
        hwnd = ctypes.windll.user32.WindowFromPoint(point)
        if not hwnd:
            return None

        # Get the root owner window (top-level window)
        root_hwnd = win32gui.GetAncestor(hwnd, 3)  # GA_ROOTOWNER = 3
        if root_hwnd:
            hwnd = root_hwnd

        # Get window title
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return None

        # Get process ID and app name
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        app = _get_app_name_windows(pid)

        return {"app": app, "title": title}

    except ImportError:
        logger.debug("pywin32 not available for Windows cursor detection")
        return None
    except Exception as e:
        logger.debug(f"Error getting Windows window under cursor: {e}")
        return None


def _get_app_via_wmi(pid: int) -> str:
    """Get app name via WMI (works for elevated processes)."""
    try:
        import wmi

        c = wmi.WMI()
        for process in c.query(f"SELECT Name FROM Win32_Process WHERE ProcessId = {pid}"):
            return process.Name
    except Exception:
        pass
    return "unknown"


def _get_window_macos() -> Optional[Dict[str, str]]:
    """macOS implementation using Accessibility API and mouse position for multi-monitor."""
    try:
        from AppKit import NSWorkspace
    except ImportError:
        logger.error("PyObjC not installed. Run: pip install pyobjc")
        return None

    try:
        # First, check window under mouse cursor (better for multi-monitor)
        window_under_cursor = _get_window_under_cursor()

        # Get frontmost app as fallback
        workspace = NSWorkspace.sharedWorkspace()
        active_app = workspace.frontmostApplication()

        if not active_app:
            if window_under_cursor:
                return window_under_cursor
            return {"app": "unknown", "title": ""}

        app = active_app.localizedName() or "unknown"
        app_pid = active_app.processIdentifier()

        # If window under cursor is different app, prefer that (multi-monitor case)
        if window_under_cursor and window_under_cursor.get("app") != app:
            # User is likely working on the other monitor
            if window_under_cursor.get("title"):
                return window_under_cursor

        # Try Accessibility API first (gets the actual focused window)
        title = _get_focused_window_title_ax(app_pid)

        # Fallback to CGWindowList if Accessibility fails
        if not title:
            title = _get_window_title_cgwindow(app_pid)

        return {"app": app, "title": title}

    except Exception as e:
        logger.error(f"Error getting window (macOS): {e}")
        return None


def _get_window_under_cursor() -> Optional[Dict[str, str]]:
    """Get the window under the mouse cursor (useful for multi-monitor setups)."""
    try:
        from AppKit import NSEvent, NSScreen
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )
    except ImportError:
        return None

    try:
        # Get mouse position in Cocoa coordinates (origin bottom-left)
        mouse_ns = NSEvent.mouseLocation()

        # Get primary screen height for coordinate conversion
        screens = NSScreen.screens()
        if not screens:
            return None
        primary_height = screens[0].frame().size.height

        # Convert NSEvent coords to Quartz coords (origin top-left)
        # Quartz Y = primary_height - NSEvent Y (for primary screen)
        # For multi-monitor, we need to account for screen arrangement
        mouse_quartz_x = mouse_ns.x
        mouse_quartz_y = primary_height - mouse_ns.y

        # Get all on-screen windows
        windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)

        for w in windows:
            bounds = w.get("kCGWindowBounds", {})
            x = bounds.get("X", 0)
            y = bounds.get("Y", 0)
            width = bounds.get("Width", 0)
            height = bounds.get("Height", 0)
            layer = w.get("kCGWindowLayer", 0)

            # Skip system UI layers (menu bar, dock, notifications, etc.)
            if layer != 0:
                continue

            # Check if mouse is within window bounds
            if x <= mouse_quartz_x <= x + width and y <= mouse_quartz_y <= y + height:
                owner = w.get("kCGWindowOwnerName", "")
                title = w.get("kCGWindowName", "")

                # Only return if we have meaningful info
                if owner and title:
                    return {"app": owner, "title": title}

        return None
    except Exception as e:
        logger.debug(f"Error getting window under cursor: {e}")
        return None


def _get_focused_window_title_ax(pid: int) -> str:
    """Get focused window title using Accessibility API (most accurate)."""
    try:
        from HIServices import (
            AXUIElementCopyAttributeValue,
            AXUIElementCreateApplication,
        )
    except ImportError:
        logger.debug("HIServices not available, falling back to CGWindowList")
        return ""

    try:
        app_ref = AXUIElementCreateApplication(pid)
        err, focused_window = AXUIElementCopyAttributeValue(app_ref, "AXFocusedWindow", None)

        if err != 0 or not focused_window:
            return ""

        err, title = AXUIElementCopyAttributeValue(focused_window, "AXTitle", None)

        if err == 0 and title:
            return str(title)

        return ""
    except Exception as e:
        logger.debug(f"Accessibility API error: {e}")
        return ""


def _get_window_title_cgwindow(pid: int) -> str:
    """Fallback: Get window title using CGWindowList (may not be focused window)."""
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListExcludeDesktopElements,
            kCGWindowListOptionOnScreenOnly,
        )
    except ImportError:
        return ""

    try:
        options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
        window_list = CGWindowListCopyWindowInfo(options, kCGNullWindowID)

        for window in window_list:
            if window.get("kCGWindowOwnerPID") == pid:
                title = window.get("kCGWindowName", "") or ""
                if title:
                    return title
        return ""
    except Exception:
        return ""


def _get_window_linux() -> Optional[Dict[str, str]]:
    """Linux implementation using X11."""
    try:
        from Xlib import X, display
        from Xlib.protocol import rq
    except ImportError:
        logger.error("python-xlib not installed. Run: pip install python-xlib")
        return None

    try:
        d = display.Display()
        root = d.screen().root

        # Get active window
        NET_ACTIVE_WINDOW = d.intern_atom("_NET_ACTIVE_WINDOW")
        response = root.get_full_property(NET_ACTIVE_WINDOW, X.AnyPropertyType)

        if not response or not response.value:
            return {"app": "unknown", "title": ""}

        window_id = response.value[0]
        window = d.create_resource_object("window", window_id)

        # Get window title
        title = ""
        try:
            NET_WM_NAME = d.intern_atom("_NET_WM_NAME")
            name_prop = window.get_full_property(NET_WM_NAME, 0)
            if name_prop:
                title = name_prop.value.decode("utf-8", errors="replace")
            else:
                # Fallback to WM_NAME
                name_prop = window.get_wm_name()
                if name_prop:
                    title = name_prop
        except Exception:
            pass

        # Get app name (WM_CLASS)
        app = "unknown"
        try:
            wm_class = window.get_wm_class()
            if wm_class:
                app = wm_class[1] or wm_class[0] or "unknown"
        except Exception:
            pass

        return {"app": app, "title": title}

    except Exception as e:
        logger.error(f"Error getting window (Linux): {e}")
        return None


# Test the module directly
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("Testing window capture...")
    result = get_current_window()
    print(f"Result: {result}")
