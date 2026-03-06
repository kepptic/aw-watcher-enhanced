"""
Document context extraction from window titles.

Parses window titles to extract:
- Filename and path
- Project/repository names
- Document types
- Git information (for IDEs)
"""

import logging
import os
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Patterns for extracting document info from window titles
# Format: app_pattern -> {title_regex, field_mappings}
TITLE_PATTERNS: Dict[str, Dict[str, Any]] = {
    # Visual Studio Code / VS Code / Cursor
    r"Code\.exe|code|Code|Visual Studio Code|Cursor": {
        "patterns": [
            # "filename.py - project-name - Visual Studio Code" (Windows/Linux)
            r"^(?P<file>.+?)\s+[-–—]\s+(?P<project>.+?)\s+[-–—]\s+Visual Studio Code$",
            # "filename.py - Visual Studio Code" (Windows/Linux, no project)
            r"^(?P<file>.+?)\s+[-–—]\s+Visual Studio Code$",
            # "filename.py — project-name" (macOS, no app suffix, em dash)
            r"^(?P<file>.+?)\s+[-–—]\s+(?P<project>[^-–—]+)$",
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
            r"^(?P<file>.+?)\s+[-–—]\s+Word$",
            r"^(?P<file>.+?)\s+[-–—]\s+Microsoft Word$",
            r"^Document\d*\s+[-–—]",  # Unsaved document
        ],
        "type": "document",
    },
    # Microsoft Excel
    r"EXCEL\.EXE|Microsoft Excel": {
        "patterns": [
            r"^(?P<file>.+?)\s+[-–—]\s+Excel$",
            r"^(?P<file>.+?)\s+[-–—]\s+Microsoft Excel$",
        ],
        "type": "spreadsheet",
    },
    # Microsoft PowerPoint
    r"POWERPNT\.EXE|Microsoft PowerPoint": {
        "patterns": [
            r"^(?P<file>.+?)\s+[-–—]\s+PowerPoint$",
        ],
        "type": "presentation",
    },
    # Notepad++
    r"notepad\+\+": {
        "patterns": [
            r"^(?P<file>.+?)\s+[-–—]\s+Notepad\+\+$",
            r"^\*?(?P<file>.+?)\s+[-–—]\s+Notepad\+\+$",  # Unsaved (*)
        ],
        "type": "text",
    },
    # Sublime Text
    r"sublime_text|Sublime Text": {
        "patterns": [
            r"^(?P<file>.+?)\s+[-–•]\s+(?P<project>.+?)\s+[-–—]\s+Sublime Text$",
            r"^(?P<file>.+?)\s+[-–—]\s+Sublime Text$",
        ],
        "type": "code",
    },
    # Vim/Neovim
    r"vim|nvim|gvim": {
        "patterns": [
            r"^(?P<file>.+?)\s+[-–—]\s+N?VIM$",
            r"^(?P<file>.+?)$",  # Often just the filename
        ],
        "type": "code",
    },
    # Adobe Acrobat/Reader
    r"Acrobat|AcroRd32": {
        "patterns": [
            r"^(?P<file>.+?)\s+[-–—]\s+Adobe",
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
    # Terminal / Command Prompt / Shell
    r"cmd\.exe|powershell|WindowsTerminal|Terminal|iTerm|iTerm2|gnome-terminal|konsole|Alacritty|kitty|WezTerm|Warp": {
        "patterns": [
            # user@host: /path/to/project
            r"^(?P<user>.+?)@(?P<host>.+?):\s*(?P<path>.+?)$",
            # /path/to/project — -zsh — 120×34 (iTerm2 format)
            r"^(?P<path>[~/].+?)\s+[-–—]\s+.*(?:zsh|bash|fish|sh)\b",
            # project-name — zsh (iTerm2/Terminal.app with folder name)
            r"^(?P<project>[^-–—]+?)\s+[-–—]\s+.*(?:zsh|bash|fish|sh)\b",
            # Windows path
            r"^(?P<path>[A-Z]:\\.+?)>?$",
            # Just a path (e.g., "~/Documents/code/myproject")
            r"^(?P<path>(?:~|/)[^\s]+)$",
        ],
        "type": "terminal",
    },
    # Browsers (for fallback when no extension)
    r"chrome\.exe|firefox\.exe|msedge\.exe|Safari|Brave": {
        "patterns": [
            # "Page Title - Browser Name"
            r"^(?P<page_title>.+?)\s+[-–—]\s+(?:Google Chrome|Mozilla Firefox|Microsoft Edge|Safari|Brave)$",
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


def get_terminal_cwd(pid: int) -> Optional[str]:
    """Get the current working directory of a terminal process.

    On macOS, uses proc_pidinfo via libproc. On Linux, reads /proc/PID/cwd.
    Returns the CWD path string, or None if unavailable.
    """
    import sys

    if sys.platform == "darwin":
        return _get_cwd_macos(pid)
    elif sys.platform == "linux":
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
            return cwd
        except (OSError, PermissionError):
            return None
    return None


def _get_cwd_macos(pid: int) -> Optional[str]:
    """Get CWD of a process on macOS using proc_pidinfo."""
    try:
        import ctypes
        import ctypes.util

        libproc = ctypes.CDLL(ctypes.util.find_library("proc"))
        if not libproc:
            return None

        # PROC_PIDVNODEPATHINFO = 9
        PROC_PIDVNODEPATHINFO = 9
        # struct vnode_info_path has 2 * (152 + 1024) bytes = 2352
        # but we use a larger buffer for safety
        MAXPATHLEN = 1024
        buf_size = 2 * (152 + MAXPATHLEN)
        buf = ctypes.create_string_buffer(buf_size)

        ret = libproc.proc_pidinfo(pid, PROC_PIDVNODEPATHINFO, 0, buf, buf_size)
        if ret <= 0:
            return None

        # The CWD path starts at offset 152 (after vnode_info struct)
        # struct vnode_info is 152 bytes, then char vip_path[MAXPATHLEN]
        # For vnode_info_path, the current dir info starts at offset (152 + 1024)
        # Actually: struct proc_vnodepathinfo {
        #   struct vnode_info_path pvi_cdir;  // 152 + 1024 bytes
        #   struct vnode_info_path pvi_rdir;  // 152 + 1024 bytes
        # }
        # pvi_cdir.vip_path starts at offset 152
        cwd_path_offset = 152
        cwd_bytes = buf[cwd_path_offset:cwd_path_offset + MAXPATHLEN]
        cwd = cwd_bytes.split(b"\x00")[0].decode("utf-8", errors="replace")

        return cwd if cwd else None
    except Exception:
        return None


def _get_child_shell_pid(parent_pid: int) -> Optional[int]:
    """Find the child shell process of a terminal app (e.g., zsh under iTerm2)."""
    import subprocess

    try:
        # pgrep -P finds direct children of parent_pid
        result = subprocess.run(
            ["pgrep", "-P", str(parent_pid)],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Return the first child PID (usually the shell)
            pids = result.stdout.strip().split("\n")
            for pid_str in pids:
                pid = int(pid_str.strip())
                # Verify it's a shell by checking the process name
                name_result = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "comm="],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                if name_result.returncode == 0:
                    comm = name_result.stdout.strip()
                    if any(sh in comm for sh in ("zsh", "bash", "fish", "sh")):
                        return pid
            # If no shell found, return first child
            return int(pids[0].strip())
    except Exception:
        pass
    return None


def extract_project_from_cwd(cwd: str) -> Optional[str]:
    """Extract project name from a working directory path.

    Returns the most meaningful project directory name from the path.
    """
    if not cwd:
        return None

    # Normalize path
    cwd = cwd.rstrip("/")

    # If it's a home directory, nothing specific
    home = os.path.expanduser("~")
    if cwd == home:
        return None

    # The last component is usually the project name
    project = os.path.basename(cwd)

    # If we're inside a subdirectory (src, lib, etc.), go up
    generic_dirs = {"src", "lib", "app", "bin", "build", "dist", "node_modules", ".git"}
    if project.lower() in generic_dirs:
        parent = os.path.dirname(cwd)
        project = os.path.basename(parent)

    return project if project else None


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


def get_shell_sessions(parent_pid: int) -> list:
    """Find all descendant shell processes of a given parent PID.

    Walks the process tree to find zsh/bash/fish shells running under
    an app (like VS Code's integrated terminal or a standalone terminal).
    Returns a list of {pid, cwd, project} for each shell found.
    """
    import subprocess
    from collections import deque

    try:
        result = subprocess.run(
            ["ps", "-axo", "pid,ppid,comm"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return []

        # Build parent->children map
        children: Dict[int, list] = {}
        procs: Dict[int, tuple] = {}
        for line in result.stdout.strip().split("\n")[1:]:
            parts = line.split()
            if len(parts) >= 3:
                pid = int(parts[0])
                ppid = int(parts[1])
                comm = " ".join(parts[2:])
                procs[pid] = (ppid, comm)
                children.setdefault(ppid, []).append(pid)

        # BFS from parent_pid to find shell descendants
        shell_names = ("/zsh", "/bash", "/fish", "-zsh", "-bash", "-fish")
        queue = deque([parent_pid])
        visited: set = set()
        shells = []

        while queue:
            pid = queue.popleft()
            if pid in visited:
                continue
            visited.add(pid)
            ppid, comm = procs.get(pid, (0, ""))
            if any(sh in comm for sh in shell_names):
                cwd = get_terminal_cwd(pid)
                project = extract_project_from_cwd(cwd) if cwd else None
                entry: Dict[str, Any] = {"pid": pid}
                if cwd:
                    entry["cwd"] = cwd
                if project:
                    entry["project"] = project
                shells.append(entry)
            for child in children.get(pid, []):
                queue.append(child)

        return shells
    except Exception as e:
        logger.debug(f"Error getting shell sessions: {e}")
        return []


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
