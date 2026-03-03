"""
Tests for adaptive OCR triggering logic.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def watcher():
    """Create an EnhancedWatcher with mocked client and adaptive trigger."""
    with patch("aw_watcher_enhanced.main.ActivityWatchClient"):
        from aw_watcher_enhanced.main import EnhancedWatcher

        w = EnhancedWatcher(testing=True, enable_ocr=False, enable_llm=False)
        # Force adaptive trigger mode
        w.config["ocr"]["trigger"] = "adaptive"
        w.config["ocr"]["periodic_interval"] = 30
        w.config["ocr"]["adaptive_fallback_interval"] = 300
        return w


class TestIsDataRich:
    """Tests for _is_data_rich helper."""

    def test_empty_data_is_not_rich(self, watcher):
        """Data with no AX, no document, and no URL is thin."""
        data = {"app": "SomeApp", "title": "SomeTitle"}
        assert watcher._is_data_rich(data) is False

    def test_ax_role_makes_data_rich(self, watcher):
        """Having focused_element_role means AX is working — data is rich."""
        data = {"app": "Code", "title": "main.py", "focused_element_role": "AXTextField"}
        assert watcher._is_data_rich(data) is True

    def test_document_context_makes_data_rich(self, watcher):
        """Having document context from title parsing is sufficient."""
        data = {"app": "Code", "title": "main.py", "document": {"filename": "main.py"}}
        assert watcher._is_data_rich(data) is True

    def test_browser_without_url_is_thin(self, watcher):
        """Browser app with no URL from aw-watcher-web is thin data."""
        data = {
            "app": "Google Chrome",
            "title": "New Tab",
            "focused_element_role": "AXWebArea",
        }
        assert watcher._is_data_rich(data) is False

    def test_browser_with_url_and_ax_is_rich(self, watcher):
        """Browser with URL and AX data is rich."""
        data = {
            "app": "Google Chrome",
            "title": "GitHub",
            "focused_element_role": "AXWebArea",
            "url": "https://github.com",
        }
        assert watcher._is_data_rich(data) is True

    def test_ax_role_empty_string_not_rich(self, watcher):
        """Empty string for focused_element_role doesn't count."""
        data = {"app": "Code", "title": "main.py", "focused_element_role": ""}
        assert watcher._is_data_rich(data) is False

    def test_non_browser_without_ax_but_with_document(self, watcher):
        """Non-browser app without AX but with document context is still rich."""
        data = {
            "app": "Microsoft Excel",
            "title": "Report.xlsx - Excel",
            "document": {"filename": "Report.xlsx"},
        }
        assert watcher._is_data_rich(data) is True


class TestAdaptiveOCRTrigger:
    """Tests for _should_capture_ocr in adaptive mode."""

    def test_idle_skips_ocr(self, watcher):
        """Idle user should skip OCR."""
        if watcher.idle_detector:
            with patch.object(watcher.idle_detector, "is_idle", return_value=True), \
                 patch.object(watcher.idle_detector, "get_idle_seconds", return_value=120.0):
                data = {"app": "Code", "title": "main.py"}
                assert watcher._should_capture_ocr(data) is False

    def test_first_capture_always_runs(self, watcher):
        """Very first capture should always trigger OCR (baseline)."""
        watcher.last_window_data = None
        watcher.last_ocr_time = None
        data = {"app": "Code", "title": "main.py"}
        assert watcher._should_capture_ocr(data) is True

    def test_rich_data_skips_frequent_ocr(self, watcher):
        """Rich data should skip OCR when recently captured."""
        watcher.last_window_data = {"app": "Code", "title": "main.py"}
        watcher.last_ocr_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        data = {
            "app": "Code",
            "title": "main.py",
            "focused_element_role": "AXTextField",
        }
        assert watcher._should_capture_ocr(data) is False

    def test_rich_data_fires_on_safety_net(self, watcher):
        """Rich data should still fire OCR after fallback interval (5 min)."""
        watcher.last_window_data = {"app": "Code", "title": "main.py"}
        watcher.last_ocr_time = datetime.now(timezone.utc) - timedelta(seconds=301)
        data = {
            "app": "Code",
            "title": "main.py",
            "focused_element_role": "AXTextField",
        }
        assert watcher._should_capture_ocr(data) is True

    def test_thin_data_fires_on_window_change(self, watcher):
        """Thin data + window change should trigger OCR."""
        watcher.last_window_data = {"app": "OtherApp", "title": "Old Title"}
        watcher.last_ocr_time = datetime.now(timezone.utc) - timedelta(seconds=2)
        data = {"app": "UnknownApp", "title": "No Context"}
        assert watcher._should_capture_ocr(data) is True

    def test_thin_data_fires_periodically(self, watcher):
        """Thin data should fire OCR on periodic interval (30s)."""
        watcher.last_window_data = {"app": "UnknownApp", "title": "No Context"}
        watcher.last_ocr_time = datetime.now(timezone.utc) - timedelta(seconds=31)
        data = {"app": "UnknownApp", "title": "No Context"}
        assert watcher._should_capture_ocr(data) is True

    def test_thin_data_skips_within_interval(self, watcher):
        """Thin data should NOT fire OCR if recently captured and window didn't change."""
        watcher.last_window_data = {"app": "UnknownApp", "title": "No Context"}
        watcher.last_ocr_time = datetime.now(timezone.utc) - timedelta(seconds=5)
        data = {"app": "UnknownApp", "title": "No Context"}
        assert watcher._should_capture_ocr(data) is False

    def test_remote_desktop_always_captures(self, watcher):
        """Remote desktop apps should always get OCR regardless of data richness."""
        watcher.last_window_data = {"app": "Windows App", "title": "Remote PC"}
        watcher.last_ocr_time = datetime.now(timezone.utc) - timedelta(seconds=11)
        data = {
            "app": "Windows App",
            "title": "Remote PC",
            "focused_element_role": "AXGroup",
        }
        assert watcher._should_capture_ocr(data) is True

    def test_remote_desktop_respects_interval(self, watcher):
        """Remote desktop should still respect the remote_desktop_interval."""
        watcher.last_window_data = {"app": "Windows App", "title": "Remote PC"}
        watcher.last_ocr_time = datetime.now(timezone.utc) - timedelta(seconds=5)
        data = {"app": "Windows App", "title": "Remote PC"}
        assert watcher._should_capture_ocr(data) is False

    def test_browser_no_url_triggers_ocr(self, watcher):
        """Browser without URL should trigger OCR (data is thin)."""
        watcher.last_window_data = {"app": "OtherApp", "title": "Old"}
        watcher.last_ocr_time = None
        data = {"app": "Google Chrome", "title": "Some Page"}
        assert watcher._should_capture_ocr(data) is True

    def test_transition_capture_fires(self, watcher):
        """Transition pending should fire OCR on the incoming window."""
        watcher._transition_pending = True
        watcher.last_window_data = {"app": "Code", "title": "main.py"}
        watcher.last_ocr_time = datetime.now(timezone.utc)
        data = {"app": "Code", "title": "main.py"}
        result = watcher._should_capture_ocr(data)
        assert result is True
        assert data.get("transition") is True


class TestLegacyTriggerModes:
    """Tests for backward-compatible legacy trigger modes."""

    def test_window_change_mode(self, watcher):
        """window_change mode fires only on window change."""
        watcher.config["ocr"]["trigger"] = "window_change"
        watcher.last_window_data = {"app": "Code", "title": "main.py"}
        data = {"app": "Code", "title": "main.py"}
        assert watcher._should_capture_ocr(data) is False

    def test_window_change_mode_fires(self, watcher):
        """window_change mode fires when window changes."""
        watcher.config["ocr"]["trigger"] = "window_change"
        watcher.last_window_data = {"app": "Code", "title": "main.py"}
        data = {"app": "Chrome", "title": "GitHub"}
        assert watcher._should_capture_ocr(data) is True

    def test_periodic_mode(self, watcher):
        """periodic mode fires on interval."""
        watcher.config["ocr"]["trigger"] = "periodic"
        watcher.last_window_data = {"app": "Code", "title": "main.py"}
        watcher.last_ocr_time = datetime.now(timezone.utc) - timedelta(seconds=31)
        data = {"app": "Code", "title": "main.py"}
        assert watcher._should_capture_ocr(data) is True

    def test_smart_mode_window_change(self, watcher):
        """smart mode fires on window change."""
        watcher.config["ocr"]["trigger"] = "smart"
        watcher.last_window_data = {"app": "Code", "title": "main.py"}
        data = {"app": "Chrome", "title": "GitHub"}
        assert watcher._should_capture_ocr(data) is True

    def test_smart_mode_periodic(self, watcher):
        """smart mode fires on periodic interval for same window."""
        watcher.config["ocr"]["trigger"] = "smart"
        watcher.last_window_data = {"app": "Code", "title": "main.py"}
        watcher.last_ocr_time = datetime.now(timezone.utc) - timedelta(seconds=61)
        data = {"app": "Code", "title": "main.py"}
        assert watcher._should_capture_ocr(data) is True
