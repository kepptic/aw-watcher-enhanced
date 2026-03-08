#![allow(dead_code)]
//! LLM integration for OCR text summarization.
//!
//! Calls Ollama's local API to summarize screen OCR text into
//! structured context (keywords, client, project).

use std::time::Duration;

use log::{debug, warn};
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};

use crate::config::LlmConfig;

const TEXT_SUMMARIZE_PROMPT: &str = r#"Extract structured data from this screenshot OCR text.
- keywords: Up to 8 single-word keywords (no phrases)
- client: Client/company name or null
- project: Project name or null
- summary: One short sentence about the activity

OCR text:
"#;

/// JSON schema for Ollama structured output (format parameter).
/// Ensures the model always returns valid, parseable JSON.
const JSON_SCHEMA: &str = r#"{"type":"object","properties":{"keywords":{"type":"array","items":{"type":"string"}},"client":{"type":["string","null"]},"project":{"type":["string","null"]},"summary":{"type":"string"}},"required":["keywords","summary"]}"#;

/// LLM response for OCR summarization.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct LlmSummary {
    #[serde(default)]
    pub keywords: Vec<String>,
    #[serde(default)]
    pub client: Option<String>,
    #[serde(default)]
    pub project: Option<String>,
    #[serde(default)]
    pub summary: Option<String>,
}

/// Ollama API request.
#[derive(Serialize)]
struct OllamaRequest {
    model: String,
    prompt: String,
    stream: bool,
    format: serde_json::Value,
    options: OllamaOptions,
}

#[derive(Serialize)]
struct OllamaOptions {
    temperature: f32,
    num_predict: u32,
}

/// Ollama API response.
#[derive(Deserialize)]
struct OllamaResponse {
    response: String,
}

pub struct LlmClient {
    client: Client,
    config: LlmConfig,
    base_url: String,
}

impl LlmClient {
    pub fn new(config: &LlmConfig) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs_f64(config.timeout))
            .build()
            .unwrap_or_else(|_| Client::new());

        Self {
            client,
            config: config.clone(),
            base_url: "http://localhost:11434".into(),
        }
    }

    /// Check if Ollama is available.
    pub fn is_available(&self) -> bool {
        self.client
            .get(&self.base_url)
            .timeout(Duration::from_secs(2))
            .send()
            .is_ok()
    }

    /// Summarize OCR text using the LLM (without context).
    pub fn summarize_ocr(&self, ocr_text: &str) -> Option<LlmSummary> {
        self.summarize_ocr_with_context(ocr_text, "", "")
    }

    /// Summarize OCR text with app/title context for better accuracy.
    /// The app and title tell the LLM which window is focused.
    pub fn summarize_ocr_with_context(
        &self,
        ocr_text: &str,
        app: &str,
        title: &str,
    ) -> Option<LlmSummary> {
        if !self.config.enabled || ocr_text.trim().is_empty() {
            return None;
        }

        // Truncate long text (find char boundary to avoid panic on multi-byte chars)
        let text = if ocr_text.len() > 2000 {
            let mut end = 2000;
            while !ocr_text.is_char_boundary(end) {
                end -= 1;
            }
            &ocr_text[..end]
        } else {
            ocr_text
        };

        let context = if !app.is_empty() {
            format!("\nActive app: {app}\nWindow title: {title}\n")
        } else {
            String::new()
        };

        let prompt = format!("{TEXT_SUMMARIZE_PROMPT}{context}\"{text}\"");
        let schema: serde_json::Value =
            serde_json::from_str(JSON_SCHEMA).expect("invalid JSON schema");

        let request = OllamaRequest {
            model: self.config.model.clone(),
            prompt,
            stream: false,
            format: schema,
            options: OllamaOptions {
                temperature: 0.0,
                num_predict: 384,
            },
        };

        let url = format!("{}/api/generate", self.base_url);
        match self.client.post(&url).json(&request).send() {
            Ok(resp) => {
                if !resp.status().is_success() {
                    warn!("LLM request failed: {}", resp.status());
                    return None;
                }

                match resp.json::<OllamaResponse>() {
                    Ok(ollama_resp) => parse_llm_response(&ollama_resp.response),
                    Err(e) => {
                        debug!("Failed to parse LLM response: {e}");
                        None
                    }
                }
            }
            Err(e) => {
                debug!("LLM request error: {e}");
                None
            }
        }
    }
}

/// Parse the LLM response text, extracting JSON from possibly noisy output.
fn parse_llm_response(text: &str) -> Option<LlmSummary> {
    let trimmed = text.trim();

    // Try direct parse
    if let Ok(summary) = serde_json::from_str::<LlmSummary>(trimmed) {
        return Some(summary);
    }

    // Try to find JSON in the response (LLMs sometimes wrap in markdown)
    if let Some(start) = trimmed.find('{') {
        if let Some(end) = trimmed.rfind('}') {
            if start < end {
                let json_str = &trimmed[start..=end];
                if let Ok(summary) = serde_json::from_str::<LlmSummary>(json_str) {
                    return Some(summary);
                }
            }
        }
    }

    debug!("Could not parse LLM response: {}", &trimmed[..trimmed.len().min(200)]);
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_clean_json() {
        let json = r#"{"keywords":["python","auth"],"client":"ACME","project":"api","summary":"Writing code"}"#;
        let result = parse_llm_response(json).unwrap();
        assert_eq!(result.keywords, vec!["python", "auth"]);
        assert_eq!(result.client.as_deref(), Some("ACME"));
        assert_eq!(result.project.as_deref(), Some("api"));
    }

    #[test]
    fn test_parse_markdown_wrapped() {
        let text = "Here's the analysis:\n```json\n{\"keywords\":[\"rust\"],\"client\":null,\"project\":\"my-proj\",\"summary\":\"Coding\"}\n```";
        let result = parse_llm_response(text).unwrap();
        assert_eq!(result.keywords, vec!["rust"]);
        assert_eq!(result.project.as_deref(), Some("my-proj"));
    }

    #[test]
    fn test_parse_partial_fields() {
        let json = r#"{"keywords":["test"]}"#;
        let result = parse_llm_response(json).unwrap();
        assert_eq!(result.keywords, vec!["test"]);
        assert!(result.client.is_none());
    }

    #[test]
    fn test_parse_garbage() {
        assert!(parse_llm_response("this is not json at all").is_none());
    }
}
