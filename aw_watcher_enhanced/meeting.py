"""
Meeting detection for aw-watcher-enhanced.

Detects active video/audio meetings by checking:
- Known meeting app names and window titles
- Running meeting-related processes
- Browser URLs (Google Meet, etc.)
"""

import logging
import re
import subprocess
import sys
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Meeting app patterns: regex -> platform name
_MEETING_APP_PATTERNS = {
    r"zoom\.us|zoom": "Zoom",
    r"microsoft teams|teams": "Microsoft Teams",
    r"facetime": "FaceTime",
    r"cisco webex|webex": "WebEx",
    r"slack": "Slack",
    r"discord": "Discord",
    r"skype": "Skype",
    r"google meet": "Google Meet",
    r"bluejeans": "BlueJeans",
    r"goto ?meeting|gotomeeting": "GoToMeeting",
    r"ringcentral": "RingCentral",
    r"whereby": "Whereby",
}

# Window title patterns that indicate an active meeting/call
_MEETING_TITLE_PATTERNS = [
    re.compile(r"meeting|call|conference", re.IGNORECASE),
    re.compile(r"screen\s*shar", re.IGNORECASE),
    re.compile(r"zoom\s+meeting", re.IGNORECASE),
    re.compile(r"teams\s+(meeting|call)", re.IGNORECASE),
]

# Google Meet URL pattern
_MEET_URL_PATTERN = re.compile(r"meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}", re.IGNORECASE)

# Process names to check for active meeting subprocess
_MEETING_PROCESSES = {
    "darwin": {
        "CptHost": "Zoom",       # Zoom's meeting process
        "zoom.us": "Zoom",
        "FaceTime": "FaceTime",
        "WebexMTA": "WebEx",
    },
    "win32": {
        "CptHost.exe": "Zoom",
        "Zoom.exe": "Zoom",
    },
}

# Cache for process checks (bounded to prevent unbounded growth)
_process_cache: Dict[str, Tuple[bool, float]] = {}
_PROCESS_CACHE_TTL = 10.0  # seconds
_PROCESS_CACHE_MAX = 50  # max entries before eviction


def _check_process_running(process_name: str) -> bool:
    """Check if a process is running (cached with eviction)."""
    now = time.time()
    cached = _process_cache.get(process_name)
    if cached and now - cached[1] < _PROCESS_CACHE_TTL:
        return cached[0]

    running = False
    try:
        if sys.platform == "darwin":
            result = subprocess.run(
                ["pgrep", "-x", process_name],
                capture_output=True, timeout=2,
            )
            running = result.returncode == 0
        elif sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {process_name}"],
                capture_output=True, text=True, timeout=2,
            )
            running = process_name.lower() in result.stdout.lower()
    except Exception as e:
        logger.debug(f"Process check failed for {process_name}: {e}")

    # Evict expired entries if cache is too large
    if len(_process_cache) >= _PROCESS_CACHE_MAX:
        expired = [k for k, (_, ts) in _process_cache.items() if now - ts >= _PROCESS_CACHE_TTL]
        for k in expired:
            del _process_cache[k]
        # If still too large, drop oldest half
        if len(_process_cache) >= _PROCESS_CACHE_MAX:
            sorted_keys = sorted(_process_cache, key=lambda k: _process_cache[k][1])
            for k in sorted_keys[: len(sorted_keys) // 2]:
                del _process_cache[k]

    _process_cache[process_name] = (running, now)
    return running


def detect_meeting(
    app_name: str,
    title: str = "",
    url: str = "",
    detect_subprocess: bool = True,
) -> Tuple[bool, str]:
    """Detect if the user is currently in a meeting.

    Args:
        app_name: Current active application name.
        title: Current window title.
        url: Current browser URL (from aw-watcher-web).
        detect_subprocess: Whether to check for meeting subprocesses.

    Returns:
        Tuple of (in_meeting: bool, meeting_app: str).
    """
    if not app_name:
        return False, ""

    app_lower = app_name.lower()

    # Check if current app matches a known meeting app
    for pattern, platform in _MEETING_APP_PATTERNS.items():
        if re.search(pattern, app_lower):
            # For some apps, also check title to confirm active meeting
            if platform in ("Slack", "Discord"):
                # Only count as meeting if title suggests call/huddle
                if any(p.search(title) for p in _MEETING_TITLE_PATTERNS):
                    return True, platform
                # Also check for huddle-specific patterns
                if "huddle" in title.lower():
                    return True, platform
                continue
            return True, platform

    # Check browser URL for Google Meet
    if url and _MEET_URL_PATTERN.search(url):
        return True, "Google Meet"

    # Check window title for meeting indicators (Teams, etc.)
    if any(p.search(title) for p in _MEETING_TITLE_PATTERNS):
        # Only flag if the app could plausibly be a meeting app
        if "teams" in app_lower:
            return True, "Microsoft Teams"

    # Check for meeting subprocess (e.g., Zoom's CptHost)
    if detect_subprocess:
        platform_processes = _MEETING_PROCESSES.get(sys.platform, {})
        for proc_name, platform in platform_processes.items():
            if _check_process_running(proc_name):
                return True, platform

    return False, ""


def detect_camera_mic() -> Dict[str, bool]:
    """Detect if camera and/or microphone are currently active.

    Uses process detection (VDCAssistant for camera) on macOS.

    Returns:
        Dict with 'camera_active' and 'mic_active' booleans.
    """
    result = {"camera_active": False, "mic_active": False}

    if sys.platform != "darwin":
        return result

    try:
        # Camera: check for VDCAssistant or AppleCameraAssistant
        cam_result = subprocess.run(
            ["pgrep", "-x", "VDCAssistant"],
            capture_output=True,
            timeout=2,
        )
        if cam_result.returncode != 0:
            cam_result = subprocess.run(
                ["pgrep", "-x", "AppleCameraAssistant"],
                capture_output=True,
                timeout=2,
            )
        result["camera_active"] = cam_result.returncode == 0
    except Exception as e:
        logger.debug(f"Camera detection error: {e}")

    try:
        # Mic: check if any process is using audio input
        mic_result = subprocess.run(
            [
                "bash", "-c",
                "ioreg -l | grep -c '\"IOAudioEngineState\" = 1'",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if mic_result.returncode == 0:
            count = int(mic_result.stdout.strip() or "0")
            result["mic_active"] = count > 0
    except Exception as e:
        logger.debug(f"Mic detection error: {e}")

    return result
