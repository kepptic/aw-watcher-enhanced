"""
Document context extraction from window titles.

Parses window titles to extract:
- Filename and path
- Project/repository names
- Document types
- Git information (for IDEs)
"""

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Patterns for extracting document info from window titles
# Format: app_pattern -> {title_regex, field_mappings}
TITLE_PATTERNS: Dict[str, Dict[str, Any]] = {
    # Visual Studio Code
    r"Code\.exe|code|Visual Studio Code": {
        "patterns": [
            # "filename.py - project-name - Visual Studio Code"
            r"^(?P<file>.+?)\s+[-–]\s+(?P<project>.+?)\s+[-–]\s+Visual Studio Code$",
            # "filename.py - Visual Studio Code"
            r"^(?P<file>.+?)\s+[-–]\s+Visual Studio Code$",
        ],
        "type": "code",
    },
    # JetBrains IDEs (PyCharm, IntelliJ, etc.)
    r"pycharm|idea|webstorm|phpstorm|rider|goland|clion": {
        "patterns": [
            # "project-name – file.py [path]"
            r"^(?P<project>.+?)\s+[–-]\s+(?P<file>.+?)(?:\s+\[(?P<path>.+?)\])?$",
        ],
        "type": "code",
    },
    # Microsoft Word
    r"WINWORD\.EXE|Microsoft Word": {
        "patterns": [
            r"^(?P<file>.+?)\s+[-–]\s+Word$",
            r"^(?P<file>.+?)\s+[-–]\s+Microsoft Word$",
            r"^Document\d*\s+[-–]",  # Unsaved document
        ],
        "type": "document",
    },
    # Microsoft Excel
    r"EXCEL\.EXE|Microsoft Excel": {
        "patterns": [
            r"^(?P<file>.+?)\s+[-–]\s+Excel$",
            r"^(?P<file>.+?)\s+[-–]\s+Microsoft Excel$",
        ],
        "type": "spreadsheet",
    },
    # Microsoft PowerPoint
    r"POWERPNT\.EXE|Microsoft PowerPoint": {
        "patterns": [
            r"^(?P<file>.+?)\s+[-–]\s+PowerPoint$",
        ],
        "type": "presentation",
    },
    # Notepad++
    r"notepad\+\+": {
        "patterns": [
            r"^(?P<file>.+?)\s+[-–]\s+Notepad\+\+$",
            r"^\*?(?P<file>.+?)\s+[-–]\s+Notepad\+\+$",  # Unsaved (*)
        ],
        "type": "text",
    },
    # Sublime Text
    r"sublime_text|Sublime Text": {
        "patterns": [
            r"^(?P<file>.+?)\s+[-–•]\s+(?P<project>.+?)\s+[-–]\s+Sublime Text$",
            r"^(?P<file>.+?)\s+[-–]\s+Sublime Text$",
        ],
        "type": "code",
    },
    # Vim/Neovim
    r"vim|nvim|gvim": {
        "patterns": [
            r"^(?P<file>.+?)\s+[-–]\s+N?VIM$",
            r"^(?P<file>.+?)$",  # Often just the filename
        ],
        "type": "code",
    },
    # Adobe Acrobat/Reader
    r"Acrobat|AcroRd32": {
        "patterns": [
            r"^(?P<file>.+?)\s+[-–]\s+Adobe",
        ],
        "type": "pdf",
    },
    # File Explorer / Finder
    r"explorer\.exe|Finder": {
        "patterns": [
            r"^(?P<path>.+)$",  # Usually shows the folder path
        ],
        "type": "file_browser",
    },
    # Terminal / Command Prompt
    r"cmd\.exe|powershell|WindowsTerminal|Terminal|iTerm|gnome-terminal|konsole": {
        "patterns": [
            # Various terminal title formats
            r"^(?P<user>.+?)@(?P<host>.+?):\s*(?P<path>.+?)$",  # user@host: /path
            r"^(?P<path>[A-Z]:\\.+?)>?$",  # Windows path
        ],
        "type": "terminal",
    },
    # Browsers (for fallback when no extension)
    r"chrome\.exe|firefox\.exe|msedge\.exe|Safari|Brave": {
        "patterns": [
            # "Page Title - Browser Name"
            r"^(?P<page_title>.+?)\s+[-–]\s+(?:Google Chrome|Mozilla Firefox|Microsoft Edge|Safari|Brave)$",
        ],
        "type": "browser",
    },
}

# Common file extensions to detect document type
FILE_EXTENSIONS = {
    "code": [
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".c",
        ".cpp",
        ".h",
        ".cs",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".swift",
        ".kt",
        ".scala",
        ".r",
        ".m",
    ],
    "document": [".doc", ".docx", ".odt", ".rtf", ".txt", ".md"],
    "spreadsheet": [".xls", ".xlsx", ".csv", ".ods"],
    "presentation": [".ppt", ".pptx", ".odp"],
    "pdf": [".pdf"],
    "image": [".png", ".jpg", ".jpeg", ".gif", ".svg", ".psd", ".ai"],
    "data": [".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg"],
}


def parse_document_context(app: str, title: str) -> Optional[Dict[str, Any]]:
    """
    Extract document context from app name and window title.

    Args:
        app: Application name (e.g., "Code.exe")
        title: Window title

    Returns:
        Dict with document info, or None if not parseable
    """
    if not app or not title:
        return None

    result: Dict[str, Any] = {}

    # Find matching app pattern
    for app_pattern, config in TITLE_PATTERNS.items():
        if re.search(app_pattern, app, re.IGNORECASE):
            # Try each title pattern
            for pattern in config["patterns"]:
                match = re.match(pattern, title, re.IGNORECASE)
                if match:
                    groups = match.groupdict()

                    # Add matched fields
                    if groups.get("file"):
                        result["filename"] = groups["file"].strip()
                    if groups.get("project"):
                        result["project"] = groups["project"].strip()
                    if groups.get("path"):
                        result["path"] = groups["path"].strip()
                    if groups.get("page_title"):
                        result["page_title"] = groups["page_title"].strip()

                    result["type"] = config["type"]
                    break
            break

    # Try to detect file type from extension
    if result.get("filename"):
        filename = result["filename"]
        for file_type, extensions in FILE_EXTENSIONS.items():
            for ext in extensions:
                if filename.lower().endswith(ext):
                    result["file_type"] = file_type
                    result["extension"] = ext
                    break

    # Try to extract project from path if not already set
    if result.get("path") and not result.get("project"):
        project = _extract_project_from_path(result["path"])
        if project:
            result["project"] = project

    return result if result else None


def _extract_project_from_path(path: str) -> Optional[str]:
    """
    Try to extract project name from a file path.

    Looks for common project directory patterns:
    - /Users/user/Projects/project-name/...
    - C:\\Users\\user\\Code\\project-name\\...
    - /home/user/repos/project-name/...
    """
    # Common project root indicators
    project_roots = [
        r"[/\\](?:Projects?|Code|repos?|src|dev|workspace|work)[/\\]([^/\\]+)",
        r"[/\\]github[/\\]([^/\\]+)",
        r"[/\\]([^/\\]+)[/\\](?:src|lib|app)[/\\]",
    ]

    for pattern in project_roots:
        match = re.search(pattern, path, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def extract_git_info(path: str) -> Optional[Dict[str, str]]:
    """
    Extract git repository info from a file path.

    Returns dict with 'repo', 'branch', 'remote' if in a git repo.
    """
    import subprocess
    from pathlib import Path

    try:
        # Find .git directory
        p = Path(path)
        while p.parent != p:
            if (p / ".git").exists():
                break
            p = p.parent
        else:
            return None

        git_dir = p
        result = {}

        # Get repo name
        result["repo"] = git_dir.name

        # Get current branch
        try:
            branch = (
                subprocess.check_output(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=str(git_dir),
                    stderr=subprocess.DEVNULL,
                    timeout=1,
                )
                .decode()
                .strip()
            )
            result["branch"] = branch
        except Exception:
            pass

        # Get remote URL
        try:
            remote = (
                subprocess.check_output(
                    ["git", "remote", "get-url", "origin"],
                    cwd=str(git_dir),
                    stderr=subprocess.DEVNULL,
                    timeout=1,
                )
                .decode()
                .strip()
            )
            result["remote"] = remote
        except Exception:
            pass

        return result

    except Exception:
        return None


# Test the module
if __name__ == "__main__":
    test_cases = [
        ("Code.exe", "main.py - my-project - Visual Studio Code"),
        ("WINWORD.EXE", "Proposal.docx - Word"),
        ("chrome.exe", "GitHub - ActivityWatch - Google Chrome"),
        ("notepad++.exe", "*untitled - Notepad++"),
        ("explorer.exe", "C:\\Users\\user\\Documents"),
    ]

    for app, title in test_cases:
        result = parse_document_context(app, title)
        print(f"\nApp: {app}")
        print(f"Title: {title}")
        print(f"Result: {result}")
