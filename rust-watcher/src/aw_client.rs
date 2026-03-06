//! ActivityWatch HTTP client.
//!
//! Communicates with aw-server via its REST API.
//! Handles bucket creation, heartbeats, and event insertion.

use std::collections::HashMap;
use std::time::Duration;

use chrono::{DateTime, Utc};
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum AwError {
    #[error("HTTP request failed: {0}")]
    Http(#[from] reqwest::Error),
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Event {
    pub timestamp: DateTime<Utc>,
    #[serde(default)]
    pub duration: f64,
    pub data: serde_json::Map<String, serde_json::Value>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Bucket {
    pub id: String,
    #[serde(rename = "type")]
    pub bucket_type: String,
    pub client: String,
    pub hostname: String,
    #[serde(default)]
    pub data: serde_json::Map<String, serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub created: Option<DateTime<Utc>>,
}

pub struct AwClient {
    client: Client,
    base_url: String,
    pub name: String,
    pub hostname: String,
}

impl AwClient {
    pub fn new(name: &str, testing: bool) -> Result<Self, AwError> {
        let port = if testing { 5666 } else { 5600 };
        let base_url = format!("http://127.0.0.1:{}", port);
        let hostname = gethostname::gethostname().to_string_lossy().to_string();

        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .connect_timeout(Duration::from_secs(5))
            .build()?;

        Ok(Self {
            client,
            base_url,
            name: name.to_string(),
            hostname,
        })
    }

    /// Create a bucket, ignoring "already exists" errors.
    pub fn create_bucket(&self, bucket_id: &str, bucket_type: &str) -> Result<(), AwError> {
        let url = format!("{}/api/0/buckets/{}", self.base_url, bucket_id);
        let bucket = Bucket {
            id: bucket_id.to_string(),
            bucket_type: bucket_type.to_string(),
            client: self.name.clone(),
            hostname: self.hostname.clone(),
            data: serde_json::Map::new(),
            created: None,
        };

        let resp = self.client.post(&url).json(&bucket).send()?;
        // 304 = already exists, which is fine
        if resp.status().is_success() || resp.status().as_u16() == 304 {
            Ok(())
        } else {
            // Try to get error text but don't fail on that
            resp.error_for_status()?;
            Ok(())
        }
    }

    /// Send a heartbeat event. The server merges events within `pulsetime` seconds.
    pub fn heartbeat(
        &self,
        bucket_id: &str,
        event: &Event,
        pulsetime: f64,
    ) -> Result<(), AwError> {
        let url = format!(
            "{}/api/0/buckets/{}/heartbeat?pulsetime={}",
            self.base_url, bucket_id, pulsetime
        );
        self.client.post(&url).json(event).send()?.error_for_status()?;
        Ok(())
    }

    /// Get buckets from the server.
    #[allow(dead_code)]
    pub fn get_buckets(&self) -> Result<HashMap<String, serde_json::Value>, AwError> {
        let url = format!("{}/api/0/buckets/", self.base_url);
        let resp = self.client.get(&url).send()?.error_for_status()?;
        Ok(resp.json()?)
    }

    /// Get recent events from a bucket.
    #[allow(dead_code)]
    pub fn get_events(
        &self,
        bucket_id: &str,
        limit: u64,
    ) -> Result<Vec<Event>, AwError> {
        let url = format!(
            "{}/api/0/buckets/{}/events?limit={}",
            self.base_url, bucket_id, limit
        );
        let resp = self.client.get(&url).send()?.error_for_status()?;
        Ok(resp.json()?)
    }

    /// Check if server is reachable.
    pub fn is_alive(&self) -> bool {
        let url = format!("{}/api/0/info", self.base_url);
        self.client.get(&url).send().is_ok()
    }
}
