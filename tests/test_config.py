"""
Tests for configuration management.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from aw_watcher_enhanced.config import (
    DEFAULT_CONFIG,
    deep_merge,
    get_config_dir,
    load_config,
)


class TestDeepMerge:
    """Tests for deep_merge function."""

    def test_simple_merge(self):
        """Test simple dictionary merge."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        """Test nested dictionary merge."""
        base = {"outer": {"inner1": 1, "inner2": 2}}
        override = {"outer": {"inner2": 3, "inner3": 4}}
        result = deep_merge(base, override)
        assert result == {"outer": {"inner1": 1, "inner2": 3, "inner3": 4}}

    def test_deep_nested_merge(self):
        """Test deeply nested merge."""
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"d": 3, "e": 4}}}
        result = deep_merge(base, override)
        assert result == {"a": {"b": {"c": 1, "d": 3, "e": 4}}}

    def test_override_non_dict_with_dict(self):
        """Test overriding non-dict value with dict."""
        base = {"a": 1}
        override = {"a": {"nested": 2}}
        result = deep_merge(base, override)
        assert result == {"a": {"nested": 2}}

    def test_override_dict_with_non_dict(self):
        """Test overriding dict value with non-dict."""
        base = {"a": {"nested": 1}}
        override = {"a": 2}
        result = deep_merge(base, override)
        assert result == {"a": 2}

    def test_empty_base(self):
        """Test merge with empty base."""
        base = {}
        override = {"a": 1}
        result = deep_merge(base, override)
        assert result == {"a": 1}

    def test_empty_override(self):
        """Test merge with empty override."""
        base = {"a": 1}
        override = {}
        result = deep_merge(base, override)
        assert result == {"a": 1}

    def test_preserves_lists(self):
        """Test that lists are replaced, not merged."""
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        result = deep_merge(base, override)
        assert result == {"items": [4, 5]}

    def test_does_not_modify_original(self):
        """Test that original dicts are not modified."""
        base = {"a": 1, "b": {"c": 2}}
        override = {"b": {"c": 3}}
        original_base = {"a": 1, "b": {"c": 2}}
        result = deep_merge(base, override)
        assert base == original_base


class TestDefaultConfig:
    """Tests for default configuration."""

    def test_has_watcher_section(self):
        """Test default config has watcher section."""
        assert "watcher" in DEFAULT_CONFIG
        assert "poll_time" in DEFAULT_CONFIG["watcher"]
        assert "pulsetime" in DEFAULT_CONFIG["watcher"]

    def test_has_ocr_section(self):
        """Test default config has OCR section."""
        assert "ocr" in DEFAULT_CONFIG
        assert "enabled" in DEFAULT_CONFIG["ocr"]
        assert "trigger" in DEFAULT_CONFIG["ocr"]
        assert "engine" in DEFAULT_CONFIG["ocr"]

    def test_has_privacy_section(self):
        """Test default config has privacy section."""
        assert "privacy" in DEFAULT_CONFIG
        assert "exclude_apps" in DEFAULT_CONFIG["privacy"]
        assert "exclude_titles" in DEFAULT_CONFIG["privacy"]

    def test_has_categorization_section(self):
        """Test default config has categorization section."""
        assert "categorization" in DEFAULT_CONFIG
        assert "enabled" in DEFAULT_CONFIG["categorization"]

    def test_default_poll_time(self):
        """Test default poll time value."""
        assert DEFAULT_CONFIG["watcher"]["poll_time"] == 5.0

    def test_default_pulsetime(self):
        """Test default pulsetime value."""
        assert DEFAULT_CONFIG["watcher"]["pulsetime"] == 6.0

    def test_default_ocr_trigger(self):
        """Test default OCR trigger."""
        assert DEFAULT_CONFIG["ocr"]["trigger"] == "window_change"

    def test_default_exclude_apps(self):
        """Test default excluded apps include password managers."""
        exclude_apps = DEFAULT_CONFIG["privacy"]["exclude_apps"]
        assert "1Password.exe" in exclude_apps
        assert "KeePass.exe" in exclude_apps


class TestGetConfigDir:
    """Tests for get_config_dir function."""

    def test_returns_path(self):
        """Test that get_config_dir returns a Path."""
        result = get_config_dir()
        assert isinstance(result, Path)

    def test_path_contains_activitywatch(self):
        """Test that path contains activitywatch directory."""
        result = get_config_dir()
        assert "activitywatch" in str(result)

    def test_path_contains_watcher_name(self):
        """Test that path contains watcher name."""
        result = get_config_dir()
        assert "aw-watcher-enhanced" in str(result)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_returns_dict(self):
        """Test that load_config returns a dict."""
        result = load_config()
        assert isinstance(result, dict)

    def test_has_all_sections(self):
        """Test that loaded config has all required sections."""
        result = load_config()
        assert "watcher" in result
        assert "ocr" in result
        assert "privacy" in result
        assert "categorization" in result

    def test_default_values_present(self):
        """Test that default values are present."""
        result = load_config()
        assert result["watcher"]["poll_time"] == 5.0
        assert result["ocr"]["enabled"] is True
    @patch("aw_watcher_enhanced.config.get_config_dir")
    def test_loads_yaml_config(self, mock_config_dir):
        """Test loading YAML configuration file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir.return_value = Path(tmpdir)

            # Create a config file
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("""
watcher:
  poll_time: 10.0
ocr:
  enabled: false
""")

            try:
                import yaml

                result = load_config()
                assert result["watcher"]["poll_time"] == 10.0
                assert result["ocr"]["enabled"] is False
                # Default values should still be present
                assert "pulsetime" in result["watcher"]
            except ImportError:
                # PyYAML not installed, skip this test
                pytest.skip("PyYAML not installed")

    @patch("aw_watcher_enhanced.config.get_config_dir")
    def test_merges_with_defaults(self, mock_config_dir):
        """Test that user config is merged with defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir.return_value = Path(tmpdir)

            # Create a partial config file
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("""
watcher:
  poll_time: 15.0
""")

            try:
                import yaml

                result = load_config()
                # User value should be used
                assert result["watcher"]["poll_time"] == 15.0
                # Default values should still be present
                assert result["watcher"]["pulsetime"] == 6.0
                assert result["ocr"]["enabled"] is True
            except ImportError:
                pytest.skip("PyYAML not installed")

    @patch("aw_watcher_enhanced.config.get_config_dir")
    def test_handles_missing_config_file(self, mock_config_dir):
        """Test handling of missing config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir.return_value = Path(tmpdir)

            # Don't create config file
            result = load_config()

            # Should return defaults
            assert result["watcher"]["poll_time"] == 5.0

    @patch("aw_watcher_enhanced.config.get_config_dir")
    def test_handles_invalid_yaml(self, mock_config_dir):
        """Test handling of invalid YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir.return_value = Path(tmpdir)

            # Create an invalid config file
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("invalid: yaml: content: [")

            try:
                import yaml

                import yaml
                result = load_config()
                # Should return defaults on error
                assert result["watcher"]["poll_time"] == 5.0
            except ImportError:
                pytest.skip("PyYAML not installed")
