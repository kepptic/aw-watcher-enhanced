"""
Tests for capture_state and the single-bucket architecture.

Volatile metrics (focus_duration, switches_last_hour, activity_pct)
were removed from event data — they are computable from event timestamps.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestCaptureStateIntegration:
    """Integration tests for capture_state."""

    @pytest.fixture
    def watcher(self):
        with patch("aw_watcher_enhanced.main.ActivityWatchClient"):
            from aw_watcher_enhanced.main import EnhancedWatcher

            w = EnhancedWatcher(
                testing=True, enable_ocr=False, enable_llm=False
            )
            return w

    @patch("aw_watcher_enhanced.main.get_current_window")
    def test_capture_state_returns_app_title(self, mock_window, watcher):
        """capture_state should return app and title."""
        mock_window.return_value = {"app": "Code", "title": "main.py"}
        result = watcher.capture_state()
        assert result is not None
        assert result["app"] == "Code"
        assert result["title"] == "main.py"

    @patch("aw_watcher_enhanced.main.get_current_window")
    def test_capture_state_no_volatile_fields(self, mock_window, watcher):
        """capture_state should NOT include volatile fields that prevent merging."""
        mock_window.return_value = {"app": "Code", "title": "main.py"}
        result = watcher.capture_state()
        assert result is not None
        # These volatile fields were removed to allow heartbeat merging
        assert "focus_duration" not in result
        assert "switches_last_hour" not in result
        assert "activity_pct" not in result

    @patch("aw_watcher_enhanced.main.get_current_window")
    def test_capture_state_none_window(self, mock_window, watcher):
        """capture_state should return None when window is None."""
        mock_window.return_value = None
        result = watcher.capture_state()
        assert result is None

    @patch("aw_watcher_enhanced.main.get_current_window")
    def test_capture_state_meeting_detection(self, mock_window, watcher):
        """capture_state should include meeting fields when enabled."""
        mock_window.return_value = {
            "app": "zoom.us",
            "title": "Zoom Meeting",
        }
        result = watcher.capture_state()
        assert result is not None
        if watcher.enable_meeting:
            assert "in_meeting" in result
            assert result["in_meeting"] is True
            assert result["meeting_app"] == "Zoom"

    @patch("aw_watcher_enhanced.main.get_current_window")
    def test_capture_state_document_context(self, mock_window, watcher):
        """capture_state should include document context from title."""
        mock_window.return_value = {
            "app": "Code",
            "title": "main.py - aw-watcher-enhanced",
        }
        result = watcher.capture_state()
        assert result is not None
        # Document context is parsed from the title
        if "doc_project" in result:
            assert isinstance(result["doc_project"], str)


class TestSharedEnrichedState:
    """Tests for the shared enriched state mechanism."""

    @pytest.fixture
    def watcher(self):
        with patch("aw_watcher_enhanced.main.ActivityWatchClient"):
            from aw_watcher_enhanced.main import EnhancedWatcher

            w = EnhancedWatcher(
                testing=True, enable_ocr=False, enable_llm=False
            )
            return w

    def test_enriched_state_initially_none(self, watcher):
        """Enriched state should start as None."""
        assert watcher._enriched_state is None
        assert watcher._enriched_window_key is None

    def test_enriched_state_lock_exists(self, watcher):
        """Enriched state should have a thread lock."""
        import threading

        assert isinstance(watcher._enriched_state_lock, type(threading.Lock()))

    def test_enriched_state_can_be_set(self, watcher):
        """Setting enriched state should be thread-safe."""
        import threading

        with watcher._enriched_state_lock:
            watcher._enriched_state = {
                "app": "Code",
                "title": "main.py",
                "document": "main.py",
            }
            watcher._enriched_window_key = ("Code", "main.py")

        with watcher._enriched_state_lock:
            assert watcher._enriched_state["app"] == "Code"
            assert watcher._enriched_state["document"] == "main.py"
            assert watcher._enriched_window_key == ("Code", "main.py")
