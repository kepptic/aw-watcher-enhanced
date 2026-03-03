"""
Tests for browser data merging.
"""

import pytest

from aw_watcher_enhanced.browser import is_browser_app


class TestIsBrowserApp:
    """Tests for is_browser_app function."""

    def test_chrome(self):
        assert is_browser_app("Google Chrome") is True

    def test_chrome_lowercase(self):
        assert is_browser_app("google chrome") is True

    def test_firefox(self):
        assert is_browser_app("Firefox") is True

    def test_safari(self):
        assert is_browser_app("Safari") is True

    def test_edge(self):
        assert is_browser_app("Microsoft Edge") is True

    def test_brave(self):
        assert is_browser_app("Brave Browser") is True

    def test_arc(self):
        assert is_browser_app("Arc") is True

    def test_vivaldi(self):
        assert is_browser_app("Vivaldi") is True

    def test_opera(self):
        assert is_browser_app("Opera") is True

    def test_chromium(self):
        assert is_browser_app("Chromium") is True

    def test_not_browser_vscode(self):
        assert is_browser_app("Code") is False

    def test_not_browser_terminal(self):
        assert is_browser_app("Terminal") is False

    def test_not_browser_slack(self):
        assert is_browser_app("Slack") is False

    def test_empty(self):
        assert is_browser_app("") is False

    def test_none(self):
        assert is_browser_app(None) is False
