"""
macOS system event listeners for aw-watcher-enhanced.

Captures app lifecycle events, now-playing music, screen lock/unlock,
and clipboard changes via NSWorkspace and NSDistributedNotificationCenter.
All event-driven (zero polling cost) except clipboard (1s poll for changeCount).
"""

import logging
import platform
import sys
import threading
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from aw_client import ActivityWatchClient


class OSEventListener:
    """Listens for macOS system events and records them.

    Captures:
    - App activated/launched/terminated (NSWorkspace notifications)
    - Screen lock/unlock (NSDistributedNotificationCenter)
    - System sleep/wake (NSWorkspace notifications)
    - Space/desktop changed (NSWorkspace notifications)
    - Now-playing music from Spotify and Apple Music
    - Clipboard changes (polling NSPasteboard.changeCount)

    All data is stored in a thread-safe list and can be flushed
    by the enrichment worker to include in enriched events.
    """

    def __init__(self):
        self._running = False
        self._thread = None
        self._events_lock = threading.Lock()
        self._pending_events: deque = deque(maxlen=500)

        # Music state
        self._current_music: Optional[Dict[str, str]] = None
        self._music_lock = threading.Lock()

        # Clipboard state
        self._last_clipboard_count = -1
        self._clipboard_lock = threading.Lock()
        self._clipboard_data: Optional[Dict[str, str]] = None

    def start(self):
        """Start the event listener thread."""
        if sys.platform != "darwin":
            logger.info("OS event listener only supported on macOS")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="os-events", daemon=True
        )
        self._thread.start()
        logger.info("OS event listener started")

    def stop(self):
        """Stop the event listener thread."""
        self._running = False
        if self._thread:
            # CFRunLoop needs to be stopped from the run loop thread
            try:
                from CoreFoundation import CFRunLoopGetMain, CFRunLoopStop

                # We can't stop another thread's run loop easily;
                # the daemon=True flag ensures cleanup on exit
            except ImportError:
                pass
            self._thread.join(timeout=2.0)
        logger.info("OS event listener stopped")

    def flush_events(self) -> List[Dict]:
        """Return and clear pending system events (thread-safe)."""
        with self._events_lock:
            events = list(self._pending_events)
            self._pending_events.clear()
            return events

    def get_music_state(self) -> Optional[Dict[str, str]]:
        """Get current now-playing music info (thread-safe)."""
        with self._music_lock:
            return self._current_music.copy() if self._current_music else None

    def get_clipboard_data(self) -> Optional[Dict[str, str]]:
        """Get latest clipboard change data (thread-safe)."""
        with self._clipboard_lock:
            data = self._clipboard_data
            self._clipboard_data = None  # consume once
            return data

    def _add_event(self, event_type: str, data: Dict):
        """Thread-safe event recording."""
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        with self._events_lock:
            self._pending_events.append(event)
        logger.debug(f"OS event: {event_type} - {data}")

    def _run(self):
        """Main run loop for macOS event listeners."""
        try:
            from AppKit import NSWorkspace
            from Foundation import (
                NSAutoreleasePool,
                NSDistributedNotificationCenter,
                NSNotificationCenter,
                NSRunLoop,
            )

            # Background threads need their own autorelease pool
            pool = NSAutoreleasePool.alloc().init()

            workspace = NSWorkspace.sharedWorkspace()
            nc = workspace.notificationCenter()
            dnc = NSDistributedNotificationCenter.defaultCenter()

            # --- NSWorkspace notifications ---

            # App activated
            nc.addObserverForName_object_queue_usingBlock_(
                "NSWorkspaceDidActivateApplicationNotification",
                None,
                None,
                lambda note: self._on_app_activated(note),
            )

            # App launched
            nc.addObserverForName_object_queue_usingBlock_(
                "NSWorkspaceDidLaunchApplicationNotification",
                None,
                None,
                lambda note: self._on_app_launched(note),
            )

            # App terminated
            nc.addObserverForName_object_queue_usingBlock_(
                "NSWorkspaceDidTerminateApplicationNotification",
                None,
                None,
                lambda note: self._on_app_terminated(note),
            )

            # System sleep/wake
            nc.addObserverForName_object_queue_usingBlock_(
                "NSWorkspaceWillSleepNotification",
                None,
                None,
                lambda note: self._add_event("system_sleep", {}),
            )
            nc.addObserverForName_object_queue_usingBlock_(
                "NSWorkspaceDidWakeNotification",
                None,
                None,
                lambda note: self._add_event("system_wake", {}),
            )

            # Space changed
            nc.addObserverForName_object_queue_usingBlock_(
                "NSWorkspaceActiveSpaceDidChangeNotification",
                None,
                None,
                lambda note: self._add_event("space_changed", {}),
            )

            # --- Distributed notifications ---

            # Screen lock/unlock
            dnc.addObserverForName_object_queue_usingBlock_(
                "com.apple.screenIsLocked",
                None,
                None,
                lambda note: self._add_event("screen_locked", {}),
            )
            dnc.addObserverForName_object_queue_usingBlock_(
                "com.apple.screenIsUnlocked",
                None,
                None,
                lambda note: self._add_event("screen_unlocked", {}),
            )

            # Spotify playback state
            dnc.addObserverForName_object_queue_usingBlock_(
                "com.spotify.client.PlaybackStateChanged",
                None,
                None,
                lambda note: self._on_spotify_change(note),
            )

            # Apple Music playback state
            dnc.addObserverForName_object_queue_usingBlock_(
                "com.apple.Music.playerInfo",
                None,
                None,
                lambda note: self._on_apple_music_change(note),
            )

            logger.info(
                "Registered NSWorkspace + distributed notification observers"
            )

            # Start clipboard polling in a separate thread
            clipboard_thread = threading.Thread(
                target=self._poll_clipboard, name="clipboard", daemon=True
            )
            clipboard_thread.start()

            # Run the NSRunLoop to receive notifications
            run_loop = NSRunLoop.currentRunLoop()
            from Foundation import NSDate

            iteration = 0
            while self._running:
                run_loop.runMode_beforeDate_(
                    "kCFRunLoopDefaultMode",
                    NSDate.dateWithTimeIntervalSinceNow_(1.0),
                )
                # Drain and recreate autorelease pool periodically
                # to prevent ObjC object accumulation from notifications
                iteration += 1
                if iteration % 60 == 0:  # Every ~60 seconds
                    del pool
                    pool = NSAutoreleasePool.alloc().init()

            del pool

        except ImportError as e:
            logger.warning(f"macOS frameworks not available: {e}")
        except Exception as e:
            logger.error(f"OS event listener error: {e}", exc_info=True)

    def _get_app_info(self, notification) -> Dict[str, str]:
        """Extract app info from an NSWorkspace notification."""
        try:
            user_info = notification.userInfo()
            if not user_info:
                return {}

            app = user_info.get("NSWorkspaceApplicationKey")
            if app:
                return {
                    "app": str(app.localizedName() or ""),
                    "bundle_id": str(app.bundleIdentifier() or ""),
                    "pid": int(app.processIdentifier()),
                }
        except Exception as e:
            logger.debug(f"Error extracting app info: {e}")
        return {}

    def _on_app_activated(self, notification):
        info = self._get_app_info(notification)
        if info:
            self._add_event("app_activated", info)

    def _on_app_launched(self, notification):
        info = self._get_app_info(notification)
        if info:
            self._add_event("app_launched", info)

    def _on_app_terminated(self, notification):
        info = self._get_app_info(notification)
        if info:
            self._add_event("app_terminated", info)

    def _on_spotify_change(self, notification):
        """Handle Spotify playback state change."""
        try:
            user_info = notification.userInfo()
            if not user_info:
                return

            state = str(user_info.get("Player State", ""))
            music_data = {
                "player": "Spotify",
                "artist": str(user_info.get("Artist", "")),
                "track": str(user_info.get("Name", "")),
                "album": str(user_info.get("Album", "")),
                "state": state.lower() if state else "unknown",
            }

            with self._music_lock:
                self._current_music = music_data

            self._add_event("music_change", music_data)

        except Exception as e:
            logger.debug(f"Spotify notification error: {e}")

    def _on_apple_music_change(self, notification):
        """Handle Apple Music playback state change."""
        try:
            user_info = notification.userInfo()
            if not user_info:
                return

            state = str(user_info.get("Player State", ""))
            music_data = {
                "player": "Apple Music",
                "artist": str(user_info.get("Artist", "")),
                "track": str(user_info.get("Name", "")),
                "album": str(user_info.get("Album", "")),
                "state": state.lower() if state else "unknown",
            }

            with self._music_lock:
                self._current_music = music_data

            self._add_event("music_change", music_data)

        except Exception as e:
            logger.debug(f"Apple Music notification error: {e}")

    def _poll_clipboard(self):
        """Poll clipboard change count (cheap integer check every 1s)."""
        try:
            from AppKit import NSPasteboard
        except ImportError:
            logger.debug("NSPasteboard not available for clipboard monitoring")
            return

        pasteboard = NSPasteboard.generalPasteboard()
        self._last_clipboard_count = pasteboard.changeCount()

        while self._running:
            try:
                current_count = pasteboard.changeCount()
                if current_count != self._last_clipboard_count:
                    self._last_clipboard_count = current_count
                    self._read_clipboard(pasteboard)

                import time

                time.sleep(1.0)
            except Exception as e:
                logger.debug(f"Clipboard poll error: {e}")
                import time

                time.sleep(5.0)

    def _read_clipboard(self, pasteboard):
        """Read clipboard content on change."""
        try:
            # Determine content type
            types = pasteboard.types()
            if not types:
                return

            clipboard_type = "unknown"
            clipboard_text = ""

            type_list = list(types)
            type_strs = [str(t) for t in type_list]

            if "public.utf8-plain-text" in type_strs:
                clipboard_type = "text"
                text = pasteboard.stringForType_("public.utf8-plain-text")
                if text:
                    # Truncate for privacy
                    clipboard_text = str(text)[:200]
            elif "public.file-url" in type_strs:
                clipboard_type = "file"
                url = pasteboard.stringForType_("public.file-url")
                if url:
                    clipboard_text = str(url)[:200]
            elif any("image" in t for t in type_strs):
                clipboard_type = "image"
            elif "public.url" in type_strs:
                clipboard_type = "url"
                url = pasteboard.stringForType_("public.url")
                if url:
                    clipboard_text = str(url)[:200]

            data = {
                "clipboard_type": clipboard_type,
                "clipboard_text": clipboard_text,
            }

            with self._clipboard_lock:
                self._clipboard_data = data

        except Exception as e:
            logger.debug(f"Clipboard read error: {e}")
