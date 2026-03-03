"""
Tests for daily summary generation.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from aw_watcher_enhanced.summary import DailySummary, _format_duration


class TestFormatDuration:
    """Tests for _format_duration helper."""

    def test_zero(self):
        assert _format_duration(0) == "0:00"

    def test_one_minute(self):
        assert _format_duration(60) == "0:01"

    def test_one_hour(self):
        assert _format_duration(3600) == "1:00"

    def test_mixed(self):
        assert _format_duration(5400) == "1:30"

    def test_large(self):
        assert _format_duration(36000) == "10:00"

    def test_partial_seconds(self):
        assert _format_duration(90.5) == "0:01"


class TestDailySummary:
    """Tests for DailySummary class."""

    @pytest.fixture
    def mock_client(self):
        with patch("aw_watcher_enhanced.summary.ActivityWatchClient") as mock:
            client = MagicMock()
            mock.return_value = client
            client.client_hostname = "testhost"
            yield client

    def test_empty_day(self, mock_client):
        """Test summary for a day with no events."""
        mock_client.get_events.return_value = []
        summary = DailySummary(testing=True)
        result = summary.generate(datetime(2026, 3, 1, tzinfo=timezone.utc))
        assert result["total_events"] == 0
        assert result["date"] == "2026-03-01"

    def test_single_event(self, mock_client):
        """Test summary with a single event."""
        event = MagicMock()
        event.timestamp = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
        event.duration = timedelta(seconds=300)
        event.data = {"app": "Code", "title": "main.py", "category": "Work/Development/Coding"}
        mock_client.get_events.return_value = [event]

        summary = DailySummary(testing=True)
        result = summary.generate(datetime(2026, 3, 1, tzinfo=timezone.utc))

        assert result["total_events"] == 1
        assert result["total_tracked_seconds"] == 300.0
        assert "Code" in result["time_by_app"]
        assert "Work/Development/Coding" in result["time_by_category"]
        assert result["context_switches"] == 0

    def test_multiple_apps(self, mock_client):
        """Test summary with multiple different apps."""
        events = []
        for i, (app, cat) in enumerate([
            ("Code", "Work/Development/Coding"),
            ("Chrome", "Personal/Entertainment"),
            ("Code", "Work/Development/Coding"),
        ]):
            event = MagicMock()
            event.timestamp = datetime(2026, 3, 1, 9 + i, 0, tzinfo=timezone.utc)
            event.duration = timedelta(seconds=600)
            event.data = {"app": app, "title": f"Title {i}", "category": cat}
            events.append(event)

        mock_client.get_events.return_value = events

        summary = DailySummary(testing=True)
        result = summary.generate(datetime(2026, 3, 1, tzinfo=timezone.utc))

        assert result["total_events"] == 3
        assert result["context_switches"] == 2  # Code->Chrome, Chrome->Code
        assert "Code" in result["time_by_app"]
        assert "Chrome" in result["time_by_app"]

    def test_meeting_time_tracked(self, mock_client):
        """Test that meeting time is aggregated."""
        event = MagicMock()
        event.timestamp = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
        event.duration = timedelta(seconds=1800)
        event.data = {"app": "zoom.us", "in_meeting": True, "category": "Work/Communication"}
        mock_client.get_events.return_value = [event]

        summary = DailySummary(testing=True)
        result = summary.generate(datetime(2026, 3, 1, tzinfo=timezone.utc))

        assert result["meeting_time_seconds"] == 1800.0
        assert result["meeting_time_formatted"] == "0:30"

    def test_first_last_active(self, mock_client):
        """Test first and last active timestamps."""
        events = []
        for hour in [8, 12, 17]:
            event = MagicMock()
            event.timestamp = datetime(2026, 3, 1, hour, 0, tzinfo=timezone.utc)
            event.duration = timedelta(seconds=60)
            event.data = {"app": "Code"}
            events.append(event)
        mock_client.get_events.return_value = events

        summary = DailySummary(testing=True)
        result = summary.generate(datetime(2026, 3, 1, tzinfo=timezone.utc))

        assert "08:00" in result["first_active"]
        assert "17:00" in result["last_active"]

    def test_uncategorized_events(self, mock_client):
        """Test that events without category get 'Uncategorized'."""
        event = MagicMock()
        event.timestamp = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
        event.duration = timedelta(seconds=300)
        event.data = {"app": "unknown_app"}
        mock_client.get_events.return_value = [event]

        summary = DailySummary(testing=True)
        result = summary.generate(datetime(2026, 3, 1, tzinfo=timezone.utc))

        assert "Uncategorized" in result["time_by_category"]
