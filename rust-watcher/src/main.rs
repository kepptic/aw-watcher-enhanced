mod aw_client;
mod browser;
mod categorizer;
mod config;
mod document;
mod file_tracker;
mod idle;
mod ide_merger;
mod llm;
mod meeting;
mod ocr;
mod os_events;
mod privacy;
mod window;

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use chrono::Utc;
use clap::Parser;
use log::{debug, error, info, warn};

use aw_client::{AwClient, Event};
use window::WindowInfo;

const WATCHER_NAME: &str = "aw-watcher-enhanced";

/// Enhanced ActivityWatch watcher with rich context capture.
#[derive(Parser, Debug)]
#[command(version, about)]
struct Args {
    /// Use testing server (port 5666)
    #[arg(long)]
    testing: bool,

    /// Enable verbose debug logging
    #[arg(short, long)]
    verbose: bool,

    /// Skip OCR/LLM features
    #[arg(long)]
    no_ocr: bool,

    /// Skip file watching
    #[arg(long)]
    no_file_watch: bool,
}

/// Shared state between heartbeat and enrichment threads.
struct SharedState {
    /// Stable enriched data for heartbeat merging (excludes volatile fields).
    enriched_data: Option<serde_json::Map<String, serde_json::Value>>,
    /// The (app, title) key the enriched data belongs to.
    enriched_window_key: Option<(String, String)>,
}

/// Fields that change every enrichment cycle (OCR, file activity, OS events).
/// These break pulse merging and are sent to a separate snapshot bucket.
const VOLATILE_KEYS: &[&str] = &[
    "ocr_keywords",
    "ocr_summary",
    "ocr_project",
    "ocr_client",
    "recent_files",
    "os_events",
];

fn main() {
    let args = Args::parse();

    // Initialize logging
    let log_level = if args.verbose { "debug" } else { "info" };
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or(log_level))
        .format_timestamp_millis()
        .init();

    info!("Starting {WATCHER_NAME}");

    // Check Accessibility permission (macOS) — required for AX API window capture.
    // If not granted, opens System Settings prompt for the user to approve.
    #[cfg(target_os = "macos")]
    {
        if !check_accessibility_permission() {
            warn!("Accessibility permission not granted — window titles will be unavailable");
            warn!("Please grant access in System Settings → Privacy & Security → Accessibility");
        }
    }

    // Load configuration
    let config = config::load_config();
    info!(
        "Config: heartbeat={}s, enrichment={}s, idle_threshold={}s",
        config.watcher.heartbeat_interval,
        config.watcher.poll_time,
        config.smart_capture.idle_threshold
    );

    // Set up signal handling
    let running = Arc::new(AtomicBool::new(true));
    {
        let running = running.clone();
        ctrlc::set_handler(move || {
            info!("Received interrupt, shutting down...");
            running.store(false, Ordering::SeqCst);
        })
        .expect("Error setting Ctrl-C handler");
    }

    // Connect to ActivityWatch server
    let client = match AwClient::new(WATCHER_NAME, args.testing) {
        Ok(c) => Arc::new(c),
        Err(e) => {
            error!("Failed to create AW client: {e}");
            std::process::exit(1);
        }
    };

    let bucket_id = format!("{}_{}", WATCHER_NAME, client.hostname);

    // Wait for server to be available
    info!("Waiting for aw-server...");
    for _ in 0..30 {
        if client.is_alive() {
            break;
        }
        thread::sleep(Duration::from_secs(1));
    }

    // Create buckets — main (stable, mergeable) + snapshot (volatile OCR/files)
    if let Err(e) = client.create_bucket(&bucket_id, "currentwindow") {
        error!("Failed to create bucket: {e}");
        std::process::exit(1);
    }
    let snapshot_bucket_id = format!("{}_snapshot_{}", WATCHER_NAME, client.hostname);
    if let Err(e) = client.create_bucket(&snapshot_bucket_id, "enrichment-snapshot") {
        warn!("Failed to create snapshot bucket: {e} — volatile data won't be stored");
    }
    info!("Bucket ready: {bucket_id}");

    // Shared state between threads
    let shared = Arc::new(Mutex::new(SharedState {
        enriched_data: None,
        enriched_window_key: None,
    }));

    // Track window changes for the enrichment thread
    let window_changed = Arc::new(AtomicBool::new(true));

    // Start file activity tracker
    let file_tracker = if !args.no_file_watch {
        let mut tracker = file_tracker::FileActivityTracker::new(50);
        tracker.start(None);
        Some(Arc::new(Mutex::new(tracker)))
    } else {
        None
    };

    // ── Enrichment thread ────────────────────────────────────────────────
    let enrichment_handle = {
        let running = running.clone();
        let shared = shared.clone();
        let window_changed = window_changed.clone();
        let client = client.clone();
        let config = config.clone();
        let file_tracker = file_tracker.clone();
        let no_ocr = args.no_ocr;
        let snapshot_bucket_id = snapshot_bucket_id.clone();

        thread::Builder::new()
            .name("enrichment".into())
            .spawn(move || {
                info!("Enrichment thread started");

                let mut browser_merger =
                    browser::BrowserDataMerger::new(config.browser.bucket_refresh_interval as f64);
                let mut ide_merger = ide_merger::IdeDataMerger::new();
                let mut meeting_detector = meeting::MeetingDetector::new();
                let mut ocr_engine = if !no_ocr && config.ocr.enabled {
                    let engine = ocr::OcrEngine::new(
                        config.smart_capture.min_ocr_interval,
                        config.ocr.max_keywords,
                    );
                    if engine.is_available() {
                        info!("OCR engine available");
                        Some(engine)
                    } else {
                        None
                    }
                } else {
                    None
                };
                let mut os_listener = os_events::OsEventListener::new(100);
                os_listener.start();

                let _llm_client = if !no_ocr && config.llm.enabled {
                    let c = llm::LlmClient::new(&config.llm);
                    if c.is_available() {
                        info!("LLM (Ollama) available: {}", config.llm.model);
                        Some(c)
                    } else {
                        info!("LLM (Ollama) not available, skipping OCR summarization");
                        None
                    }
                } else {
                    None
                };

                let poll_time_ms = (config.watcher.poll_time * 1000.0) as u64;

                while running.load(Ordering::SeqCst) {
                    // Wait for window change or periodic timeout
                    let mut waited = 0u64;
                    while waited < poll_time_ms && running.load(Ordering::SeqCst) {
                        if window_changed.swap(false, Ordering::SeqCst) {
                            break;
                        }
                        thread::sleep(Duration::from_millis(100));
                        waited += 100;
                    }

                    if !running.load(Ordering::SeqCst) {
                        break;
                    }

                    // Capture full enriched state
                    if let Some(info) = window::get_current_window() {
                        let mut data = serde_json::Map::new();
                        data.insert("app".into(), info.app.clone().into());
                        data.insert("title".into(), info.title.clone().into());

                        // Privacy filter first — may exclude or redact
                        if !privacy::apply_privacy_filters(&mut data, &config.privacy) {
                            debug!("Event excluded by privacy filter");
                            // Store empty enriched state so heartbeat uses basic data
                            if let Ok(mut state) = shared.lock() {
                                state.enriched_data = None;
                                state.enriched_window_key = None;
                            }
                            continue;
                        }

                        // Parse document context
                        if let Some(doc) =
                            document::parse_document_context(&info.app, &info.title)
                        {
                            if let Some(f) = &doc.filename {
                                data.insert("doc_file".into(), f.clone().into());
                            }
                            if let Some(p) = &doc.project {
                                data.insert("doc_project".into(), p.clone().into());
                            }
                            if let Some(t) = &doc.doc_type {
                                data.insert("doc_type".into(), t.clone().into());
                            }
                            if let Some(e) = &doc.extension {
                                data.insert("doc_ext".into(), e.clone().into());
                            }
                        }

                        // Browser data merge — use web extension's URL/title
                        let mut url = String::new();
                        let mut domain = String::new();
                        let mut effective_title = info.title.clone();
                        if config.browser.enabled && browser::is_browser_app(&info.app) {
                            if let Some(bd) = browser_merger.get_browser_data(&client) {
                                url = bd.url.clone();
                                domain = bd.domain.clone();
                                data.insert("url".into(), bd.url.into());
                                data.insert("domain".into(), bd.domain.into());
                                // Use the web extension's clean tab title instead of
                                // the AX API window title (which has browser suffix)
                                if !bd.tab_title.is_empty() {
                                    effective_title = bd.tab_title.clone();
                                    data.insert("title".into(), bd.tab_title.into());
                                }
                            }
                        }

                        // Categorize (after browser merge so URL/domain are available)
                        let category = categorizer::categorize_with_url(
                            &info.app, &effective_title, &url, &domain,
                        );
                        data.insert("category".into(), category.into());

                        // Extract IT client/tenant from known management tool URLs
                        if let Some((client_name, tool)) =
                            categorizer::extract_it_client(&url, &domain, &effective_title)
                        {
                            data.insert("it_client".into(), client_name.into());
                            data.insert("it_tool".into(), tool.into());
                        }

                        // Extract remote host for RDP/remote desktop sessions
                        if let Some(host) =
                            categorizer::extract_remote_host(&info.app, &effective_title)
                        {
                            data.insert("remote_host".into(), host.into());
                        }

                        // IDE data merge (before AI detection — provides terminal context)
                        if let Some(ide_data) = ide_merger.get_ide_data(&client, &info.app) {
                            for (k, v) in ide_data.fields {
                                data.insert(k, v);
                            }
                        }

                        // Detect AI assistant from title or IDE terminal name
                        let title_lower = info.title.to_lowercase();
                        let ide_terminal = data
                            .get("ide_active_terminal")
                            .and_then(|v| v.as_str())
                            .unwrap_or("");
                        // Claude Code sets VS Code terminal name to its version (e.g., "2.1.69")
                        // With cwd enrichment it becomes "2.1.69 cent" — check first word
                        let term_name = ide_terminal.split_whitespace().next().unwrap_or("");
                        let is_claude_terminal = !term_name.is_empty()
                            && term_name.contains('.')
                            && term_name
                                .chars()
                                .all(|c| c.is_ascii_digit() || c == '.');

                        if title_lower.contains("claude") || is_claude_terminal {
                            data.insert("ai_assistant".into(), "claude_code".into());
                        } else if title_lower.contains("copilot") {
                            data.insert("ai_assistant".into(), "github_copilot".into());
                        } else if title_lower.contains("aider") {
                            data.insert("ai_assistant".into(), "aider".into());
                        } else if info.app.to_lowercase().contains("cursor") {
                            data.insert("ai_assistant".into(), "cursor".into());
                        }

                        // Meeting detection
                        if config.meeting.enabled {
                            let url = data
                                .get("url")
                                .and_then(|v| v.as_str())
                                .unwrap_or("");
                            let (in_meeting, platform) = meeting_detector.detect(
                                &info.app,
                                &info.title,
                                url,
                                config.meeting.detect_subprocess,
                            );
                            if in_meeting {
                                data.insert("in_meeting".into(), true.into());
                                data.insert("meeting_app".into(), platform.into());

                                let (camera, mic) = meeting::detect_camera_mic();
                                if camera {
                                    data.insert("camera_active".into(), true.into());
                                }
                                if mic {
                                    data.insert("mic_active".into(), true.into());
                                }
                            }
                        }

                        // Recent file activity
                        if let Some(ref ft) = file_tracker {
                            if let Ok(tracker) = ft.lock() {
                                let files = tracker.get_recent_files(5);
                                if !files.is_empty() {
                                    let file_list: Vec<serde_json::Value> = files
                                        .iter()
                                        .map(|f| {
                                            serde_json::json!({
                                                "path": f.path,
                                                "action": f.action,
                                            })
                                        })
                                        .collect();
                                    data.insert("recent_files".into(), file_list.into());
                                }
                            }
                        }

                        // OCR capture — focused window only for better accuracy
                        if let Some(ref mut engine) = ocr_engine {
                            let wid = window::get_focused_window_id();
                            debug!("OCR window_id={:?} for {}", wid, info.app);
                            if let Some(ocr_result) = engine.capture_and_ocr_window(wid) {
                                if !ocr_result.keywords.is_empty() {
                                    let kw: Vec<serde_json::Value> = ocr_result
                                        .keywords
                                        .iter()
                                        .map(|k| k.clone().into())
                                        .collect();
                                    data.insert("ocr_keywords".into(), kw.into());
                                }
                                // Run LLM summarization with app context
                                if let Some(ref llm) = _llm_client {
                                    if let Some(summary) = llm.summarize_ocr_with_context(
                                        &ocr_result.full_text,
                                        &info.app,
                                        &effective_title,
                                    ) {
                                        if let Some(s) = summary.summary {
                                            data.insert("ocr_summary".into(), s.into());
                                        }
                                        if let Some(c) = summary.client {
                                            data.insert("ocr_client".into(), c.into());
                                        }
                                        if let Some(p) = summary.project {
                                            data.insert("ocr_project".into(), p.into());
                                        }
                                    }
                                }
                            }
                        }

                        // OS events (flush recent)
                        let os_events = os_listener.flush_events();
                        if !os_events.is_empty() {
                            let events_json: Vec<serde_json::Value> = os_events
                                .iter()
                                .map(|e| {
                                    serde_json::json!({
                                        "type": e.event_type,
                                        "app": e.app_name,
                                    })
                                })
                                .collect();
                            data.insert("os_events".into(), events_json.into());
                        }

                        // Separate volatile fields (OCR, files, OS events) from stable data.
                        // Heartbeat thread only sends stable fields so aw-server can pulse-merge.
                        let mut volatile = serde_json::Map::new();
                        for &key in VOLATILE_KEYS {
                            if let Some(v) = data.remove(key) {
                                volatile.insert(key.into(), v);
                            }
                        }

                        // Send volatile data to snapshot bucket (once per enrichment cycle)
                        if !volatile.is_empty() {
                            // Include app/title for context
                            volatile.insert("app".into(), info.app.clone().into());
                            volatile.insert("title".into(), info.title.clone().into());
                            let snap_event = Event {
                                timestamp: Utc::now(),
                                duration: 0.0,
                                data: volatile,
                            };
                            let snap_pulse = config.watcher.poll_time + 1.0;
                            if let Err(e) = client.heartbeat(&snapshot_bucket_id, &snap_event, snap_pulse) {
                                debug!("Snapshot heartbeat failed: {e}");
                            }
                        }

                        // Store stable enriched state for heartbeat merging
                        let wkey = (info.app.clone(), info.title.clone());
                        if let Ok(mut state) = shared.lock() {
                            state.enriched_data = Some(data);
                            state.enriched_window_key = Some(wkey);
                        }

                        debug!(
                            "Enriched: {} - {}",
                            info.app,
                            &info.title[..info.title.len().min(50)]
                        );
                    }
                }
                info!("Enrichment thread stopped");
            })
            .expect("Failed to spawn enrichment thread")
    };

    // ── Heartbeat thread ─────────────────────────────────────────────────
    let heartbeat_handle = {
        let running = running.clone();
        let client = client.clone();
        let shared = shared.clone();
        let window_changed = window_changed.clone();
        let bucket_id = bucket_id.clone();
        let config = config.clone();

        thread::Builder::new()
            .name("heartbeat".into())
            .spawn(move || {
                info!("Heartbeat thread started ({}s interval)", config.watcher.heartbeat_interval);
                let mut last_window: Option<(String, String)> = None;
                // Cache the last enriched data so every heartbeat sends consistent fields.
                // Without this, heartbeats alternate between 2-key basic and 22-key enriched
                // data, preventing the server from merging them into continuous events.
                let mut last_enriched: Option<serde_json::Map<String, serde_json::Value>> = None;
                let mut idle_detector = idle::IdleDetector::new(config.smart_capture.idle_threshold);
                let sleep_ms = (config.watcher.heartbeat_interval * 1000.0) as u64;
                let pulsetime = config.watcher.heartbeat_interval + 1.0;

                while running.load(Ordering::SeqCst) {
                    // Check idle
                    if idle_detector.is_idle() {
                        debug!("User idle, skipping heartbeat");
                        thread::sleep(Duration::from_millis(sleep_ms));
                        continue;
                    }

                    let window = window::get_current_window().unwrap_or(WindowInfo {
                        app: "unknown".into(),
                        title: String::new(),
                    });

                    let current_key = (window.app.clone(), window.title.clone());

                    // Check for window change
                    let changed = last_window.as_ref() != Some(&current_key);
                    if changed {
                        // Clear stale enriched state
                        if let Ok(mut state) = shared.lock() {
                            state.enriched_data = None;
                            state.enriched_window_key = None;
                        }
                        last_enriched = None;
                        // Signal enrichment thread
                        window_changed.store(true, Ordering::SeqCst);
                        debug!(
                            "Window: {} - {}",
                            window.app,
                            &window.title[..window.title.len().min(50)]
                        );
                    }

                    // Build event data — use enriched state if available, else reuse
                    // the last known enriched data so the server can merge heartbeats.
                    let data = if let Ok(state) = shared.lock() {
                        if state.enriched_window_key.as_ref() == Some(&current_key) {
                            if let Some(ref enriched) = state.enriched_data {
                                last_enriched = Some(enriched.clone());
                                enriched.clone()
                            } else if let Some(ref cached) = last_enriched {
                                cached.clone()
                            } else {
                                quick_enriched_data(&window)
                            }
                        } else if let Some(ref cached) = last_enriched {
                            // Same window, enrichment thread hasn't updated yet — reuse cache
                            cached.clone()
                        } else {
                            quick_enriched_data(&window)
                        }
                    } else {
                        quick_enriched_data(&window)
                    };

                    let event = Event {
                        timestamp: Utc::now(),
                        duration: 0.0,
                        data,
                    };

                    if let Err(e) = client.heartbeat(&bucket_id, &event, pulsetime) {
                        warn!("Heartbeat failed: {e}");
                    }

                    last_window = Some(current_key);
                    thread::sleep(Duration::from_millis(sleep_ms));
                }

                info!("Heartbeat thread stopped");
            })
            .expect("Failed to spawn heartbeat thread")
    };

    // Main thread waits for stop signal
    while running.load(Ordering::SeqCst) {
        thread::sleep(Duration::from_millis(500));
    }

    info!("Waiting for threads to finish...");
    let _ = heartbeat_handle.join();
    let _ = enrichment_handle.join();
    info!("{WATCHER_NAME} stopped");
}

/// Build event data with cheap enrichment (no network/OCR).
/// Includes category and document context so the first heartbeat after
/// a window change has enough fields to merge with later enriched heartbeats.
fn quick_enriched_data(window: &WindowInfo) -> serde_json::Map<String, serde_json::Value> {
    let mut m = serde_json::Map::new();
    m.insert("app".into(), window.app.clone().into());
    m.insert("title".into(), window.title.clone().into());

    // Document context (pure string parsing, no I/O)
    if let Some(doc) = document::parse_document_context(&window.app, &window.title) {
        if let Some(f) = &doc.filename {
            m.insert("doc_file".into(), f.clone().into());
        }
        if let Some(p) = &doc.project {
            m.insert("doc_project".into(), p.clone().into());
        }
        if let Some(t) = &doc.doc_type {
            m.insert("doc_type".into(), t.clone().into());
        }
        if let Some(e) = &doc.extension {
            m.insert("doc_ext".into(), e.clone().into());
        }
    }

    // Category (pure function)
    let category = categorizer::categorize_with_url(&window.app, &window.title, "", "");
    m.insert("category".into(), category.into());

    m
}

/// Check macOS Accessibility permission and prompt the user if not granted.
/// Returns true if permission is already granted.
#[cfg(target_os = "macos")]
fn check_accessibility_permission() -> bool {
    use std::ffi::c_void;

    #[link(name = "ApplicationServices", kind = "framework")]
    extern "C" {
        fn AXIsProcessTrusted() -> bool;
    }

    #[link(name = "CoreFoundation", kind = "framework")]
    extern "C" {
        fn CFDictionaryCreate(
            allocator: *const c_void,
            keys: *const *const c_void,
            values: *const *const c_void,
            num_values: isize,
            key_callbacks: *const c_void,
            value_callbacks: *const c_void,
        ) -> *const c_void;
        fn CFRelease(cf: *const c_void);
        static kCFTypeDictionaryKeyCallBacks: c_void;
        static kCFTypeDictionaryValueCallBacks: c_void;
        static kCFBooleanTrue: *const c_void;
    }

    extern "C" {
        // This key is in ApplicationServices but we need to reference it directly
        static kAXTrustedCheckOptionPrompt: *const c_void;
        fn AXIsProcessTrustedWithOptions(options: *const c_void) -> bool;
    }

    unsafe {
        // Quick check first — avoid showing the prompt if already trusted
        if AXIsProcessTrusted() {
            info!("Accessibility permission: granted");
            return true;
        }

        // Not trusted — show the system prompt
        info!("Accessibility permission: not granted, requesting...");
        let keys = [kAXTrustedCheckOptionPrompt];
        let values = [kCFBooleanTrue];
        let options = CFDictionaryCreate(
            std::ptr::null(),
            keys.as_ptr(),
            values.as_ptr(),
            1,
            &kCFTypeDictionaryKeyCallBacks as *const c_void,
            &kCFTypeDictionaryValueCallBacks as *const c_void,
        );

        let trusted = AXIsProcessTrustedWithOptions(options);
        CFRelease(options);
        trusted
    }
}
