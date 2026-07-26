#![allow(dead_code)]
//! Privacy filtering for aw-watcher-enhanced.
//!
//! Applies privacy rules to captured event data:
//! - Exclude certain apps entirely
//! - Redact sensitive window titles
//! - Filter URLs
//! - Scrub PII from text (emails, phone numbers, SSN, credit cards)

use log::{debug, warn};
use regex::Regex;
use std::sync::LazyLock;

use crate::config::PrivacyConfig;

/// Sensitive app patterns that should always be excluded.
static SENSITIVE_APPS: &[&str] = &[
    "1password",
    "keepass",
    "lastpass",
    "bitwarden",
    "dashlane",
    "enpass",
    "roboform",
];

// Pre-compiled PII regexes
static EMAIL_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b").unwrap()
});
static PHONE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b").unwrap()
});
static SSN_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b").unwrap()
});
static CREDIT_CARD_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"\b(?:\d{4}[-.\s]?){3}\d{4}\b").unwrap()
});

/// Check if an app should always be treated as sensitive.
pub fn is_sensitive_app(app: &str) -> bool {
    let app_lower = app.to_lowercase();
    SENSITIVE_APPS.iter().any(|p| app_lower.contains(p))
}

/// Apply privacy filters to event data.
///
/// Returns `None` if the event should be excluded entirely.
/// Otherwise returns the (possibly redacted) data map.
pub fn apply_privacy_filters(
    data: &mut serde_json::Map<String, serde_json::Value>,
    config: &PrivacyConfig,
) -> bool {
    let app = data
        .get("app")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_lowercase();
    let title = data
        .get("title")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    // Always exclude sensitive apps
    if is_sensitive_app(&app) {
        debug!("Excluding sensitive app: {app}");
        return false;
    }

    // Check app exclusions
    for excluded in &config.exclude_apps {
        let excluded_lower = excluded.to_lowercase();
        if excluded_lower.contains(&app) || app.contains(&excluded_lower) {
            debug!("Excluding app: {app}");
            return false;
        }
    }

    // Check title exclusions — redact title but keep event
    for pattern in &config.exclude_titles {
        match Regex::new(pattern) {
            Ok(re) => {
                if re.is_match(&title) {
                    debug!("Redacting title matching: {pattern}");
                    data.insert("title".into(), "[REDACTED]".into());
                    for key in [
                        "doc_file",
                        "doc_project",
                        "doc_type",
                        "doc_ext",
                        "ocr_keywords",
                        "ocr_summary",
                        "ocr_client",
                        "ocr_project",
                    ] {
                        data.remove(key);
                    }
                    break;
                }
            }
            Err(e) => {
                warn!("Invalid exclude title pattern '{pattern}': {e}");
            }
        }
    }

    // Check URL exclusions
    if let Some(url) = data.get("url").and_then(|v| v.as_str()).map(|s| s.to_string()) {
        for pattern in &config.exclude_urls {
            match Regex::new(pattern) {
                Ok(re) => {
                    if re.is_match(&url) {
                        debug!("Redacting URL matching: {pattern}");
                        data.insert("url".into(), "[REDACTED]".into());
                        data.insert("domain".into(), "[REDACTED]".into());
                        for key in [
                            "ocr_keywords",
                            "ocr_summary",
                            "ocr_client",
                            "ocr_project",
                        ] {
                            data.remove(key);
                        }
                        break;
                    }
                }
                Err(e) => {
                    warn!("Invalid URL exclude pattern '{pattern}': {e}");
                }
            }
        }
    }

    // Apply redaction patterns to OCR keywords
    if let Some(keywords) = data.get("ocr_keywords").cloned() {
        if let Some(arr) = keywords.as_array() {
            let filtered: Vec<serde_json::Value> = arr
                .iter()
                .filter_map(|kw| {
                    let s = kw.as_str().unwrap_or("");
                    let matches_sensitive_pattern = config.redact_patterns.iter().any(|pat| {
                        Regex::new(pat)
                            .map(|re| re.is_match(s))
                            .unwrap_or(false)
                    });
                    if matches_sensitive_pattern {
                        return None;
                    }
                    let cleaned = if config.redact_emails || config.redact_phones {
                        redact_pii(s)
                    } else {
                        s.to_string()
                    };
                    Some(serde_json::Value::String(cleaned))
                })
                .collect();
            data.insert("ocr_keywords".into(), filtered.into());
        }
    }

    true
}

/// Redact common PII patterns from text.
pub fn redact_pii(text: &str) -> String {
    let mut result = EMAIL_RE.replace_all(text, "[EMAIL]").to_string();
    result = PHONE_RE.replace_all(&result, "[PHONE]").to_string();
    result = SSN_RE.replace_all(&result, "[SSN]").to_string();
    result = CREDIT_CARD_RE.replace_all(&result, "[CREDIT_CARD]").to_string();
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sensitive_apps() {
        assert!(is_sensitive_app("1Password"));
        assert!(is_sensitive_app("KeePass"));
        assert!(is_sensitive_app("bitwarden"));
        assert!(!is_sensitive_app("Code"));
        assert!(!is_sensitive_app("Chrome"));
    }

    #[test]
    fn test_redact_pii() {
        let text = "Contact john@example.com or call 555-123-4567. SSN: 123-45-6789";
        let redacted = redact_pii(text);
        assert!(redacted.contains("[EMAIL]"));
        assert!(redacted.contains("[PHONE]"));
        assert!(redacted.contains("[SSN]"));
        assert!(!redacted.contains("john@example.com"));
        assert!(!redacted.contains("555-123-4567"));
    }

    #[test]
    fn test_redact_credit_card() {
        let text = "Card: 4111-1111-1111-1111";
        let redacted = redact_pii(text);
        assert!(redacted.contains("[CREDIT_CARD]"));
    }

    #[test]
    fn test_apply_filters_exclude_app() {
        let config = PrivacyConfig::default();
        let mut data = serde_json::Map::new();
        data.insert("app".into(), "1Password".into());
        data.insert("title".into(), "vault".into());
        assert!(!apply_privacy_filters(&mut data, &config));
    }

    #[test]
    fn test_apply_filters_redact_title() {
        let config = PrivacyConfig::default();
        let mut data = serde_json::Map::new();
        data.insert("app".into(), "Chrome".into());
        data.insert("title".into(), "My Password Manager".into());
        data.insert("doc_file".into(), "credentials.txt".into());
        data.insert("ocr_keywords".into(), serde_json::json!(["credentials"]));
        assert!(apply_privacy_filters(&mut data, &config));
        assert_eq!(data.get("title").unwrap().as_str().unwrap(), "[REDACTED]");
        assert!(!data.contains_key("doc_file"));
        assert!(!data.contains_key("ocr_keywords"));
    }

    #[test]
    fn test_apply_filters_redact_url_removes_ocr() {
        let config = PrivacyConfig::default();
        let mut data = serde_json::Map::new();
        data.insert("app".into(), "Chrome".into());
        data.insert("title".into(), "Account".into());
        data.insert("url".into(), "https://bank.example/account".into());
        data.insert("domain".into(), "bank.example".into());
        data.insert("ocr_keywords".into(), serde_json::json!(["balance"]));
        assert!(apply_privacy_filters(&mut data, &config));
        assert_eq!(data.get("url").unwrap(), "[REDACTED]");
        assert_eq!(data.get("domain").unwrap(), "[REDACTED]");
        assert!(!data.contains_key("ocr_keywords"));
    }

    #[test]
    fn test_apply_filters_scrubs_ocr_keywords() {
        let mut config = PrivacyConfig::default();
        config.redact_patterns = vec![r"(?i).*token.*".into()];
        config.redact_emails = true;
        let mut data = serde_json::Map::new();
        data.insert("app".into(), "Code".into());
        data.insert("title".into(), "main.rs".into());
        data.insert(
            "ocr_keywords".into(),
            serde_json::json!(["api_token", "dev@example.com", "project"]),
        );
        assert!(apply_privacy_filters(&mut data, &config));
        assert_eq!(
            data.get("ocr_keywords").unwrap(),
            &serde_json::json!(["[EMAIL]", "project"])
        );
    }

    #[test]
    fn test_apply_filters_normal_event() {
        let config = PrivacyConfig::default();
        let mut data = serde_json::Map::new();
        data.insert("app".into(), "Code".into());
        data.insert("title".into(), "main.rs - my-project".into());
        assert!(apply_privacy_filters(&mut data, &config));
        assert_eq!(
            data.get("title").unwrap().as_str().unwrap(),
            "main.rs - my-project"
        );
    }
}
