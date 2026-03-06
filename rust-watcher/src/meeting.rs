//! Meeting detection for aw-watcher-enhanced.
//!
//! Detects active video/audio meetings by checking:
//! - Known meeting app names and window titles
//! - Running meeting-related processes
//! - Browser URLs (Google Meet, etc.)

use std::collections::HashMap;
use std::process::Command;
use std::sync::LazyLock;
use std::time::Instant;

use regex::Regex;

/// Meeting app patterns: (regex, platform name).
static MEETING_APP_PATTERNS: LazyLock<Vec<(Regex, &'static str)>> = LazyLock::new(|| {
    vec![
        (Regex::new(r"(?i)zoom\.us|zoom").unwrap(), "Zoom"),
        (
            Regex::new(r"(?i)microsoft teams|teams").unwrap(),
            "Microsoft Teams",
        ),
        (Regex::new(r"(?i)facetime").unwrap(), "FaceTime"),
        (Regex::new(r"(?i)cisco webex|webex").unwrap(), "WebEx"),
        (Regex::new(r"(?i)slack").unwrap(), "Slack"),
        (Regex::new(r"(?i)discord").unwrap(), "Discord"),
        (Regex::new(r"(?i)skype").unwrap(), "Skype"),
        (Regex::new(r"(?i)google meet").unwrap(), "Google Meet"),
        (Regex::new(r"(?i)bluejeans").unwrap(), "BlueJeans"),
        (
            Regex::new(r"(?i)goto\s?meeting|gotomeeting").unwrap(),
            "GoToMeeting",
        ),
        (Regex::new(r"(?i)ringcentral").unwrap(), "RingCentral"),
        (Regex::new(r"(?i)whereby").unwrap(), "Whereby"),
    ]
});

/// Title patterns indicating an active meeting/call.
static MEETING_TITLE_PATTERNS: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    vec![
        Regex::new(r"(?i)meeting|call|conference").unwrap(),
        Regex::new(r"(?i)screen\s*shar").unwrap(),
        Regex::new(r"(?i)zoom\s+meeting").unwrap(),
        Regex::new(r"(?i)teams\s+(meeting|call)").unwrap(),
    ]
});

static MEET_URL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}").unwrap()
});

/// macOS meeting processes: process_name -> platform.
#[cfg(target_os = "macos")]
const MEETING_PROCESSES: &[(&str, &str)] = &[
    ("CptHost", "Zoom"),
    ("zoom.us", "Zoom"),
    ("FaceTime", "FaceTime"),
    ("WebexMTA", "WebEx"),
];

#[cfg(target_os = "windows")]
const MEETING_PROCESSES: &[(&str, &str)] = &[("CptHost.exe", "Zoom"), ("Zoom.exe", "Zoom")];

#[cfg(not(any(target_os = "macos", target_os = "windows")))]
const MEETING_PROCESSES: &[(&str, &str)] = &[];

/// Process check cache with TTL and bounded size.
struct ProcessCache {
    entries: HashMap<String, (bool, Instant)>,
    ttl: f64,
    max_entries: usize,
}

impl ProcessCache {
    fn new() -> Self {
        Self {
            entries: HashMap::new(),
            ttl: 10.0,
            max_entries: 50,
        }
    }

    fn check(&mut self, process_name: &str) -> bool {
        let now = Instant::now();

        // Check cache
        if let Some((running, ts)) = self.entries.get(process_name) {
            if now.duration_since(*ts).as_secs_f64() < self.ttl {
                return *running;
            }
        }

        let running = check_process_running(process_name);

        // Evict if over capacity
        if self.entries.len() >= self.max_entries {
            let expired: Vec<String> = self
                .entries
                .iter()
                .filter(|(_, (_, ts))| now.duration_since(*ts).as_secs_f64() >= self.ttl)
                .map(|(k, _)| k.clone())
                .collect();
            for k in expired {
                self.entries.remove(&k);
            }
            if self.entries.len() >= self.max_entries {
                // Drop oldest half
                let mut by_age: Vec<(String, Instant)> = self
                    .entries
                    .iter()
                    .map(|(k, (_, ts))| (k.clone(), *ts))
                    .collect();
                by_age.sort_by_key(|(_, ts)| *ts);
                for (k, _) in by_age.iter().take(by_age.len() / 2) {
                    self.entries.remove(k);
                }
            }
        }

        self.entries
            .insert(process_name.to_string(), (running, now));
        running
    }
}

fn check_process_running(process_name: &str) -> bool {
    #[cfg(target_os = "macos")]
    {
        Command::new("pgrep")
            .args(["-x", process_name])
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
    }
    #[cfg(target_os = "windows")]
    {
        Command::new("tasklist")
            .args(["/FI", &format!("IMAGENAME eq {process_name}")])
            .output()
            .map(|o| {
                String::from_utf8_lossy(&o.stdout)
                    .to_lowercase()
                    .contains(&process_name.to_lowercase())
            })
            .unwrap_or(false)
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        let _ = process_name;
        false
    }
}

/// Meeting detection result.
pub struct MeetingDetector {
    process_cache: ProcessCache,
}

impl MeetingDetector {
    pub fn new() -> Self {
        Self {
            process_cache: ProcessCache::new(),
        }
    }

    /// Detect if the user is currently in a meeting.
    ///
    /// Returns (in_meeting, meeting_platform).
    pub fn detect(
        &mut self,
        app_name: &str,
        title: &str,
        url: &str,
        detect_subprocess: bool,
    ) -> (bool, &'static str) {
        if app_name.is_empty() {
            return (false, "");
        }

        let app_lower = app_name.to_lowercase();

        // Check meeting app patterns
        for (re, platform) in MEETING_APP_PATTERNS.iter() {
            if re.is_match(&app_lower) {
                // Slack/Discord need title confirmation
                if *platform == "Slack" || *platform == "Discord" {
                    if MEETING_TITLE_PATTERNS.iter().any(|p| p.is_match(title))
                        || title.to_lowercase().contains("huddle")
                    {
                        return (true, platform);
                    }
                    continue;
                }
                return (true, platform);
            }
        }

        // Check browser URL for Google Meet
        if !url.is_empty() && MEET_URL_RE.is_match(url) {
            return (true, "Google Meet");
        }

        // Check title for Teams meetings
        if MEETING_TITLE_PATTERNS.iter().any(|p| p.is_match(title)) && app_lower.contains("teams")
        {
            return (true, "Microsoft Teams");
        }

        // Check meeting subprocesses
        if detect_subprocess {
            for &(proc_name, platform) in MEETING_PROCESSES {
                if self.process_cache.check(proc_name) {
                    return (true, platform);
                }
            }
        }

        (false, "")
    }
}

/// Detect if camera and/or microphone are currently active (macOS only).
pub fn detect_camera_mic() -> (bool, bool) {
    #[cfg(target_os = "macos")]
    {
        let camera = Command::new("pgrep")
            .args(["-x", "VDCAssistant"])
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
            || Command::new("pgrep")
                .args(["-x", "AppleCameraAssistant"])
                .output()
                .map(|o| o.status.success())
                .unwrap_or(false);

        let mic = Command::new("bash")
            .args([
                "-c",
                "ioreg -l | grep -c '\"IOAudioEngineState\" = 1'",
            ])
            .output()
            .ok()
            .and_then(|o| {
                String::from_utf8_lossy(&o.stdout)
                    .trim()
                    .parse::<i32>()
                    .ok()
            })
            .map(|count| count > 0)
            .unwrap_or(false);

        (camera, mic)
    }

    #[cfg(not(target_os = "macos"))]
    {
        (false, false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_zoom() {
        let mut detector = MeetingDetector::new();
        let (meeting, platform) = detector.detect("zoom.us", "Zoom Meeting", "", false);
        assert!(meeting);
        assert_eq!(platform, "Zoom");
    }

    #[test]
    fn test_detect_slack_no_meeting() {
        let mut detector = MeetingDetector::new();
        let (meeting, _) = detector.detect("Slack", "general - my-workspace", "", false);
        assert!(!meeting);
    }

    #[test]
    fn test_detect_slack_huddle() {
        let mut detector = MeetingDetector::new();
        let (meeting, platform) = detector.detect("Slack", "Huddle with team", "", false);
        assert!(meeting);
        assert_eq!(platform, "Slack");
    }

    #[test]
    fn test_detect_google_meet_url() {
        let mut detector = MeetingDetector::new();
        let (meeting, platform) =
            detector.detect("Chrome", "Meet", "https://meet.google.com/abc-defg-hij", false);
        assert!(meeting);
        assert_eq!(platform, "Google Meet");
    }

    #[test]
    fn test_no_meeting() {
        let mut detector = MeetingDetector::new();
        let (meeting, _) = detector.detect("Code", "main.rs", "", false);
        assert!(!meeting);
    }
}
