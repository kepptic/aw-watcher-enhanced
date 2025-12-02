"""
Tests for document context extraction.
"""

import pytest

from aw_watcher_enhanced.document import (
    _extract_project_from_path,
    parse_document_context,
)


class TestParseDocumentContext:
    """Tests for parse_document_context function."""

    def test_vscode_with_project(self):
        """Test VS Code title parsing with project name."""
            app="Code.exe", title="main.py - my-project - Visual Studio Code"
        )
        assert result is not None
        assert result["filename"] == "main.py"
        assert result["project"] == "my-project"
        assert result["type"] == "code"

    def test_vscode_without_project(self):
        """Test VS Code title parsing without project name."""
        result = parse_document_context(app="Code.exe", title="script.js - Visual Studio Code")
        assert result is not None
        assert result["filename"] == "script.js"
        assert result["type"] == "code"

    def test_vscode_lowercase(self):
        """Test VS Code with lowercase app name (Linux/macOS)."""
        result = parse_document_context(app="code", title="app.tsx - frontend - Visual Studio Code")
        assert result is not None
        assert result["filename"] == "app.tsx"
        assert result["project"] == "frontend"

    def test_word_document(self):
        """Test Microsoft Word title parsing."""
        result = parse_document_context(app="WINWORD.EXE", title="Proposal.docx - Word")
        assert result is not None
        assert result["filename"] == "Proposal.docx"
        assert result["type"] == "document"
        assert result["extension"] == ".docx"

    def test_excel_spreadsheet(self):
        """Test Microsoft Excel title parsing."""
        result = parse_document_context(app="EXCEL.EXE", title="Budget_2024.xlsx - Excel")
        assert result is not None
        assert result["filename"] == "Budget_2024.xlsx"
        assert result["type"] == "spreadsheet"
        assert result["extension"] == ".xlsx"

    def test_notepad_plus_plus(self):
        """Test Notepad++ title parsing."""
        result = parse_document_context(app="notepad++.exe", title="config.json - Notepad++")
        assert result is not None
        assert result["filename"] == "config.json"
        assert result["type"] == "text"

    def test_notepad_plus_plus_unsaved(self):
        """Test Notepad++ with unsaved file (asterisk)."""
        result = parse_document_context(app="notepad++.exe", title="*new_file.txt - Notepad++")
        assert result is not None
        assert result["filename"] == "new_file.txt"

    def test_sublime_text(self):
        """Test Sublime Text title parsing."""
        result = parse_document_context(
            app="sublime_text.exe", title="index.html - website - Sublime Text"
        )
        assert result is not None
        assert result["filename"] == "index.html"
        assert result["project"] == "website"
        assert result["type"] == "code"

    def test_chrome_browser(self):
        """Test Chrome browser title parsing."""
        result = parse_document_context(
            app="chrome.exe", title="GitHub - ActivityWatch - Google Chrome"
        )
        assert result is not None
        assert result["page_title"] == "GitHub - ActivityWatch"
        assert result["type"] == "browser"

    def test_firefox_browser(self):
        """Test Firefox browser title parsing."""
        result = parse_document_context(app="firefox.exe", title="Stack Overflow - Mozilla Firefox")
        assert result is not None
        assert result["page_title"] == "Stack Overflow"
        assert result["type"] == "browser"

    def test_file_explorer(self):
        """Test Windows File Explorer."""
        result = parse_document_context(app="explorer.exe", title="C:\\Users\\user\\Documents")
        assert result is not None
        assert result["path"] == "C:\\Users\\user\\Documents"
        assert result["type"] == "file_browser"

    def test_terminal_with_path(self):
        """Test terminal with user@host:path format."""
        result = parse_document_context(
            app="WindowsTerminal.exe", title="user@hostname: /home/user/projects"
        )
        assert result is not None
        assert result["type"] == "terminal"

    def test_adobe_acrobat(self):
        """Test Adobe Acrobat PDF title parsing."""
        result = parse_document_context(
            app="Acrobat.exe", title="Manual.pdf - Adobe Acrobat Reader"
        )
        assert result is not None
        assert result["filename"] == "Manual.pdf"
        assert result["type"] == "pdf"

    def test_empty_title(self):
        """Test with empty title."""
        result = parse_document_context(app="Code.exe", title="")
        assert result is None

    def test_empty_app(self):
        """Test with empty app."""
        result = parse_document_context(app="", title="Some Title")
        assert result is None

    def test_unknown_app(self):
        """Test with unknown app."""
        result = parse_document_context(app="unknownapp.exe", title="Some Window Title")
        # Should return None for unrecognized apps
        assert result is None

    def test_file_extension_detection_python(self):
        """Test Python file extension detection."""
        result = parse_document_context(app="Code.exe", title="test_module.py - Visual Studio Code")
        assert result is not None
        assert result["file_type"] == "code"
        assert result["extension"] == ".py"

    def test_file_extension_detection_typescript(self):
        """Test TypeScript file extension detection."""
        result = parse_document_context(app="Code.exe", title="component.tsx - Visual Studio Code")
        assert result is not None
        assert result["file_type"] == "code"
        assert result["extension"] == ".tsx"

    def test_file_extension_detection_markdown(self):
        """Test Markdown file extension detection."""
        result = parse_document_context(app="Code.exe", title="README.md - Visual Studio Code")
        )
        assert result is not None
        assert result["file_type"] == "document"
        assert result["extension"] == ".md"


class TestExtractProjectFromPath:
    """Tests for _extract_project_from_path function."""

    def test_projects_folder(self):
        """Test extraction from Projects folder."""
        result = _extract_project_from_path("/Users/user/Projects/my-app/src/main.py")
        assert result == "my-app"

    def test_code_folder(self):
        """Test extraction from Code folder."""
        result = _extract_project_from_path("C:\\Users\\user\\Code\\website\\index.html")
        assert result == "website"

    def test_repos_folder(self):
        """Test extraction from repos folder."""
        result = _extract_project_from_path("/home/user/repos/backend/app.py")
        assert result == "backend"

    def test_github_folder(self):
        """Test extraction from github folder."""
        result = _extract_project_from_path("/Users/user/github/activitywatch/main.py")
        assert result == "activitywatch"

    def test_src_folder_pattern(self):
        """Test extraction when src folder is present."""
        result = _extract_project_from_path("/opt/project-name/src/module.py")
        assert result == "project-name"

    def test_no_project_pattern(self):
        """Test path without recognizable project pattern."""
        result = _extract_project_from_path("/tmp/file.txt")
        assert result is None

    def test_empty_path(self):
        """Test with empty path."""
        result = _extract_project_from_path("")
        assert result is None
