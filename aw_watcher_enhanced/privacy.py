"""
Privacy filtering for aw-watcher-enhanced.

Applies privacy rules to captured data:
- Exclude certain apps entirely
- Redact sensitive window titles
- Filter OCR content
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def apply_privacy_filters(
    data: Dict[str, Any], privacy_config: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Apply privacy filters to captured event data.

    Args:
        data: Event data dict (app, title, ocr_keywords, etc.)
        privacy_config: Privacy configuration

    Returns:
        Filtered data dict, or None if event should be excluded entirely
    """
    if not data:
        return None

    app = data.get("app", "").lower()
    title = data.get("title", "")

    # Check app exclusions
    exclude_apps = privacy_config.get("exclude_apps", [])
    for excluded in exclude_apps:
        if excluded.lower() in app or app in excluded.lower():
            logger.debug(f"Excluding app: {app}")
            return None

    # Check title exclusions
    exclude_titles = privacy_config.get("exclude_titles", [])
    for pattern in exclude_titles:
        try:
            if re.search(pattern, title, re.IGNORECASE):
                logger.debug(f"Excluding title matching: {pattern}")
                # Option 1: Exclude entirely
                # return None
                # Option 2: Redact title but keep event
                data = data.copy()
                data["title"] = "[REDACTED]"
                break
        except re.error as e:
            logger.warning(f"Invalid exclude pattern '{pattern}': {e}")

    # Check URL exclusions (if URL present)
    url = data.get("url", "")
    if url:
        exclude_urls = privacy_config.get("exclude_urls", [])
        for pattern in exclude_urls:
            try:
                if re.search(pattern, url, re.IGNORECASE):
                    logger.debug(f"Excluding URL matching: {pattern}")
                    data = data.copy()
                    data["url"] = "[REDACTED]"
                    data["domain"] = "[REDACTED]"
                    break
            except re.error as e:
                logger.warning(f"Invalid URL exclude pattern '{pattern}': {e}")

    # Apply redaction patterns to OCR content
    if "ocr_keywords" in data:
        redact_patterns = privacy_config.get("redact_patterns", [])
        data = data.copy()
        data["ocr_keywords"] = _filter_keywords(data["ocr_keywords"], redact_patterns)

    if "ocr_entities" in data:
        # Remove potentially sensitive entities
        data = data.copy()
        entities = data["ocr_entities"].copy()

        # Optionally redact emails, phones, etc.
        if privacy_config.get("redact_emails", False):
            entities.pop("emails", None)
        if privacy_config.get("redact_phones", False):
            entities.pop("phones", None)

        data["ocr_entities"] = entities

    return data


def _filter_keywords(keywords: List[str], redact_patterns: List[str]) -> List[str]:
    """Filter keywords matching redaction patterns."""
    if not redact_patterns:
        return keywords

    filtered = []
    for keyword in keywords:
        exclude = False
        for pattern in redact_patterns:
            try:
                if re.search(pattern, keyword, re.IGNORECASE):
                    exclude = True
                    break
            except re.error:
                pass

        if not exclude:
            filtered.append(keyword)

    return filtered


def redact_pii(text: str) -> str:
    """
    Redact common PII patterns from text.

    Redacts:
    - Email addresses
    - Phone numbers
    - Social Security Numbers
    - Credit card numbers
    """
    # Email addresses
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]", text
    )

    # Phone numbers
    text = re.sub(
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[PHONE]", text
    )

    # SSN
    text = re.sub(r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b", "[SSN]", text)

    # Credit card (basic pattern)
    text = re.sub(r"\b(?:\d{4}[-.\s]?){3}\d{4}\b", "[CREDIT_CARD]", text)

    return text


# Sensitive app patterns that should always be excluded
SENSITIVE_APPS = [
    r"1password",
    r"keepass",
    r"lastpass",
    r"bitwarden",
    r"dashlane",
    r"enpass",
    r"roboform",
]


def is_sensitive_app(app: str) -> bool:
    """Check if an app should always be treated as sensitive."""
    app_lower = app.lower()
    return any(re.search(pattern, app_lower) for pattern in SENSITIVE_APPS)


# Test module
if __name__ == "__main__":
    # Test PII redaction
    test_text = """
    Contact John at john.doe@example.com or call 555-123-4567.
    SSN: 123-45-6789
    Card: 4111-1111-1111-1111
    """
    print("Original:", test_text)
    print("Redacted:", redact_pii(test_text))

    # Test privacy filter
    test_data = {
        "app": "chrome.exe",
        "title": "My Bank Account - Chrome",
        "ocr_keywords": ["balance", "account", "transfer"],
    }
    config = {
        "exclude_apps": ["1Password.exe"],
        "exclude_titles": [r".*bank.*"],
    }
    result = apply_privacy_filters(test_data, config)
    print(f"\nFiltered result: {result}")
