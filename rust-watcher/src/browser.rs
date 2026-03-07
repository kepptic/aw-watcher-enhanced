//! Browser data merging for aw-watcher-enhanced.
//!
//! Queries aw-watcher-web buckets to merge URL/domain data into events
//! when the active app is a browser.

use std::time::Instant;

use chrono::Utc;
use log::debug;
use url::Url;

use crate::aw_client::AwClient;

/// Max age (seconds) before a web bucket event is considered stale.
/// The web extension stops heartbeating when the tab hasn't changed,
/// so we use a generous window. The caller only queries when the active
/// app is a browser, so the event is likely still the current tab.
const MAX_WEB_EVENT_AGE: f64 = 120.0;

/// Known browser app names (lowercase).
const BROWSER_APPS: &[&str] = &[
    "google chrome",
    "chrome",
    "firefox",
    "mozilla firefox",
    "safari",
    "microsoft edge",
    "edge",
    "brave browser",
    "brave",
    "arc",
    "opera",
    "opera gx",
    "vivaldi",
    "chromium",
    "orion",
    "zen browser",
    "zen",
];

/// Check if the given app name is a known browser.
pub fn is_browser_app(app: &str) -> bool {
    let lower = app.to_lowercase();
    BROWSER_APPS.contains(&lower.as_str())
}

/// Browser data from aw-watcher-web.
#[derive(Debug, Clone)]
pub struct BrowserData {
    pub url: String,
    pub domain: String,
    pub tab_title: String,
}

/// Merges browser URL data from aw-watcher-web into enhanced events.
pub struct BrowserDataMerger {
    web_buckets: Vec<String>,
    buckets_last_refresh: Instant,
    bucket_refresh_interval: f64,
    last_result: Option<BrowserData>,
    last_result_time: Instant,
    cache_ttl: f64,
}

impl BrowserDataMerger {
    pub fn new(bucket_refresh_interval: f64) -> Self {
        Self {
            web_buckets: Vec::new(),
            buckets_last_refresh: Instant::now() - std::time::Duration::from_secs(999),
            bucket_refresh_interval,
            last_result: None,
            last_result_time: Instant::now() - std::time::Duration::from_secs(999),
            cache_ttl: 2.0,
        }
    }

    fn discover_web_buckets(&mut self, client: &AwClient) -> &[String] {
        let now = Instant::now();
        if now.duration_since(self.buckets_last_refresh).as_secs_f64()
            < self.bucket_refresh_interval
        {
            return &self.web_buckets;
        }

        match client.get_buckets() {
            Ok(buckets) => {
                self.web_buckets = buckets
                    .keys()
                    .filter(|id| id.starts_with("aw-watcher-web"))
                    .cloned()
                    .collect();
                self.buckets_last_refresh = now;
                if !self.web_buckets.is_empty() {
                    debug!("Found web buckets: {:?}", self.web_buckets);
                }
            }
            Err(e) => {
                debug!("Error discovering web buckets: {e}");
            }
        }

        &self.web_buckets
    }

    /// Get the most recent browser URL/title data.
    pub fn get_browser_data(&mut self, client: &AwClient) -> Option<BrowserData> {
        let now = Instant::now();
        if now.duration_since(self.last_result_time).as_secs_f64() < self.cache_ttl {
            return self.last_result.clone();
        }

        let buckets = self.discover_web_buckets(client).to_vec();
        if buckets.is_empty() {
            return None;
        }

        for bucket_id in &buckets {
            match client.get_events(bucket_id, 1) {
                Ok(events) => {
                    if events.is_empty() {
                        continue;
                    }
                    let event = &events[0];

                    // Check freshness — stale web events shouldn't be merged.
                    // Use timestamp + duration as the effective end time, since
                    // the web extension uses pulse merging (duration gets extended).
                    let effective_end = event.timestamp
                        + chrono::Duration::milliseconds((event.duration * 1000.0) as i64);
                    let age = (Utc::now() - effective_end).num_seconds() as f64;
                    if age > MAX_WEB_EVENT_AGE {
                        continue;
                    }

                    let url = event
                        .data
                        .get("url")
                        .and_then(|v| v.as_str())
                        .unwrap_or("");
                    if url.is_empty() {
                        continue;
                    }

                    let domain = Url::parse(url)
                        .ok()
                        .and_then(|u| u.host_str().map(|h| h.to_string()))
                        .unwrap_or_default();

                    let tab_title = event
                        .data
                        .get("title")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string();

                    let result = BrowserData {
                        url: url.to_string(),
                        domain,
                        tab_title,
                    };

                    self.last_result = Some(result.clone());
                    self.last_result_time = now;
                    return Some(result);
                }
                Err(e) => {
                    debug!("Error querying bucket {bucket_id}: {e}");
                }
            }
        }

        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_browser_app() {
        assert!(is_browser_app("Google Chrome"));
        assert!(is_browser_app("Firefox"));
        assert!(is_browser_app("Safari"));
        assert!(is_browser_app("Arc"));
        assert!(is_browser_app("Zen Browser"));
        assert!(!is_browser_app("Code"));
        assert!(!is_browser_app("Slack"));
    }
}
