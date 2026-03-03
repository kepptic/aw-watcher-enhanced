"""
Tests for meeting detection.
"""

import pytest

from aw_watcher_enhanced.meeting import detect_meeting


class TestDetectMeeting:
    """Tests for detect_meeting function."""

    def test_zoom_app(self):
        in_meeting, app = detect_meeting("zoom.us", "Zoom Meeting")
        assert in_meeting is True
        assert app == "Zoom"

    def test_zoom_alternate_name(self):
        in_meeting, app = detect_meeting("Zoom", "Meeting in progress")
        assert in_meeting is True
        assert app == "Zoom"

    def test_teams_meeting_title(self):
        in_meeting, app = detect_meeting("Microsoft Teams", "Meeting | Team Chat")
        assert in_meeting is True
        assert app == "Microsoft Teams"

    def test_teams_no_meeting(self):
        """Teams without meeting title should still match as meeting app."""
        in_meeting, app = detect_meeting("Microsoft Teams", "General - Team Chat")
        assert in_meeting is True
        assert app == "Microsoft Teams"

    def test_facetime(self):
        in_meeting, app = detect_meeting("FaceTime", "John Doe")
        assert in_meeting is True
        assert app == "FaceTime"

    def test_webex(self):
        in_meeting, app = detect_meeting("Cisco Webex", "Weekly Standup")
        assert in_meeting is True
        assert app == "WebEx"

    def test_google_meet_url(self):
        """Google Meet detected via URL."""
        in_meeting, app = detect_meeting(
            "Google Chrome", "Meeting",
            url="https://meet.google.com/abc-defg-hij",
        )
        assert in_meeting is True
        assert app == "Google Meet"

    def test_google_meet_no_url(self):
        """Chrome without Meet URL is not a meeting."""
        in_meeting, app = detect_meeting(
            "Google Chrome", "GitHub",
            url="https://github.com",
            detect_subprocess=False,
        )
        assert in_meeting is False

    def test_slack_chat_no_meeting(self):
        """Regular Slack chat is not a meeting."""
        in_meeting, app = detect_meeting("Slack", "general - Company")
        assert in_meeting is False

    def test_slack_huddle(self):
        """Slack huddle counts as a meeting."""
        in_meeting, app = detect_meeting("Slack", "Huddle in #general")
        assert in_meeting is True
        assert app == "Slack"

    def test_slack_call(self):
        """Slack with call title is a meeting."""
        in_meeting, app = detect_meeting("Slack", "Call with John")
        assert in_meeting is True
        assert app == "Slack"

    def test_discord_chat_no_meeting(self):
        """Regular Discord chat is not a meeting."""
        in_meeting, app = detect_meeting("Discord", "general - Server")
        assert in_meeting is False

    def test_discord_call(self):
        """Discord with call indicator is a meeting."""
        in_meeting, app = detect_meeting("Discord", "Voice Call - Server")
        assert in_meeting is True
        assert app == "Discord"

    def test_non_meeting_app(self):
        in_meeting, app = detect_meeting("Code", "main.py - project")
        assert in_meeting is False
        assert app == ""

    def test_empty_app(self):
        in_meeting, app = detect_meeting("", "")
        assert in_meeting is False

    def test_skype(self):
        in_meeting, app = detect_meeting("Skype", "Call with Alice")
        assert in_meeting is True
        assert app == "Skype"

    def test_no_subprocess_detection(self):
        """Non-meeting app without subprocess detection."""
        in_meeting, app = detect_meeting(
            "Finder", "Documents",
            detect_subprocess=False,
        )
        assert in_meeting is False
