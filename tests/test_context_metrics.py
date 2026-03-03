"""
Tests for context-switch metrics and activity tracking in the watcher.
"""

import time
from unittest.mock import MagicMock, patch

import pytest


class TestContextSwitchMetrics:
    """Tests for _compute_context_metrics in EnhancedWatcher."""

    @pytest.fixture
    def watcher(self):
        """Create an EnhancedWatcher with mocked client."""
        with patch("aw_watcher_enhanced.main.ActivityWatchClient"):
            from aw_watcher_enhanced.main import EnhancedWatcher
            w = EnhancedWatcher(testing=True, enable_ocr=False, enable_llm=False)
            return w

    def test_first_capture_zero_duration(self, watcher):
        """First capture should have focus_duration of 0."""
        data = {"app": "Code", "title": "main.py"}
        metrics = watcher._compute_context_metrics(data)
        assert metrics["focus_duration"] == 0.0
        assert metrics["switches_last_hour"] == 0

    def test_same_window_duration_increases(self, watcher):
        """Staying on same window should increase focus_duration."""
        data = {"app": "Code", "title": "main.py"}
        watcher._compute_context_metrics(data)
        time.sleep(0.1)
        metrics = watcher._compute_context_metrics(data)
        assert metrics["focus_duration"] >= 0.1
        assert metrics["switches_last_hour"] == 0

    def test_switch_resets_duration(self, watcher):
        """Switching windows should report old duration and reset."""
        data1 = {"app": "Code", "title": "main.py"}
        watcher._compute_context_metrics(data1)
        time.sleep(0.1)

        data2 = {"app": "Chrome", "title": "GitHub"}
        metrics = watcher._compute_context_metrics(data2)
        assert metrics["focus_duration"] >= 0.1
        assert metrics["switches_last_hour"] == 1

    def test_multiple_switches_counted(self, watcher):
        """Multiple switches should be counted."""
        apps = ["Code", "Chrome", "Slack", "Code", "Terminal"]
        for app in apps:
            watcher._compute_context_metrics({"app": app, "title": ""})

        metrics = watcher._compute_context_metrics({"app": "Finder", "title": ""})
        assert metrics["switches_last_hour"] == 5

    def test_title_change_counts_as_switch(self, watcher):
        """Changing title within same app counts as a switch."""
        watcher._compute_context_metrics({"app": "Code", "title": "main.py"})
        watcher._compute_context_metrics({"app": "Code", "title": "test.py"})
        metrics = watcher._compute_context_metrics({"app": "Code", "title": "utils.py"})
        assert metrics["switches_last_hour"] == 2


class TestCaptureStateIntegration:
    """Integration tests for capture_state with new metrics."""

    @pytest.fixture
    def watcher(self):
        with patch("aw_watcher_enhanced.main.ActivityWatchClient"):
            from aw_watcher_enhanced.main import EnhancedWatcher
            w = EnhancedWatcher(testing=True, enable_ocr=False, enable_llm=False)
            return w

    @patch("aw_watcher_enhanced.main.get_current_window")
    def test_capture_state_includes_focus_duration(self, mock_window, watcher):
        """capture_state should include focus_duration."""
        mock_window.return_value = {"app": "Code", "title": "main.py"}
        result = watcher.capture_state()
        assert result is not None
        assert "focus_duration" in result

    @patch("aw_watcher_enhanced.main.get_current_window")
    def test_capture_state_includes_switches_last_hour(self, mock_window, watcher):
        """capture_state should include switches_last_hour."""
        mock_window.return_value = {"app": "Code", "title": "main.py"}
        result = watcher.capture_state()
        assert result is not None
        assert "switches_last_hour" in result

    @patch("aw_watcher_enhanced.main.get_current_window")
    def test_capture_state_includes_activity_pct(self, mock_window, watcher):
        """capture_state should include activity_pct when idle detector is available."""
        mock_window.return_value = {"app": "Code", "title": "main.py"}
        result = watcher.capture_state()
        assert result is not None
        if watcher.idle_detector:
            assert "activity_pct" in result
            assert 0.0 <= result["activity_pct"] <= 100.0

    @patch("aw_watcher_enhanced.main.get_current_window")
    def test_capture_state_none_window(self, mock_window, watcher):
        """capture_state should return None when window is None."""
        mock_window.return_value = None
        result = watcher.capture_state()
        assert result is None

    @patch("aw_watcher_enhanced.main.get_current_window")
    def test_capture_state_meeting_detection(self, mock_window, watcher):
        """capture_state should include meeting fields when enabled."""
        mock_window.return_value = {"app": "zoom.us", "title": "Zoom Meeting"}
        result = watcher.capture_state()
        assert result is not None
        if watcher.enable_meeting:
            assert "in_meeting" in result
            assert result["in_meeting"] is True
            assert result["meeting_app"] == "Zoom"
