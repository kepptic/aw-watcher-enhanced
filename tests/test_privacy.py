"""
Tests for privacy filtering.
"""

import pytest

from aw_watcher_enhanced.privacy import (
    _filter_keywords,
    apply_privacy_filters,
    is_sensitive_app,
    redact_pii,
)


class TestApplyPrivacyFilters:
    """Tests for apply_privacy_filters function."""

    def test_exclude_password_manager(self):
        """Test that password managers are excluded."""
        data = {"app": "1Password.exe", "title": "Vault"}
        config = {"exclude_apps": ["1Password.exe"]}
        result = apply_privacy_filters(data, config)
        assert result is None

    def test_exclude_keepass(self):
        """Test that KeePass is excluded."""
        data = {"app": "KeePass.exe", "title": "Database"}
        config = {"exclude_apps": ["KeePass.exe"]}
        result = apply_privacy_filters(data, config)
        assert result is None

    def test_exclude_partial_match(self):
        """Test partial app name matching."""
        data = {"app": "bitwarden.exe", "title": "Vault"}
        config = {"exclude_apps": ["Bitwarden"]}
        result = apply_privacy_filters(data, config)
        assert result is None

    def test_exclude_title_pattern(self):
        """Test title pattern exclusion."""
        data = {"app": "chrome.exe", "title": "Reset Password - Example.com"}
        config = {"exclude_titles": [r".*password.*"]}
        result = apply_privacy_filters(data, config)
        assert result is not None
        assert result["title"] == "[REDACTED]"

    def test_exclude_private_title(self):
        """Test private title exclusion."""
        data = {"app": "notepad.exe", "title": "private_notes.txt"}
        config = {"exclude_titles": [r".*private.*"]}
        result = apply_privacy_filters(data, config)
        assert result is not None
        assert result["title"] == "[REDACTED]"

    def test_exclude_url_pattern(self):
        """Test URL pattern exclusion."""
        data = {
            "app": "chrome.exe",
            "title": "Online Banking",
            "url": "https://mybank.com/account",
            "domain": "mybank.com",
        }
        config = {"exclude_urls": [r".*bank.*"]}
        result = apply_privacy_filters(data, config)
        assert result is not None
        assert result["url"] == "[REDACTED]"
        assert result["domain"] == "[REDACTED]"

    def test_allow_normal_app(self):
        """Test that normal apps pass through."""
        data = {"app": "chrome.exe", "title": "GitHub"}
        config = {"exclude_apps": ["1Password.exe"]}
        result = apply_privacy_filters(data, config)
        assert result is not None
        assert result["app"] == "chrome.exe"
        assert result["title"] == "GitHub"

    def test_filter_ocr_keywords(self):
        """Test OCR keyword filtering."""
        data = {
            "app": "chrome.exe",
            "title": "Page",
            "ocr_keywords": ["password", "login", "username", "submit"],
        }
        config = {"redact_patterns": [r"password", r"username"]}
        result = apply_privacy_filters(data, config)
        assert result is not None
        assert "password" not in result["ocr_keywords"]
        assert "username" not in result["ocr_keywords"]
        assert "login" in result["ocr_keywords"]
        assert "submit" in result["ocr_keywords"]

    def test_redact_emails_in_entities(self):
        """Test email redaction in OCR entities."""
        data = {
            "app": "chrome.exe",
            "title": "Page",
            "ocr_entities": {"emails": ["user@example.com"], "dates": ["2024-01-15"]},
        }
        config = {"redact_emails": True}
        result = apply_privacy_filters(data, config)
        assert result is not None
        assert "emails" not in result["ocr_entities"]
        assert "dates" in result["ocr_entities"]

    def test_redact_phones_in_entities(self):
        """Test phone redaction in OCR entities."""
        data = {
            "app": "chrome.exe",
            "title": "Page",
            "ocr_entities": {"phones": ["555-123-4567"], "urls": ["https://example.com"]},
        }
        config = {"redact_phones": True}
        result = apply_privacy_filters(data, config)
        assert result is not None
        assert "phones" not in result["ocr_entities"]
        assert "urls" in result["ocr_entities"]

    def test_empty_data(self):
        """Test with empty data."""
        result = apply_privacy_filters({}, {})
        assert result is None

    def test_none_data(self):
        """Test with None data."""
        result = apply_privacy_filters(None, {})
        assert result is None

    def test_invalid_regex_pattern(self):
        """Test with invalid regex pattern (should not crash)."""
        data = {"app": "chrome.exe", "title": "Test"}
        config = {"exclude_titles": [r"[invalid"]}  # Invalid regex
        result = apply_privacy_filters(data, config)
        assert result is not None  # Should pass through despite invalid pattern

    def test_case_insensitive_matching(self):
        """Test case insensitive pattern matching."""
        data = {"app": "chrome.exe", "title": "My PASSWORD Reset"}
        config = {"exclude_titles": [r".*password.*"]}
        result = apply_privacy_filters(data, config)
        assert result is not None
        assert result["title"] == "[REDACTED]"


class TestRedactPii:
    """Tests for redact_pii function."""

    def test_redact_email(self):
        """Test email address redaction."""
        text = "Contact john.doe@example.com for more info."
        result = redact_pii(text)
        assert "[EMAIL]" in result
        assert "john.doe@example.com" not in result

    def test_redact_multiple_emails(self):
        """Test multiple email redaction."""
        text = "Email alice@test.com or bob@example.org"
        result = redact_pii(text)
        assert result.count("[EMAIL]") == 2

    def test_redact_phone_number(self):
        """Test phone number redaction."""
        text = "Call me at 555-123-4567"
        result = redact_pii(text)
        assert "[PHONE]" in result
        assert "555-123-4567" not in result

    def test_redact_phone_with_country_code(self):
        """Test phone with country code redaction."""
        text = "Call +1-555-123-4567"
        result = redact_pii(text)
        assert "[PHONE]" in result

    def test_redact_phone_with_dots(self):
        """Test phone with dots redaction."""
        text = "Phone: 555.123.4567"
        result = redact_pii(text)
        assert "[PHONE]" in result

    def test_redact_ssn(self):
        """Test SSN redaction."""
        text = "SSN: 123-45-6789"
        result = redact_pii(text)
        assert "[SSN]" in result
        assert "123-45-6789" not in result

    def test_redact_credit_card(self):
        """Test credit card number redaction."""
        text = "Card: 4111-1111-1111-1111"
        result = redact_pii(text)
        assert "[CREDIT_CARD]" in result
        assert "4111-1111-1111-1111" not in result

    def test_redact_credit_card_spaces(self):
        """Test credit card with spaces redaction."""
        text = "Card: 4111 1111 1111 1111"
        result = redact_pii(text)
        assert "[CREDIT_CARD]" in result

    def test_preserve_normal_text(self):
        """Test that normal text is preserved."""
        text = "This is a normal sentence without PII."
        result = redact_pii(text)
        assert result == text

    def test_redact_mixed_pii(self):
        """Test redaction of mixed PII types."""
        text = "Contact: john@example.com, 555-123-4567, SSN: 123-45-6789"
        result = redact_pii(text)
        assert "[EMAIL]" in result
        assert "[PHONE]" in result
        assert "[SSN]" in result


class TestIsSensitiveApp:
    """Tests for is_sensitive_app function."""

    def test_1password(self):
        """Test 1Password detection."""
        assert is_sensitive_app("1Password.exe") is True
        assert is_sensitive_app("1password") is True

    def test_keepass(self):
        """Test KeePass detection."""
        assert is_sensitive_app("KeePass.exe") is True
        assert is_sensitive_app("keepassxc") is True

    def test_lastpass(self):
        """Test LastPass detection."""
        assert is_sensitive_app("LastPass.exe") is True
        assert is_sensitive_app("lastpass") is True

    def test_bitwarden(self):
        """Test Bitwarden detection."""
        assert is_sensitive_app("Bitwarden.exe") is True
        assert is_sensitive_app("bitwarden") is True

    def test_dashlane(self):
        """Test Dashlane detection."""
        assert is_sensitive_app("Dashlane.exe") is True

    def test_enpass(self):
        """Test Enpass detection."""
        assert is_sensitive_app("Enpass.exe") is True

    def test_roboform(self):
        """Test RoboForm detection."""
        assert is_sensitive_app("RoboForm.exe") is True

    def test_normal_app(self):
        """Test that normal apps return False."""
        assert is_sensitive_app("chrome.exe") is False
        assert is_sensitive_app("Code.exe") is False
        assert is_sensitive_app("notepad.exe") is False


class TestFilterKeywords:
    """Tests for _filter_keywords function."""

    def test_filter_matching_keywords(self):
        """Test filtering keywords that match patterns."""
        keywords = ["password", "username", "login", "submit"]
        patterns = [r"password", r"username"]
        result = _filter_keywords(keywords, patterns)
        assert "password" not in result
        assert "username" not in result
        assert "login" in result
        assert "submit" in result

    def test_no_patterns(self):
        """Test with no patterns returns all keywords."""
        keywords = ["one", "two", "three"]
        result = _filter_keywords(keywords, [])
        assert result == keywords

    def test_empty_keywords(self):
        """Test with empty keywords list."""
        result = _filter_keywords([], [r"pattern"])
        assert result == []

    def test_case_insensitive_filtering(self):
        """Test case insensitive keyword filtering."""
        keywords = ["PASSWORD", "Username", "login"]
        patterns = [r"password", r"username"]
        result = _filter_keywords(keywords, patterns)
        assert "PASSWORD" not in result
        assert "Username" not in result
        assert "login" in result

    def test_invalid_pattern_ignored(self):
        """Test that invalid patterns don't crash."""
        keywords = ["one", "two"]
        patterns = [r"[invalid", r"one"]  # First is invalid regex
        result = _filter_keywords(keywords, patterns)
        assert "one" not in result
        assert "two" in result
