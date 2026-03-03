"""
Tests for window capture module.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from aw_watcher_enhanced.window import get_current_window


class TestGetCurrentWindow:
    """Tests for get_current_window function."""

    def test_returns_dict_or_none(self):
        """Test that get_current_window returns a dict or None."""
        result = get_current_window()
        assert result is None or isinstance(result, dict)

    def test_result_has_app_key(self):
        """Test that result contains 'app' key."""
        result = get_current_window()
        if result is not None:
            assert "app" in result

    def test_result_has_title_key(self):
        """Test that result contains 'title' key."""
        result = get_current_window()
        if result is not None:
            assert "title" in result

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_macos_not_loginwindow(self):
        """Test that macOS doesn't return loginwindow as the active app."""
        result = get_current_window()
        if result is not None:
            # With the AX fix, we should never get loginwindow
            assert result["app"] != "loginwindow"

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
    def test_macos_focused_element_fields(self):
        """Test that macOS returns focused element fields when AX is available."""
        result = get_current_window()
        if result is not None:
            # These fields may or may not be present depending on AX permissions
            # but the keys should be strings if present
            for key in ["focused_element_role", "focused_element_title",
                        "focused_element_description", "focused_element_context"]:
                if key in result:
                    assert isinstance(result[key], str)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
class TestDeepAXQuerying:
    """Tests for deep Accessibility API querying on macOS."""

    def test_walk_ax_parent_chain_import(self):
        """Test that _walk_ax_parent_chain is importable."""
        from aw_watcher_enhanced.window import _walk_ax_parent_chain
        assert callable(_walk_ax_parent_chain)

    def test_get_focused_element_details_import(self):
        """Test that _get_focused_element_details is importable."""
        from aw_watcher_enhanced.window import _get_focused_element_details
        assert callable(_get_focused_element_details)

    def test_get_focused_element_details_returns_dict(self):
        """Test that _get_focused_element_details returns a dict."""
        from aw_watcher_enhanced.window import _get_focused_element_details
        result = _get_focused_element_details()
        assert isinstance(result, dict)

    def test_system_apps_filter(self):
        """Test that _SYSTEM_APPS is defined."""
        from aw_watcher_enhanced.window import _SYSTEM_APPS
        assert "loginwindow" in _SYSTEM_APPS
        assert "SecurityAgent" in _SYSTEM_APPS

    def test_get_focused_app_ax_import(self):
        """Test that _get_focused_app_ax is importable."""
        from aw_watcher_enhanced.window import _get_focused_app_ax
        assert callable(_get_focused_app_ax)
