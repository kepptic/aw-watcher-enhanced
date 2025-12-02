"""
Tests for OCR functionality.

Note: These tests don't require actual OCR engine - they test the text processing functions.
"""

import pytest

from aw_watcher_enhanced.ocr import (
    extract_entities,
    extract_keywords,
)


class TestExtractKeywords:
    """Tests for extract_keywords function."""

    def test_basic_extraction(self):
        """Test basic keyword extraction."""
        text = "The quick brown fox jumps over the lazy dog"
        result = extract_keywords(text)
        assert "quick" in result
        assert "brown" in result
        assert "fox" in result
        assert "jumps" in result
        assert "lazy" in result
        assert "dog" in result

    def test_filters_stop_words(self):
        """Test that stop words are filtered."""
        text = "The quick brown fox jumps over the lazy dog"
        result = extract_keywords(text)
        assert "the" not in result
        assert "over" not in result

    def test_filters_short_words(self):
        """Test that words shorter than 3 chars are filtered."""
        text = "I am a developer at the company"
        result = extract_keywords(text)
        # "I", "am", "a", "at" should be filtered
        assert "developer" in result
        assert "company" in result

    def test_removes_duplicates(self):
        """Test that duplicate keywords are removed."""
        text = "code code coding coding code"
        result = extract_keywords(text)
        assert result.count("code") == 1
        assert result.count("coding") == 1

    def test_respects_max_keywords(self):
        """Test that max_keywords limit is respected."""
        text = " ".join([f"word{i}" for i in range(50)])
        result = extract_keywords(text, max_keywords=10)
        assert len(result) <= 10

    def test_empty_text(self):
        """Test with empty text."""
        result = extract_keywords("")
        assert result == []

    def test_none_text(self):
        """Test with None text."""
        result = extract_keywords(None)
        assert result == []

    def test_extracts_code_keywords(self):
        """Test extraction of programming-related keywords."""
        text = """
        def process_data(input_data):
            results = []
            for item in input_data:
                results.append(transform(item))
            return results
        """
        result = extract_keywords(text)
        assert "process_data" in result or "process" in result
        assert "results" in result
        assert "input_data" in result or "input" in result
        assert "transform" in result

    def test_handles_special_characters(self):
        """Test handling of special characters."""
        text = "user@example.com: Hello! How are you? #hashtag @mention"
        result = extract_keywords(text)
        # Should extract word parts
        assert "hello" in result
        assert "hashtag" in result
        assert "mention" in result

    def test_lowercase_conversion(self):
        """Test that keywords are lowercased."""
        text = "JavaScript TypeScript Python"
        result = extract_keywords(text)
        assert "javascript" in result
        assert "typescript" in result
        assert "python" in result
        assert "JavaScript" not in result


class TestExtractEntities:
    """Tests for extract_entities function."""

    def test_extract_email(self):
        """Test email extraction."""
        text = "Contact me at john.doe@example.com"
        result = extract_entities(text)
        assert "emails" in result
        assert "john.doe@example.com" in result["emails"]

    def test_extract_multiple_emails(self):
        """Test multiple email extraction."""
        text = "Email alice@test.com or bob@example.org"
        result = extract_entities(text)
        assert "emails" in result
        assert len(result["emails"]) == 2

    def test_extract_url(self):
        """Test URL extraction."""
        text = "Visit https://example.com/page for more info"
        result = extract_entities(text)
        assert "urls" in result
        assert "https://example.com/page" in result["urls"]

    def test_extract_multiple_urls(self):
        """Test multiple URL extraction."""
        text = "Check https://example.com and http://test.org"
        result = extract_entities(text)
        assert "urls" in result
        assert len(result["urls"]) == 2

    def test_extract_phone_number(self):
        """Test phone number extraction."""
        text = "Call 555-123-4567 for support"
        result = extract_entities(text)
        assert "phones" in result
        assert "555-123-4567" in result["phones"]

    def test_extract_phone_with_parentheses(self):
        """Test phone with parentheses extraction."""
        text = "Phone: (555) 123-4567"
        result = extract_entities(text)
        assert "phones" in result
        assert len(result["phones"]) == 1

    def test_extract_date_slash_format(self):
        """Test date extraction (slash format)."""
        text = "Meeting on 01/15/2024"
        result = extract_entities(text)
        assert "dates" in result
        assert "01/15/2024" in result["dates"]

    def test_extract_date_iso_format(self):
        """Test date extraction (ISO format)."""
        text = "Updated: 2024-01-15"
        result = extract_entities(text)
        assert "dates" in result
        assert "2024-01-15" in result["dates"]

    def test_extract_date_written_format(self):
        """Test date extraction (written format)."""
        text = "January 15, 2024 meeting notes"
        result = extract_entities(text)
        assert "dates" in result
        assert any("January" in d for d in result["dates"])

    def test_extract_money_dollar(self):
        """Test money extraction (dollar)."""
        text = "Total: $1,234.56"
        result = extract_entities(text)
        assert "amounts" in result
        assert "$1,234.56" in result["amounts"]

    def test_extract_money_usd(self):
        """Test money extraction (USD suffix)."""
        text = "Budget: 50000 USD"
        result = extract_entities(text)
        assert "amounts" in result
        assert any("USD" in a for a in result["amounts"])

    def test_empty_text(self):
        """Test with empty text."""
        result = extract_entities("")
        assert result == {}

    def test_no_entities(self):
        """Test text with no recognizable entities."""
        text = "This is a simple sentence without entities"
        result = extract_entities(text)
        # Should return empty dict or dict with empty lists
        assert not any(result.get(k) for k in ["emails", "urls", "phones", "dates", "amounts"])

    def test_limits_results(self):
        """Test that entity lists are limited."""
        # Create text with many emails
        emails = [f"user{i}@example.com" for i in range(20)]
        text = " ".join(emails)
        result = extract_entities(text)
        assert "emails" in result
        assert len(result["emails"]) <= 5  # Should be limited

    def test_deduplicates_entities(self):
        """Test that duplicate entities are removed."""
        text = "Email john@example.com or john@example.com"
        result = extract_entities(text)
        assert "emails" in result
        assert len(result["emails"]) == 1


class TestOcrIntegration:
    """Integration tests for OCR module."""

    def test_keywords_and_entities_combined(self):
        """Test extracting both keywords and entities from same text."""
        text = """
        Meeting Notes - January 15, 2024
        Attendees: john@example.com, jane@test.org

        Discussion about the new product launch.
        Budget: $50,000
        Timeline: 3 months

        Next meeting: Call 555-123-4567 to confirm.
        Website: https://example.com/project
        """

        keywords = extract_keywords(text)
        entities = extract_entities(text)

        # Check keywords
        assert "meeting" in keywords
        assert "budget" in keywords
        assert "product" in keywords

        # Check entities
        assert "emails" in entities
        assert len(entities["emails"]) == 2
        assert "phones" in entities
        assert "amounts" in entities
        assert "urls" in entities
        assert "dates" in entities

    def test_ocr_like_text_processing(self):
        """Test processing text that looks like OCR output (with noise)."""
        text = """
        File  Edit  View  Help

        Document.docx - Microsoft Word

        Meeting Agenda
        1. Review Q4 results
        2. Plan Q1 initiatives
        3. Budget discussion $100,000

        Contact: support@company.com
        """

        keywords = extract_keywords(text)
        entities = extract_entities(text)

        # Should extract meaningful keywords despite menu items
        assert "meeting" in keywords
        assert "agenda" in keywords
        assert "budget" in keywords

        # Should extract entities
        assert "emails" in entities
        assert "amounts" in entities
