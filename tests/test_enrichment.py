"""
Tests for the two-bucket architecture and enrichment worker.
"""

import os
import sys
import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from aw_watcher_enhanced.enrichment import EnrichmentWorker
from aw_watcher_enhanced.window import get_window_fast


class TestGetWindowFast:
    """Tests for the lightweight window capture function."""

    def test_returns_dict_or_none(self):
        result = get_window_fast()
        assert result is None or isinstance(result, dict)

    def test_result_has_only_app_and_title(self):
        result = get_window_fast()
        if result is not None:
            assert "app" in result
            assert "title" in result
            # Should NOT have deep AX fields
            assert "focused_element_role" not in result
            assert "focused_element_context" not in result

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_macos_not_loginwindow(self):
        result = get_window_fast()
        if result is not None:
            assert result["app"] != "loginwindow"


class TestGetAllWindows:
    """Tests for the all-windows snapshot function."""

    def test_import(self):
        from aw_watcher_enhanced.window import get_all_windows

        assert callable(get_all_windows)

    def test_returns_list(self):
        from aw_watcher_enhanced.window import get_all_windows

        result = get_all_windows()
        assert isinstance(result, list)

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_entries_have_app_and_title(self):
        from aw_watcher_enhanced.window import get_all_windows

        result = get_all_windows()
        for entry in result:
            assert "app" in entry
            assert "title" in entry


class TestEnrichmentWorker:
    """Tests for EnrichmentWorker."""

    def _make_mock_watcher(self):
        mock_watcher = MagicMock()
        mock_watcher.running = True
        mock_watcher._enriched_state = None
        mock_watcher._enriched_state_lock = threading.Lock()
        mock_watcher._enriched_window_key = None
        return mock_watcher

    def test_creation(self):
        mock_watcher = self._make_mock_watcher()
        worker = EnrichmentWorker(
            watcher=mock_watcher,
            periodic_interval=1.0,
        )
        assert worker.periodic_interval == 1.0

    def test_notify_window_change(self):
        mock_watcher = self._make_mock_watcher()
        worker = EnrichmentWorker(watcher=mock_watcher)
        # Should not raise
        worker.notify_window_change()

    @staticmethod
    def _wait_for(condition, timeout=2.0, interval=0.05):
        """Poll until condition() is truthy or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if condition():
                return True
            time.sleep(interval)
        return condition()

    def test_start_and_stop(self):
        mock_watcher = self._make_mock_watcher()
        mock_watcher.capture_state.return_value = None

        worker = EnrichmentWorker(
            watcher=mock_watcher,
            periodic_interval=0.1,
        )
        worker.start()
        assert worker._thread is not None
        assert worker._thread.is_alive()

        mock_watcher.running = False
        worker.stop()

    def test_captures_on_window_change(self):
        mock_watcher = self._make_mock_watcher()
        mock_watcher.capture_state.return_value = {
            "app": "Code",
            "title": "main.py",
        }

        worker = EnrichmentWorker(
            watcher=mock_watcher,
            periodic_interval=10.0,  # Long so only triggered by change
        )
        worker.start()

        # Trigger window change
        worker.notify_window_change()
        assert self._wait_for(lambda: mock_watcher.capture_state.called)

        mock_watcher.running = False
        worker.stop()

        assert mock_watcher.capture_state.called

    def test_stores_enriched_state(self):
        """Enrichment should store data in watcher's shared state."""
        mock_watcher = self._make_mock_watcher()
        mock_watcher.capture_state.return_value = {
            "app": "Code",
            "title": "main.py",
            "document": "main.py",
        }

        worker = EnrichmentWorker(
            watcher=mock_watcher,
            periodic_interval=10.0,
        )
        worker.start()

        worker.notify_window_change()
        assert self._wait_for(lambda: mock_watcher._enriched_state is not None)

        mock_watcher.running = False
        worker.stop()

        # Enriched state should be stored in watcher
        assert mock_watcher._enriched_state is not None
        assert mock_watcher._enriched_state["app"] == "Code"
        assert mock_watcher._enriched_state["document"] == "main.py"
        assert mock_watcher._enriched_window_key == ("Code", "main.py")


class TestDetectCameraMic:
    """Tests for camera/mic detection."""

    def test_import(self):
        from aw_watcher_enhanced.meeting import detect_camera_mic

        assert callable(detect_camera_mic)

    def test_returns_dict(self):
        from aw_watcher_enhanced.meeting import detect_camera_mic

        result = detect_camera_mic()
        assert isinstance(result, dict)
        assert "camera_active" in result
        assert "mic_active" in result
        assert isinstance(result["camera_active"], bool)
        assert isinstance(result["mic_active"], bool)


class TestCalendarMonitor:
    """Tests for calendar monitor."""

    def test_import(self):
        from aw_watcher_enhanced.calendar_events import CalendarMonitor

        assert callable(CalendarMonitor)

    def test_creation(self):
        from aw_watcher_enhanced.calendar_events import CalendarMonitor

        monitor = CalendarMonitor()
        # get_current_event should work even without EventKit
        result = monitor.get_current_event()
        assert result is None or isinstance(result, dict)


class TestFileActivityTracker:
    """Tests for file activity tracker."""

    def test_import(self):
        from aw_watcher_enhanced.file_events import FileActivityTracker

        assert callable(FileActivityTracker)

    def test_creation(self):
        from aw_watcher_enhanced.file_events import FileActivityTracker

        tracker = FileActivityTracker()
        result = tracker.get_recent_files()
        assert isinstance(result, list)

    def test_tracked_extensions(self):
        from aw_watcher_enhanced.file_events import _TRACKED_EXTENSIONS

        assert ".py" in _TRACKED_EXTENSIONS
        assert ".js" in _TRACKED_EXTENSIONS
        assert ".md" in _TRACKED_EXTENSIONS

    def test_ignore_patterns(self):
        from aw_watcher_enhanced.file_events import _IGNORE_PATTERNS

        assert ".git" in _IGNORE_PATTERNS
        assert "node_modules" in _IGNORE_PATTERNS
        assert "__pycache__" in _IGNORE_PATTERNS


class TestTerminalCWD:
    """Tests for terminal CWD detection and project extraction."""

    def test_extract_project_from_cwd(self):
        from aw_watcher_enhanced.document import extract_project_from_cwd

        assert extract_project_from_cwd("/Users/gr/Documents/DevOps/kepptic/products/aw-watcher-enhanced") == "aw-watcher-enhanced"
        assert extract_project_from_cwd("/Users/gr/Projects/my-app") == "my-app"
        assert extract_project_from_cwd("/Users/gr/Projects/my-app/src") == "my-app"  # goes up from generic dir
        assert extract_project_from_cwd(os.path.expanduser("~")) is None  # home dir

    def test_extract_project_from_cwd_generic_subdirs(self):
        from aw_watcher_enhanced.document import extract_project_from_cwd

        # Should go up from generic subdirectories
        assert extract_project_from_cwd("/code/myproject/src") == "myproject"
        assert extract_project_from_cwd("/code/myproject/lib") == "myproject"
        assert extract_project_from_cwd("/code/myproject/build") == "myproject"

    def test_get_terminal_cwd_returns_string_or_none(self):
        from aw_watcher_enhanced.document import get_terminal_cwd

        # Use our own PID - should return a valid CWD
        result = get_terminal_cwd(os.getpid())
        if sys.platform == "darwin":
            assert result is None or isinstance(result, str)
        else:
            # On other platforms, may not be supported
            assert result is None or isinstance(result, str)

    def test_parse_terminal_title_with_path(self):
        from aw_watcher_enhanced.document import parse_document_context

        # iTerm2-style title with path
        result = parse_document_context("iTerm2", "~/Documents/code/myproject — -zsh — 120×34")
        assert result is not None
        assert result.get("type") == "terminal"

    def test_parse_vscode_em_dash(self):
        from aw_watcher_enhanced.document import parse_document_context

        # macOS VS Code title format with em dash
        result = parse_document_context("Code", "2.1.63 — DevOps")
        assert result is not None
        assert result.get("type") == "code"
        assert result.get("filename") == "2.1.63"
        assert result.get("project") == "DevOps"

    def test_parse_vscode_standard(self):
        from aw_watcher_enhanced.document import parse_document_context

        # Standard Windows/Linux VS Code title
        result = parse_document_context("Code", "main.py - aw-watcher-enhanced - Visual Studio Code")
        assert result is not None
        assert result.get("filename") == "main.py"
        assert result.get("project") == "aw-watcher-enhanced"


class TestOSEventListener:
    """Tests for OS event listener."""

    def test_import(self):
        from aw_watcher_enhanced.os_events import OSEventListener

        assert callable(OSEventListener)

    def test_creation(self):
        from aw_watcher_enhanced.os_events import OSEventListener

        listener = OSEventListener()
        # Thread-safe accessors should work even before start
        assert listener.flush_events() == []
        assert listener.get_music_state() is None
        assert listener.get_clipboard_data() is None

    def test_add_event_internal(self):
        from aw_watcher_enhanced.os_events import OSEventListener

        listener = OSEventListener()
        listener._add_event("test_event", {"key": "value"})

        events = listener.flush_events()
        assert len(events) == 1
        assert events[0]["type"] == "test_event"
        assert events[0]["key"] == "value"
        assert "timestamp" in events[0]

    def test_flush_clears_events(self):
        from aw_watcher_enhanced.os_events import OSEventListener

        listener = OSEventListener()
        listener._add_event("test", {})
        listener._add_event("test2", {})

        events = listener.flush_events()
        assert len(events) == 2

        # Second flush should be empty
        events = listener.flush_events()
        assert len(events) == 0
