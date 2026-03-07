//! IDE data merger for aw-watcher-enhanced.
//!
//! Reads events from aw-watcher-vscode (or similar IDE watchers) and merges
//! the rich editor context (file, language, branch, project) into events.

use std::time::Instant;

use chrono::Utc;
use log::debug;
use regex::Regex;
use std::sync::LazyLock;

use crate::aw_client::AwClient;

/// Max age (seconds) before an IDE event is considered stale.
/// VS Code watcher events can have duration=0 and sporadic timing,
/// so we use 60s to avoid missing data between heartbeats.
const MAX_EVENT_AGE: f64 = 60.0;

/// IDE bucket patterns to look for.
const IDE_BUCKET_PATTERNS: &[&str] = &[
    "aw-watcher-vscode",
    "aw-watcher-sublime",
    "aw-watcher-jetbrains",
    "aw-watcher-vim",
    "aw-watcher-emacs",
];

static IDE_APP_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"(?i)code|visual\s*studio\s*code|cursor|windsurf|sublime|pycharm|idea|webstorm|phpstorm|rider|goland|clion|android\s*studio|vim|nvim|emacs|atom",
    )
    .unwrap()
});

/// Check if the given app name is an IDE.
pub fn is_ide_app(app: &str) -> bool {
    IDE_APP_RE.is_match(app)
}

/// IDE watcher data merged into events.
#[derive(Debug, Clone)]
pub struct IdeData {
    pub fields: serde_json::Map<String, serde_json::Value>,
}

/// Reads the latest IDE watcher event and provides it for merging.
pub struct IdeDataMerger {
    ide_buckets: Vec<(String, String)>, // (pattern, bucket_id)
    last_scan_time: Instant,
    scan_interval: f64,
    cache: Option<IdeData>,
    cache_time: Instant,
    cache_ttl: f64,
}

impl IdeDataMerger {
    pub fn new() -> Self {
        let past = Instant::now() - std::time::Duration::from_secs(999);
        Self {
            ide_buckets: Vec::new(),
            last_scan_time: past,
            scan_interval: 60.0,
            cache: None,
            cache_time: past,
            cache_ttl: 2.0,
        }
    }

    fn scan_buckets(&mut self, client: &AwClient) {
        let now = Instant::now();
        if now.duration_since(self.last_scan_time).as_secs_f64() < self.scan_interval {
            return;
        }

        self.last_scan_time = now;
        match client.get_buckets() {
            Ok(buckets) => {
                self.ide_buckets.clear();
                for bucket_id in buckets.keys() {
                    for &pattern in IDE_BUCKET_PATTERNS {
                        if bucket_id.contains(pattern) {
                            self.ide_buckets
                                .push((pattern.to_string(), bucket_id.clone()));
                            break;
                        }
                    }
                }
                if !self.ide_buckets.is_empty() {
                    debug!(
                        "Found IDE buckets: {:?}",
                        self.ide_buckets
                            .iter()
                            .map(|(_, id)| id.as_str())
                            .collect::<Vec<_>>()
                    );
                }
            }
            Err(e) => {
                debug!("Error scanning IDE buckets: {e}");
            }
        }
    }

    /// Get the latest IDE watcher event data if recent enough.
    pub fn get_ide_data(&mut self, client: &AwClient, app_name: &str) -> Option<IdeData> {
        if !is_ide_app(app_name) {
            return None;
        }

        let now = Instant::now();
        if now.duration_since(self.cache_time).as_secs_f64() < self.cache_ttl {
            return self.cache.clone();
        }

        self.scan_buckets(client);

        if self.ide_buckets.is_empty() {
            return None;
        }

        for (source, bucket_id) in &self.ide_buckets {
            // Fetch several recent events — multiple VS Code windows share the same
            // bucket, so we need to find the focused one, not just the most recent.
            match client.get_events(bucket_id, 5) {
                Ok(events) => {
                    if events.is_empty() {
                        continue;
                    }

                    // Prefer the most recent focused event; fall back to most recent overall
                    let mut best_event = None;
                    let mut best_focused = None;

                    for event in &events {
                        let age = (Utc::now() - event.timestamp).num_seconds() as f64;
                        if age > MAX_EVENT_AGE {
                            continue;
                        }
                        if best_event.is_none() {
                            best_event = Some(event);
                        }
                        if event.data.get("is_focused").and_then(|v| v.as_bool()) == Some(true) {
                            best_focused = Some(event);
                            break; // Most recent focused event wins
                        }
                    }

                    let event = best_focused.or(best_event);
                    if let Some(event) = event {
                        if let Some(ide_data) = extract_ide_fields(&event.data, source) {
                            self.cache = Some(ide_data.clone());
                            self.cache_time = now;
                            return Some(ide_data);
                        }
                    }
                }
                Err(e) => {
                    debug!("Error reading IDE bucket {bucket_id}: {e}");
                }
            }
        }

        self.cache = None;
        self.cache_time = now;
        None
    }
}

/// Extract and normalize fields from an IDE event.
fn extract_ide_fields(
    data: &serde_json::Map<String, serde_json::Value>,
    source: &str,
) -> Option<IdeData> {
    if data.is_empty() {
        return None;
    }

    let mut fields = serde_json::Map::new();

    // Core fields
    if let Some(file) = data.get("file").and_then(|v| v.as_str()) {
        if file != "unknown" {
            fields.insert("ide_file".into(), file.into());
        }
    }
    if let Some(lang) = data.get("language").and_then(|v| v.as_str()) {
        if lang != "unknown" {
            fields.insert("ide_language".into(), lang.into());
        }
    }
    if let Some(project) = data.get("project").and_then(|v| v.as_str()) {
        if project != "unknown" {
            fields.insert("ide_project".into(), project.into());
            // Also set doc_project with IDE's more accurate name
            fields.insert("doc_project".into(), project.into());
        }
    }
    if let Some(branch) = data.get("branch").and_then(|v| v.as_str()) {
        if branch != "unknown" {
            fields.insert("ide_branch".into(), branch.into());
        }
    }

    // Enhanced fields
    if let Some(v) = data.get("relative_path") {
        fields.insert("ide_relative_path".into(), v.clone());
    }
    if let Some(v) = data.get("cursor_line") {
        fields.insert("ide_cursor_line".into(), v.clone());
    }
    if let Some(v) = data.get("lines_in_file") {
        fields.insert("ide_lines_in_file".into(), v.clone());
    }
    if let Some(v) = data.get("git_dirty_count") {
        fields.insert("ide_git_dirty".into(), v.clone());
    }
    if let Some(v) = data.get("git_remote") {
        fields.insert("ide_git_remote".into(), v.clone());
    }
    if data.get("is_debugging").and_then(|v| v.as_bool()) == Some(true) {
        fields.insert("ide_debugging".into(), true.into());
        if let Some(v) = data.get("debug_type") {
            fields.insert("ide_debug_type".into(), v.clone());
        }
    }
    if let Some(v) = data.get("open_file_count") {
        fields.insert("ide_open_file_count".into(), v.clone());
    }
    if data.get("is_terminal").and_then(|v| v.as_bool()) == Some(true) {
        fields.insert("ide_is_terminal".into(), true.into());
        if let Some(v) = data.get("terminal_name") {
            fields.insert("ide_terminal_name".into(), v.clone());
        }
    }

    // Terminal context from VS Code watcher
    if let Some(label) = data.get("active_terminal_label").and_then(|v| v.as_str()) {
        // Full tab label e.g., "2.1.69 Setsail"
        if !label.is_empty() {
            fields.insert("ide_active_terminal".into(), label.into());
        }
    } else if let Some(term) = data.get("active_terminal").and_then(|v| v.as_str()) {
        if !term.is_empty() && term != "unknown" {
            fields.insert("ide_active_terminal".into(), term.into());
        }
    }
    if let Some(desc) = data.get("terminal_description").and_then(|v| v.as_str()) {
        if !desc.is_empty() {
            fields.insert("ide_terminal_project".into(), desc.into());
        }
    }
    if let Some(names) = data.get("terminal_names").and_then(|v| v.as_str()) {
        if !names.is_empty() {
            fields.insert("ide_terminal_sessions".into(), names.into());
        }
    }
    if let Some(v) = data.get("terminal_count") {
        fields.insert("ide_terminal_count".into(), v.clone());
    }
    if let Some(focused) = data.get("is_focused") {
        fields.insert("ide_focused".into(), focused.clone());
    }

    fields.insert("ide_source".into(), source.into());

    // Need at least one useful field beyond ide_source
    if fields.len() > 1 {
        Some(IdeData { fields })
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_ide_app() {
        assert!(is_ide_app("Code"));
        assert!(is_ide_app("Visual Studio Code"));
        assert!(is_ide_app("Cursor"));
        assert!(is_ide_app("PyCharm"));
        assert!(is_ide_app("vim"));
        assert!(!is_ide_app("Google Chrome"));
        assert!(!is_ide_app("Slack"));
    }

    #[test]
    fn test_extract_ide_fields() {
        let mut data = serde_json::Map::new();
        data.insert("file".into(), "/src/main.rs".into());
        data.insert("language".into(), "rust".into());
        data.insert("project".into(), "my-project".into());
        data.insert("branch".into(), "main".into());

        let result = extract_ide_fields(&data, "aw-watcher-vscode").unwrap();
        assert_eq!(
            result.fields.get("ide_file").unwrap().as_str().unwrap(),
            "/src/main.rs"
        );
        assert_eq!(
            result.fields.get("ide_language").unwrap().as_str().unwrap(),
            "rust"
        );
        assert_eq!(
            result.fields.get("doc_project").unwrap().as_str().unwrap(),
            "my-project"
        );
    }

    #[test]
    fn test_extract_empty_data() {
        let data = serde_json::Map::new();
        assert!(extract_ide_fields(&data, "test").is_none());
    }

    #[test]
    fn test_extract_unknown_values() {
        let mut data = serde_json::Map::new();
        data.insert("file".into(), "unknown".into());
        data.insert("language".into(), "unknown".into());
        // Only ide_source, so should return None
        assert!(extract_ide_fields(&data, "test").is_none());
    }
}
