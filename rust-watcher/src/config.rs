//! Configuration management for aw-watcher-enhanced.
//!
//! Loads config from TOML file with deep-merge over defaults.
//! Platform-specific config directories (macOS, Linux, Windows).

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

/// Top-level configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Config {
    pub watcher: WatcherConfig,
    pub smart_capture: SmartCaptureConfig,
    pub ocr: OcrConfig,
    pub llm: LlmConfig,
    pub browser: BrowserConfig,
    pub meeting: MeetingConfig,
    pub privacy: PrivacyConfig,
    pub categorization: CategorizationConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct WatcherConfig {
    pub heartbeat_interval: f64,
    pub poll_time: f64,
    pub pulsetime: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct SmartCaptureConfig {
    pub idle_threshold: f64,
    pub idle_poll_time: f64,
    pub min_ocr_interval: f64,
    pub active_window_interval: f64,
    pub active_monitor_interval: f64,
    pub full_capture_interval: f64,
    pub ocr_diff: OcrDiffConfig,
    pub remote_desktop_interval: f64,
    pub remote_desktop_apps: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct OcrDiffConfig {
    pub similarity_threshold: f64,
    pub min_change_chars: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct OcrConfig {
    pub enabled: bool,
    pub trigger: String,
    pub periodic_interval: u64,
    pub adaptive_fallback_interval: u64,
    pub engine: String,
    pub extract_mode: String,
    pub max_keywords: usize,
    pub transition_capture: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct LlmConfig {
    pub model: String,
    pub timeout: f64,
    pub enabled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct BrowserConfig {
    pub enabled: bool,
    pub merge_with_window: bool,
    pub bucket_refresh_interval: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct MeetingConfig {
    pub enabled: bool,
    pub detect_subprocess: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct PrivacyConfig {
    pub exclude_apps: Vec<String>,
    pub exclude_titles: Vec<String>,
    pub exclude_urls: Vec<String>,
    pub redact_patterns: Vec<String>,
    pub redact_emails: bool,
    pub redact_phones: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct CategorizationConfig {
    pub enabled: bool,
}

// ─── Defaults ────────────────────────────────────────────────────────────────

impl Default for Config {
    fn default() -> Self {
        Self {
            watcher: WatcherConfig::default(),
            smart_capture: SmartCaptureConfig::default(),
            ocr: OcrConfig::default(),
            llm: LlmConfig::default(),
            browser: BrowserConfig::default(),
            meeting: MeetingConfig::default(),
            privacy: PrivacyConfig::default(),
            categorization: CategorizationConfig::default(),
        }
    }
}

impl Default for WatcherConfig {
    fn default() -> Self {
        Self {
            heartbeat_interval: 1.0,
            poll_time: 5.0,
            pulsetime: 6.0,
        }
    }
}

impl Default for SmartCaptureConfig {
    fn default() -> Self {
        Self {
            idle_threshold: 60.0,
            idle_poll_time: 30.0,
            min_ocr_interval: 5.0,
            active_window_interval: 5.0,
            active_monitor_interval: 30.0,
            full_capture_interval: 120.0,
            ocr_diff: OcrDiffConfig::default(),
            remote_desktop_interval: 10.0,
            remote_desktop_apps: vec![
                "Microsoft Remote Desktop".into(),
                "Windows App".into(),
                "Citrix Viewer".into(),
                "Citrix Workspace".into(),
                "VMware Horizon".into(),
                "Parallels Desktop".into(),
                "TeamViewer".into(),
                "AnyDesk".into(),
                "Chrome Remote Desktop".into(),
                "Royal TSX".into(),
                "Jump Desktop".into(),
                "Screens".into(),
                "VNC Viewer".into(),
                "RealVNC".into(),
            ],
        }
    }
}

impl Default for OcrDiffConfig {
    fn default() -> Self {
        Self {
            similarity_threshold: 0.85,
            min_change_chars: 50,
        }
    }
}

impl Default for OcrConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            trigger: "adaptive".into(),
            periodic_interval: 30,
            adaptive_fallback_interval: 300,
            engine: "auto".into(),
            extract_mode: "keywords".into(),
            max_keywords: 20,
            transition_capture: true,
        }
    }
}

impl Default for LlmConfig {
    fn default() -> Self {
        Self {
            model: "gemma3:4b".into(),
            timeout: 10.0,
            enabled: true,
        }
    }
}

impl Default for BrowserConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            merge_with_window: true,
            bucket_refresh_interval: 300,
        }
    }
}

impl Default for MeetingConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            detect_subprocess: true,
        }
    }
}

impl Default for PrivacyConfig {
    fn default() -> Self {
        Self {
            exclude_apps: vec![
                "1Password.exe".into(),
                "KeePass.exe".into(),
                "LastPass.exe".into(),
                "Bitwarden.exe".into(),
            ],
            exclude_titles: vec![
                r".*[Pp]assword.*".into(),
                r".*[Pp]rivate.*".into(),
                r".*[Ss]ecret.*".into(),
            ],
            exclude_urls: vec![r".*bank.*".into(), r".*paypal.*".into()],
            redact_patterns: vec![],
            redact_emails: false,
            redact_phones: false,
        }
    }
}

impl Default for CategorizationConfig {
    fn default() -> Self {
        Self { enabled: true }
    }
}

// ─── Config loading ──────────────────────────────────────────────────────────

/// Get the platform-specific config directory.
pub fn get_config_dir() -> PathBuf {
    let base = if cfg!(target_os = "macos") {
        dirs::home_dir()
            .map(|h| h.join("Library/Application Support"))
            .unwrap_or_else(|| PathBuf::from("."))
    } else if cfg!(target_os = "windows") {
        dirs::data_local_dir().unwrap_or_else(|| PathBuf::from("."))
    } else {
        dirs::config_dir().unwrap_or_else(|| PathBuf::from("."))
    };

    base.join("activitywatch").join("aw-watcher-enhanced")
}

/// Load configuration from TOML file, falling back to defaults.
pub fn load_config() -> Config {
    let config_dir = get_config_dir();
    let config_file = config_dir.join("config.toml");

    if config_file.exists() {
        match fs::read_to_string(&config_file) {
            Ok(contents) => match toml::from_str::<Config>(&contents) {
                Ok(config) => {
                    log::info!("Loaded config from {}", config_file.display());
                    return config;
                }
                Err(e) => {
                    log::error!("Error parsing config: {e}");
                }
            },
            Err(e) => {
                log::error!("Error reading config file: {e}");
            }
        }
    } else {
        // Create default config file
        let _ = fs::create_dir_all(&config_dir);
        let config = Config::default();
        match toml::to_string_pretty(&config) {
            Ok(contents) => {
                if let Err(e) = fs::write(&config_file, contents) {
                    log::warn!("Could not write default config: {e}");
                } else {
                    log::info!("Created default config at {}", config_file.display());
                }
            }
            Err(e) => {
                log::warn!("Could not serialize default config: {e}");
            }
        }
        return config;
    }

    Config::default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = Config::default();
        assert_eq!(config.watcher.heartbeat_interval, 1.0);
        assert_eq!(config.smart_capture.idle_threshold, 60.0);
        assert!(config.ocr.enabled);
        assert_eq!(config.llm.model, "gemma3:4b");
        assert!(config.privacy.exclude_apps.len() >= 4);
    }

    #[test]
    fn test_config_serialization() {
        let config = Config::default();
        let toml_str = toml::to_string_pretty(&config).unwrap();
        let parsed: Config = toml::from_str(&toml_str).unwrap();
        assert_eq!(parsed.watcher.heartbeat_interval, config.watcher.heartbeat_interval);
        assert_eq!(parsed.ocr.trigger, config.ocr.trigger);
    }

    #[test]
    fn test_partial_config_merge() {
        // Only overriding some fields should keep defaults for the rest
        let partial = r#"
[watcher]
heartbeat_interval = 2.0

[ocr]
enabled = false
"#;
        let config: Config = toml::from_str(partial).unwrap();
        assert_eq!(config.watcher.heartbeat_interval, 2.0);
        assert_eq!(config.watcher.poll_time, 5.0); // default preserved
        assert!(!config.ocr.enabled);
        assert_eq!(config.ocr.trigger, "adaptive"); // default preserved
    }
}
