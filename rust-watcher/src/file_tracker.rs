//! File activity tracking for aw-watcher-enhanced.
//!
//! Monitors file system changes in key directories using the `notify` crate.
//! Records recently modified files with timestamps. Uses FSEvents on macOS,
//! inotify on Linux, ReadDirectoryChangesW on Windows.

use std::collections::VecDeque;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use chrono::Utc;
use log::{debug, info};
use notify::{EventKind, RecommendedWatcher, RecursiveMode, Watcher};

/// File extensions we track.
const TRACKED_EXTENSIONS: &[&str] = &[
    // Code
    "py", "js", "ts", "tsx", "jsx", "java", "go", "rs", "rb", "php", "c", "cpp", "h", "cs",
    "swift", "kt", "scala", "r", "sql", "sh", "bash", "zsh",
    // Web
    "html", "css", "scss", "less", "vue", "svelte",
    // Config
    "json", "yaml", "yml", "toml", "ini", "cfg", "env", "xml",
    // Documents
    "md", "txt", "rst", "tex", "csv",
    // Notebooks
    "ipynb",
];

/// Directory names to ignore.
const IGNORE_DIRS: &[&str] = &[
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
];

/// A recorded file change event.
#[derive(Debug, Clone, serde::Serialize)]
pub struct FileEvent {
    pub path: String,
    pub action: &'static str,
    pub timestamp: String,
}

/// Tracks file modifications in watched directories.
pub struct FileActivityTracker {
    recent_files: Arc<Mutex<VecDeque<FileEvent>>>,
    max_events: usize,
    _watcher: Option<RecommendedWatcher>,
}

impl FileActivityTracker {
    pub fn new(max_events: usize) -> Self {
        Self {
            recent_files: Arc::new(Mutex::new(VecDeque::with_capacity(max_events))),
            max_events,
            _watcher: None,
        }
    }

    /// Start watching directories for file changes.
    pub fn start(&mut self, watch_dirs: Option<Vec<PathBuf>>) {
        let dirs = watch_dirs.unwrap_or_else(default_watch_dirs);
        let dirs: Vec<PathBuf> = dirs.into_iter().filter(|d| d.is_dir()).collect();

        if dirs.is_empty() {
            info!("No valid watch directories found");
            return;
        }

        let recent = self.recent_files.clone();
        let max = self.max_events;

        let mut watcher = match notify::recommended_watcher(move |res: Result<notify::Event, _>| {
            if let Ok(event) = res {
                let action = match event.kind {
                    EventKind::Modify(_) => "modified",
                    EventKind::Create(_) => "created",
                    _ => return,
                };

                for path in &event.paths {
                    if should_track(path) {
                        let display = shorten_path(path);
                        let entry = FileEvent {
                            path: display.clone(),
                            action,
                            timestamp: Utc::now().to_rfc3339(),
                        };

                        if let Ok(mut files) = recent.lock() {
                            // Deduplicate: update timestamp if same file
                            if let Some(last) = files.back() {
                                if last.path == display {
                                    files.pop_back();
                                }
                            }
                            if files.len() >= max {
                                files.pop_front();
                            }
                            files.push_back(entry);
                        }
                    }
                }
            }
        }) {
            Ok(w) => w,
            Err(e) => {
                log::warn!("Failed to create file watcher: {e}");
                return;
            }
        };

        for dir in &dirs {
            if let Err(e) = watcher.watch(dir, RecursiveMode::Recursive) {
                debug!("Cannot watch {}: {e}", dir.display());
            } else {
                debug!("Watching directory: {}", dir.display());
            }
        }

        info!("File activity tracker started ({} dirs)", dirs.len());
        self._watcher = Some(watcher);
    }

    /// Get recently modified files (thread-safe), most recent first.
    pub fn get_recent_files(&self, limit: usize) -> Vec<FileEvent> {
        let files = self.recent_files.lock().unwrap();
        files.iter().rev().take(limit).cloned().collect()
    }
}

fn should_track(path: &Path) -> bool {
    // Check extension
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("");
    if !TRACKED_EXTENSIONS.contains(&ext) {
        return false;
    }

    // Check ignored directories
    for component in path.components() {
        if let std::path::Component::Normal(name) = component {
            if let Some(s) = name.to_str() {
                if IGNORE_DIRS.contains(&s) {
                    return false;
                }
            }
        }
    }

    true
}

fn shorten_path(path: &Path) -> String {
    if let Some(home) = dirs::home_dir() {
        if let Ok(relative) = path.strip_prefix(&home) {
            return format!("~/{}", relative.display());
        }
    }
    path.display().to_string()
}

fn default_watch_dirs() -> Vec<PathBuf> {
    let home = match dirs::home_dir() {
        Some(h) => h,
        None => return vec![],
    };
    vec![
        home.join("Documents"),
        home.join("Desktop"),
        home.join("Projects"),
        home.join("Developer"),
        home.join("Code"),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_should_track() {
        assert!(should_track(Path::new("/home/user/project/main.rs")));
        assert!(should_track(Path::new("/home/user/project/app.py")));
        assert!(!should_track(Path::new("/home/user/project/image.png")));
        assert!(!should_track(Path::new(
            "/home/user/project/node_modules/foo.js"
        )));
        assert!(!should_track(Path::new(
            "/home/user/project/.git/objects/abc"
        )));
    }

    #[test]
    fn test_shorten_path() {
        // Should not panic
        let shortened = shorten_path(Path::new("/tmp/test.rs"));
        assert!(!shortened.is_empty());
    }

    #[test]
    fn test_file_tracker_empty() {
        let tracker = FileActivityTracker::new(50);
        let files = tracker.get_recent_files(10);
        assert!(files.is_empty());
    }
}
