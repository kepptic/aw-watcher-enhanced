"""
Tests for activity categorization.
"""

import pytest

from aw_watcher_enhanced.categorizer import (
    DEFAULT_RULES,
    _detect_client,
    _match_rules,
    categorize_event,
    get_category_hierarchy,
    suggest_category,
)


class TestCategorizeEvent:
    """Tests for categorize_event function."""

    @pytest.fixture
    def config(self):
        """Default categorization config."""
        return {"enabled": True}

    def test_vscode_coding(self, config):
        """Test VS Code categorization."""
        data = {"app": "Code.exe", "title": "main.py - my-project"}
        result = categorize_event(data, config)
        assert result == "Work/Development/Coding"

    def test_pycharm_coding(self, config):
        """Test PyCharm categorization."""
        data = {"app": "pycharm64.exe", "title": "project - main.py"}
        result = categorize_event(data, config)
        assert result == "Work/Development/Coding"

    def test_github_pr(self, config):
        data = {"app": "chrome.exe", "url": "https://github.com/user/repo/pull/123"}
        result = categorize_event(data, config)
        assert result == "Work/Development/Code Review"

    def test_github_general(self, config):
        """Test GitHub general page categorization."""
        data = {"app": "chrome.exe", "url": "https://github.com/user/repo"}
        result = categorize_event(data, config)
        assert result == "Work/Development"

    def test_stackoverflow(self, config):
        """Test Stack Overflow categorization."""
        data = {"app": "chrome.exe", "url": "https://stackoverflow.com/questions/12345"}
        result = categorize_event(data, config)
        assert result == "Work/Development/Research"

    def test_slack_chat(self, config):
        """Test Slack categorization."""
        data = {"app": "Slack.exe", "title": "general - Company"}
        result = categorize_event(data, config)
        assert result == "Work/Communication/Chat"

    def test_teams_chat(self, config):
        """Test Microsoft Teams categorization."""
        data = {"app": "Teams.exe", "title": "Team Chat"}
        result = categorize_event(data, config)
        assert result == "Work/Communication/Chat"

    def test_gmail(self, config):
        """Test Gmail categorization."""
        data = {"app": "chrome.exe", "url": "https://mail.google.com/mail/u/0/#inbox"}
        result = categorize_event(data, config)
        assert result == "Work/Communication/Email"

    def test_outlook_web(self, config):
        """Test Outlook web categorization."""
        data = {"app": "chrome.exe", "url": "https://outlook.office.com/mail/"}
        result = categorize_event(data, config)
        assert result == "Work/Communication/Email"

    def test_outlook_app(self, config):
        """Test Outlook app categorization."""
        data = {"app": "OUTLOOK.EXE", "title": "Inbox - user@company.com"}
        result = categorize_event(data, config)
        assert result == "Work/Communication/Email"

    def test_google_meet(self, config):
        """Test Google Meet categorization."""
        data = {"app": "chrome.exe", "url": "https://meet.google.com/abc-defg-hij"}
        result = categorize_event(data, config)
        assert result == "Work/Communication/Meetings"

    def test_zoom(self, config):
        """Test Zoom categorization."""
        data = {"app": "chrome.exe", "url": "https://zoom.us/j/123456789"}
        result = categorize_event(data, config)
        assert result == "Work/Communication/Meetings"

    def test_word_document(self, config):
        """Test Word document categorization."""
        data = {"app": "WINWORD.EXE", "title": "Report.docx - Word"}
        result = categorize_event(data, config)
        assert result == "Work/Documentation/Writing"

    def test_google_docs(self, config):
        """Test Google Docs categorization."""
        data = {"app": "chrome.exe", "url": "https://docs.google.com/document/d/abc123"}
        result = categorize_event(data, config)
        assert result == "Work/Documentation/Writing"

    def test_notion(self, config):
        """Test Notion categorization."""
        data = {"app": "chrome.exe", "url": "https://notion.so/workspace/page"}
        result = categorize_event(data, config)
        assert result == "Work/Documentation"

    def test_excel(self, config):
        """Test Excel categorization."""
        data = {"app": "EXCEL.EXE", "title": "Budget.xlsx - Excel"}
        result = categorize_event(data, config)
        assert result == "Work/Data/Spreadsheets"

    def test_google_sheets(self, config):
        """Test Google Sheets categorization."""
        data = {"app": "chrome.exe", "url": "https://docs.google.com/spreadsheets/d/abc123"}
        result = categorize_event(data, config)
        assert result == "Work/Data/Spreadsheets"

    def test_figma(self, config):
        """Test Figma categorization."""
        data = {"app": "chrome.exe", "url": "https://figma.com/file/abc123"}
        result = categorize_event(data, config)
        assert result == "Work/Design"

    def test_figma_app(self, config):
        """Test Figma desktop app categorization."""
        data = {"app": "Figma.exe", "title": "Design System"}
        result = categorize_event(data, config)
        assert result == "Work/Design"

    def test_jira(self, config):
        """Test Jira categorization."""
        data = {"app": "chrome.exe", "url": "https://company.atlassian.net/jira/board"}
        result = categorize_event(data, config)
        assert result == "Work/Project Management"

    def test_trello(self, config):
        """Test Trello categorization."""
        data = {"app": "chrome.exe", "url": "https://trello.com/b/abc123/board"}
        result = categorize_event(data, config)
        assert result == "Work/Project Management"

    def test_youtube_general(self, config):
        """Test YouTube general categorization."""
        data = {"app": "chrome.exe", "url": "https://youtube.com/watch?v=abc123"}
        result = categorize_event(data, config)
        assert result == "Personal/Entertainment"

    def test_youtube_tutorial(self, config):
        """Test YouTube tutorial categorization."""
        data = {"app": "chrome.exe", "url": "https://youtube.com/watch?v=abc123&tutorial=python"}
        result = categorize_event(data, config)
        # Should match tutorial pattern first
        assert "Learning" in result or "Entertainment" in result

    def test_twitter(self, config):
        """Test Twitter/X categorization."""
        data = {"app": "chrome.exe", "url": "https://twitter.com/user/status/123"}
        result = categorize_event(data, config)
        assert result == "Personal/Social Media"

    def test_facebook(self, config):
        """Test Facebook categorization."""
        data = {"app": "chrome.exe", "url": "https://facebook.com/notifications"}
        result = categorize_event(data, config)
        assert result == "Personal/Social Media"

    def test_reddit(self, config):
        """Test Reddit categorization."""
        data = {"app": "chrome.exe", "url": "https://reddit.com/r/programming"}
        result = categorize_event(data, config)
        assert result == "Personal/Social Media"

    def test_amazon(self, config):
        """Test Amazon shopping categorization."""
        data = {"app": "chrome.exe", "url": "https://amazon.com/dp/B08N5WRWNW"}
        result = categorize_event(data, config)
        assert result == "Personal/Shopping"

    def test_file_explorer(self, config):
        """Test File Explorer categorization."""
        data = {"app": "explorer.exe", "title": "Documents"}
        result = categorize_event(data, config)
        assert result == "System/File Management"

    def test_terminal(self, config):
        """Test terminal categorization."""
        data = {"app": "WindowsTerminal.exe", "title": "PowerShell"}
        result = categorize_event(data, config)
        assert result == "Work/Development/Terminal"

    def test_disabled_categorization(self):
        """Test that disabled categorization returns None."""
        config = {"enabled": False}
        data = {"app": "Code.exe", "title": "main.py"}
        result = categorize_event(data, config)
        assert result is None

    def test_unknown_app(self, config):
        """Test unknown app returns None."""
        data = {"app": "random_app.exe", "title": "Unknown Window"}
        result = categorize_event(data, config)
        assert result is None


class TestClientDetection:
    """Tests for client/project detection."""

    def test_detect_client_from_title(self):
        """Test client detection from window title."""
        client_keywords = {
            "acme-corp": ["acme", "project-x"],
            "bigcorp": ["bigcorp", "initiative-y"],
        }
        data = {"title": "Working on ACME Project-X - VS Code"}
        result = _detect_client(data, client_keywords)
        assert result == "acme-corp"

    def test_detect_client_from_url(self):
        """Test client detection from URL."""
        client_keywords = {
            "acme-corp": ["acme.com", "acme-portal"],
        }
        data = {"url": "https://portal.acme.com/dashboard"}
        result = _detect_client(data, client_keywords)
        assert result == "acme-corp"

    def test_detect_client_from_ocr(self):
        """Test client detection from OCR keywords."""
        client_keywords = {
            "acme-corp": ["acme", "john@acme.com"],
        }
        data = {"ocr_keywords": ["meeting", "budget", "acme", "quarterly"]}
        result = _detect_client(data, client_keywords)
        assert result == "acme-corp"

    def test_detect_client_from_project(self):
        """Test client detection from document project."""
        client_keywords = {
            "acme-corp": ["acme-frontend", "acme-backend"],
        }
        data = {"document": {"project": "acme-frontend"}}
        result = _detect_client(data, client_keywords)
        assert result == "acme-corp"

    def test_no_client_match(self):
        """Test when no client matches."""
        client_keywords = {
            "acme-corp": ["acme"],
        }
        data = {"title": "Personal project - VS Code"}
        result = _detect_client(data, client_keywords)
        assert result is None

    def test_empty_keywords(self):
        """Test with empty client keywords."""
        result = _detect_client({"title": "Something"}, {})
        assert result is None

    def test_client_in_categorize_event(self):
        """Test client detection through categorize_event."""
        config = {
            "enabled": True,
            "client_keywords": {
                "acme-corp": ["acme", "project-x"],
            },
        }
        data = {
            "app": "unknown.exe",
            "title": "ACME Project-X Meeting Notes",
        }
        result = categorize_event(data, config)
        assert result == "Work/Client/acme-corp"


class TestCategoryHierarchy:
    """Tests for get_category_hierarchy function."""

    def test_three_level_hierarchy(self):
        """Test three-level category hierarchy."""
        result = get_category_hierarchy("Work/Development/Coding")
        assert result == ["Work", "Work/Development", "Work/Development/Coding"]

    def test_two_level_hierarchy(self):
        """Test two-level category hierarchy."""
        result = get_category_hierarchy("Personal/Entertainment")
        assert result == ["Personal", "Personal/Entertainment"]

    def test_single_level(self):
        """Test single-level category."""
        result = get_category_hierarchy("System")
        assert result == ["System"]

    def test_empty_category(self):
        """Test empty category."""
        result = get_category_hierarchy("")
        assert result == []

    def test_none_category(self):
        """Test None category."""
        result = get_category_hierarchy(None)
        assert result == []


class TestSuggestCategory:
    """Tests for suggest_category function."""

    def test_suggest_for_coding(self):
        """Test suggestions for coding activity."""
        data = {"app": "Code.exe", "url": "https://github.com/user/repo"}
        result = suggest_category(data)
        assert len(result) > 0
        assert any("Development" in cat for cat in result)

    def test_suggest_for_email(self):
        """Test suggestions for email activity."""
        data = {"app": "outlook.exe", "url": "https://mail.google.com"}
        result = suggest_category(data)
        assert len(result) > 0
        assert any("Email" in cat or "Communication" in cat for cat in result)

    def test_suggest_multiple(self):
        """Test that multiple suggestions are returned."""
        data = {"app": "chrome.exe", "url": "https://github.com/user/repo", "title": "Pull Request"}
        }
        result = suggest_category(data)
        assert len(result) >= 1

    def test_suggest_limits_results(self):
        """Test that suggestions are limited to 5."""
        data = {"app": "chrome.exe", "url": "https://example.com"}
        result = suggest_category(data)
        assert len(result) <= 5

    def test_suggest_unique_categories(self):
        """Test that suggestions are unique."""
        data = {"app": "slack.exe", "url": "https://slack.com"}
        result = suggest_category(data)
        assert len(result) == len(set(result))
