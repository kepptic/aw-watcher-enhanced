"""
Cross-platform window capture for aw-watcher-enhanced.

Captures the currently active window's app name and title.
"""

import logging
import os
import sys
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _with_autorelease(func):
    """Decorator that wraps a function in an NSAutoreleasePool on macOS.

    Quartz/AppKit calls (CGWindowListCopyWindowInfo, NSWorkspace, etc.)
    return Core Foundation objects that accumulate without an autorelease
    pool. In background threads (heartbeat, enrichment) there is no
    default pool, so every CF object leaks. This decorator ensures
    cleanup after each call.
    """
    if sys.platform != "darwin":
        return func

    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            from Foundation import NSAutoreleasePool
        except ImportError:
            return func(*args, **kwargs)

        pool = NSAutoreleasePool.alloc().init()
        try:
            return func(*args, **kwargs)
        finally:
            del pool

    return wrapper


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


@_with_autorelease
def _walk_ax_parent_chain(element, max_depth: int = 5) -> str:
    """Walk the AX parent chain to build a breadcrumb context string.

    E.g. "Terminal > zsh" or "VS Code > Editor > main.py"
    """
    try:
        from HIServices import AXUIElementCopyAttributeValue
    except ImportError:
        return ""

    parts = []
    current = element
    for _ in range(max_depth):
        err, title = AXUIElementCopyAttributeValue(current, "AXTitle", None)
        if err == 0 and title:
            title_str = str(title).strip()
            if title_str and title_str not in parts:
                parts.append(title_str)

        err, role_desc = AXUIElementCopyAttributeValue(current, "AXRoleDescription", None)
        if err == 0 and role_desc:
            desc_str = str(role_desc).strip()
            # Only add role descriptions that are informative
            if desc_str and desc_str not in parts and desc_str not in (
                "application", "window", "group", "scroll area",
            ):
                parts.append(desc_str)

        err, parent = AXUIElementCopyAttributeValue(current, "AXParent", None)
        if err != 0 or not parent:
            break
        current = parent

    # Reverse so parent comes first
    parts.reverse()
    return " > ".join(parts) if parts else ""


@_with_autorelease
def _get_focused_element_details() -> Dict[str, str]:
    """Get details about the currently focused UI element using AXFocusedUIElement.

    Returns a dict with focused_element_role, focused_element_title,
    focused_element_description, and focused_element_context.
    """
    try:
        from HIServices import (
            AXUIElementCopyAttributeValue,
            AXUIElementCreateSystemWide,
        )
    except ImportError:
        return {}

    try:
        system_wide = AXUIElementCreateSystemWide()
        err, focused_element = AXUIElementCopyAttributeValue(
            system_wide, "AXFocusedUIElement", None
        )
        if err != 0 or not focused_element:
            return {}

        result = {}

        # Role (e.g. "AXTextField", "AXTextArea", "AXButton")
        err, role = AXUIElementCopyAttributeValue(focused_element, "AXRole", None)
        if err == 0 and role:
            result["focused_element_role"] = str(role)

        # Role description (e.g. "text field", "button", "tab")
        err, role_desc = AXUIElementCopyAttributeValue(
            focused_element, "AXRoleDescription", None
        )
        if err == 0 and role_desc:
            result["focused_element_title"] = str(role_desc)

        # Title of the focused element
        err, title = AXUIElementCopyAttributeValue(focused_element, "AXTitle", None)
        if err == 0 and title:
            title_str = str(title).strip()
            if title_str:
                result["focused_element_title"] = title_str

        # Description (accessibility description)
        err, desc = AXUIElementCopyAttributeValue(
            focused_element, "AXDescription", None
        )
        if err == 0 and desc:
            desc_str = str(desc).strip()
            if desc_str:
                result["focused_element_description"] = desc_str

        # Build context breadcrumb from parent chain
        context = _walk_ax_parent_chain(focused_element)
        if context:
            result["focused_element_context"] = context

        # Focused text content (what user is typing/viewing)
        err, value = AXUIElementCopyAttributeValue(
            focused_element, "AXValue", None
        )
        if err == 0 and value:
            value_str = str(value).strip()
            if value_str:
                result["focused_text"] = value_str[:500]

        # Selected text
        err, selected = AXUIElementCopyAttributeValue(
            focused_element, "AXSelectedText", None
        )
        if err == 0 and selected:
            selected_str = str(selected).strip()
            if selected_str:
                result["selected_text"] = selected_str[:500]

        return result

    except Exception as e:
        logger.debug(f"AXFocusedUIElement error: {e}")
        return {}


@_with_autorelease
def _get_focused_app_ax() -> Optional[Dict[str, str]]:
    """Get focused application and window title using system-wide Accessibility API."""
    try:
        from HIServices import (
            AXUIElementCopyAttributeValue,
            AXUIElementCreateSystemWide,
        )
    except ImportError:
        return None

    try:
        system_wide = AXUIElementCreateSystemWide()
        err, focused_app = AXUIElementCopyAttributeValue(
            system_wide, "AXFocusedApplication", None
        )
        if err != 0 or not focused_app:
            return None

        # Get app name
        err, app_name = AXUIElementCopyAttributeValue(focused_app, "AXTitle", None)
        app = str(app_name) if err == 0 and app_name else ""

        # Get focused window title
        title = ""
        err, focused_window = AXUIElementCopyAttributeValue(
            focused_app, "AXFocusedWindow", None
        )
        if err == 0 and focused_window:
            err, win_title = AXUIElementCopyAttributeValue(
                focused_window, "AXTitle", None
            )
            if err == 0 and win_title:
                title = str(win_title)

        if app:
            result = {"app": app, "title": title}
            # Get PID for terminal CWD / shell session detection
            try:
                from HIServices import AXUIElementGetPid
                err, pid_val = AXUIElementGetPid(focused_app, None)
                if err == 0 and pid_val:
                    result["pid"] = int(pid_val)
            except (ImportError, Exception):
                pass
            return result
        return None
    except Exception as e:
        logger.debug(f"System-wide Accessibility API error: {e}")
        return None


# System processes that should not be reported as the active app
_SYSTEM_APPS = frozenset({"loginwindow", "loginwindow.app", "SecurityAgent"})


@_with_autorelease
def _get_window_macos() -> Optional[Dict[str, str]]:
    """macOS implementation using Accessibility API and mouse position for multi-monitor."""
    try:
        from AppKit import NSWorkspace
    except ImportError:
        logger.error("PyObjC not installed. Run: pip install pyobjc")
        return None

    try:
        # Primary: Use system-wide Accessibility API (most reliable)
        ax_result = _get_focused_app_ax()
        if ax_result and ax_result.get("app") not in _SYSTEM_APPS:
            # Enrich with focused UI element details
            focused_details = _get_focused_element_details()
            if focused_details:
                ax_result.update(focused_details)
            # Ensure PID is set (fallback to NSWorkspace if AX didn't provide it)
            if "pid" not in ax_result:
                try:
                    workspace = NSWorkspace.sharedWorkspace()
                    active_app = workspace.frontmostApplication()
                    if active_app:
                        ax_result["pid"] = active_app.processIdentifier()
                except Exception:
                    pass
            return ax_result

        # Secondary: Check window under mouse cursor (useful for multi-monitor)
        window_under_cursor = _get_window_under_cursor()

        # Tertiary: Get frontmost app via NSWorkspace
        workspace = NSWorkspace.sharedWorkspace()
        active_app = workspace.frontmostApplication()

        if not active_app:
            if window_under_cursor and window_under_cursor.get("app") not in _SYSTEM_APPS:
                return window_under_cursor
            return {"app": "unknown", "title": ""}

        app = active_app.localizedName() or "unknown"
        app_pid = active_app.processIdentifier()

        # If NSWorkspace returns a system app, prefer window under cursor
        if app in _SYSTEM_APPS:
            if window_under_cursor and window_under_cursor.get("app") not in _SYSTEM_APPS:
                return window_under_cursor

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

        result = {"app": app, "title": title, "pid": app_pid}

        # Enrich with focused UI element details (deep AX querying)
        focused_details = _get_focused_element_details()
        if focused_details:
            result.update(focused_details)

        return result

    except Exception as e:
        logger.error(f"Error getting window (macOS): {e}")
        return None


@_with_autorelease
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


@_with_autorelease
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


@_with_autorelease
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


@_with_autorelease
def get_all_windows(resolve_terminal_cwd: bool = True) -> list:
    """Get titles of all visible on-screen windows.

    Returns list of {app, title, ...} for all visible windows (not just focused).
    For terminal windows, also resolves cwd and project name so we know
    what each terminal session is working on.
    Only supported on macOS (uses CGWindowListCopyWindowInfo).
    """
    if sys.platform != "darwin":
        return []

    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListExcludeDesktopElements,
            kCGWindowListOptionOnScreenOnly,
        )
    except ImportError:
        return []

    try:
        options = (
            kCGWindowListOptionOnScreenOnly
            | kCGWindowListExcludeDesktopElements
        )
        window_list = CGWindowListCopyWindowInfo(options, kCGNullWindowID)

        results = []
        seen = set()
        # Track PIDs we've already resolved CWD for (terminal apps share PID)
        resolved_pids = {}

        for w in window_list:
            layer = w.get("kCGWindowLayer", 0)
            if layer != 0:
                continue  # Skip system UI layers

            owner = w.get("kCGWindowOwnerName", "")
            title = w.get("kCGWindowName", "")
            if not owner:
                continue

            key = (owner, title)
            if key in seen:
                continue
            seen.add(key)

            entry = {"app": owner, "title": title or ""}

            # For terminal windows, resolve CWD and project
            if resolve_terminal_cwd and _is_terminal_app_name(owner):
                pid = w.get("kCGWindowOwnerPID")
                if pid:
                    if pid not in resolved_pids:
                        resolved_pids[pid] = _resolve_terminal_cwds(pid)
                    cwds = resolved_pids[pid]
                    if cwds:
                        # Use the first unmatched CWD (each shell child
                        # corresponds roughly to a window/tab)
                        cwd = cwds[0]
                        entry["cwd"] = cwd
                        from .document import extract_project_from_cwd
                        project = extract_project_from_cwd(cwd)
                        if project:
                            entry["project"] = project

            results.append(entry)

        return results
    except Exception as e:
        logger.debug(f"Error getting all windows: {e}")
        return []


# Terminal app names for CWD resolution in get_all_windows
_TERMINAL_APP_NAMES = {
    "terminal", "iterm2", "iterm", "alacritty", "kitty",
    "wezterm", "warp", "hyper", "konsole", "gnome-terminal",
}


def _is_terminal_app_name(app: str) -> bool:
    """Check if an app name is a terminal emulator."""
    return app.lower() in _TERMINAL_APP_NAMES


def _resolve_terminal_cwds(terminal_pid: int) -> list:
    """Get CWDs of all child shell processes under a terminal app.

    Terminal apps spawn child shells (zsh, bash, fish) — one per tab/window.
    Returns a list of CWD strings for each child shell found.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["pgrep", "-P", str(terminal_pid)],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return []

        cwds = []
        for pid_str in result.stdout.strip().split("\n"):
            if not pid_str.strip():
                continue
            child_pid = int(pid_str.strip())
            from .document import get_terminal_cwd
            cwd = get_terminal_cwd(child_pid)
            if cwd:
                cwds.append(cwd)

        return cwds
    except Exception:
        return []


def get_window_fast() -> Optional[Dict[str, str]]:
    """Get current window app and title only - lightweight for fast heartbeat.

    Returns only {app, title} without deep AX queries, cursor detection,
    or focused element details. Designed for 1s polling with minimal overhead.
    """
    if sys.platform == "win32":
        return _get_window_fast_windows()
    elif sys.platform == "darwin":
        return _get_window_fast_macos()
    else:
        return _get_window_linux()  # Linux is already lightweight


@_with_autorelease
def _get_window_fast_macos() -> Optional[Dict[str, str]]:
    """Fast macOS window capture - AX focused app + title, no deep queries."""
    try:
        # Try AX API first (gets focused app + window title without deep traversal)
        ax_result = _get_focused_app_ax()
        if ax_result and ax_result.get("app") not in _SYSTEM_APPS:
            return {"app": ax_result["app"], "title": ax_result.get("title", "")}

        # Fallback: NSWorkspace (just app name, may lack window title)
        from AppKit import NSWorkspace

        workspace = NSWorkspace.sharedWorkspace()
        active_app = workspace.frontmostApplication()
        if active_app:
            app = active_app.localizedName() or "unknown"
            if app not in _SYSTEM_APPS:
                return {"app": app, "title": ""}

        return {"app": "unknown", "title": ""}
    except Exception as e:
        logger.debug(f"Fast window capture error: {e}")
        return None


def _get_window_fast_windows() -> Optional[Dict[str, str]]:
    """Fast Windows window capture - GetForegroundWindow only."""
    try:
        import win32gui
        import win32process
    except ImportError:
        return None

    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return {"app": "unknown", "title": ""}

        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        app = _get_app_name_windows(pid)

        return {"app": app, "title": title}
    except Exception as e:
        logger.debug(f"Fast window capture error: {e}")
        return None


# Test the module directly
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("Testing window capture...")
    result = get_current_window()
    print(f"Result: {result}")

    print("\nTesting fast window capture...")
    result = get_window_fast()
    print(f"Fast result: {result}")
