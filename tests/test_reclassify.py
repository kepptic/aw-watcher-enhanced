"""
Tests for retroactive reclassification.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from aw_watcher_enhanced.reclassify import Reclassifier


class TestReclassifier:
    """Tests for Reclassifier class."""

    @pytest.fixture
    def mock_client(self):
        with patch("aw_watcher_enhanced.reclassify.ActivityWatchClient") as mock:
            client = MagicMock()
            mock.return_value = client
            client.client_hostname = "testhost"
            yield client

    def test_no_events(self, mock_client):
        """Test reclassify with no events in range."""
        mock_client.get_events.return_value = []
        reclassifier = Reclassifier(testing=True)
        changes = reclassifier.reclassify(
            start=datetime(2026, 3, 1, tzinfo=timezone.utc),
            end=datetime(2026, 3, 2, tzinfo=timezone.utc),
            dry_run=True,
        )
        assert changes == []

    def test_no_changes_needed(self, mock_client):
        """Test when all events already match current rules."""
        event = MagicMock()
        event.id = 1
        event.timestamp = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
        event.data = {
            "app": "Code.exe",
            "title": "main.py",
            "category": "Work/Development/Coding",
        }
        mock_client.get_events.return_value = [event]

        reclassifier = Reclassifier(testing=True)
        changes = reclassifier.reclassify(
            start=datetime(2026, 3, 1, tzinfo=timezone.utc),
            end=datetime(2026, 3, 2, tzinfo=timezone.utc),
            dry_run=True,
        )
        assert len(changes) == 0

    def test_detects_change(self, mock_client):
        """Test that category changes are detected."""
        event = MagicMock()
        event.id = 1
        event.timestamp = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
        event.data = {
            "app": "Code.exe",
            "title": "main.py",
            "category": "Wrong/Category",
        }
        mock_client.get_events.return_value = [event]

        reclassifier = Reclassifier(testing=True)
        changes = reclassifier.reclassify(
            start=datetime(2026, 3, 1, tzinfo=timezone.utc),
            end=datetime(2026, 3, 2, tzinfo=timezone.utc),
            dry_run=True,
        )
        assert len(changes) == 1
        assert changes[0]["old_category"] == "Wrong/Category"
        assert changes[0]["new_category"] == "Work/Development/Coding"

    def test_dry_run_no_mutations(self, mock_client):
        """Test that dry run doesn't modify events."""
        event = MagicMock()
        event.id = 1
        event.timestamp = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
        event.data = {"app": "Code.exe", "title": "main.py", "category": "Wrong"}
        mock_client.get_events.return_value = [event]

        reclassifier = Reclassifier(testing=True)
        reclassifier.reclassify(
            start=datetime(2026, 3, 1, tzinfo=timezone.utc),
            end=datetime(2026, 3, 2, tzinfo=timezone.utc),
            dry_run=True,
        )
        # In dry_run mode, should NOT call delete_event or insert_event
        mock_client.delete_event.assert_not_called()
        mock_client.insert_event.assert_not_called()

    def test_live_mode_updates_events(self, mock_client):
        """Test that live mode actually updates events."""
        event = MagicMock()
        event.id = 1
        event.timestamp = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
        event.data = {"app": "Code.exe", "title": "main.py", "category": "Wrong"}
        mock_client.get_events.return_value = [event]

        reclassifier = Reclassifier(testing=True)
        reclassifier.reclassify(
            start=datetime(2026, 3, 1, tzinfo=timezone.utc),
            end=datetime(2026, 3, 2, tzinfo=timezone.utc),
            dry_run=False,
        )
        mock_client.delete_event.assert_called_once()
        mock_client.insert_event.assert_called_once()

    def test_change_details_complete(self, mock_client):
        """Test that change records have all required fields."""
        event = MagicMock()
        event.id = 42
        event.timestamp = datetime(2026, 3, 1, 14, 30, tzinfo=timezone.utc)
        event.data = {"app": "Code.exe", "title": "utils.py", "category": "Old"}
        mock_client.get_events.return_value = [event]

        reclassifier = Reclassifier(testing=True)
        changes = reclassifier.reclassify(
            start=datetime(2026, 3, 1, tzinfo=timezone.utc),
            end=datetime(2026, 3, 2, tzinfo=timezone.utc),
            dry_run=True,
        )
        assert len(changes) == 1
        change = changes[0]
        assert "event_id" in change
        assert "timestamp" in change
        assert "app" in change
        assert "old_category" in change
        assert "new_category" in change
