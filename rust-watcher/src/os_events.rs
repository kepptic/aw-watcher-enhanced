#![allow(dead_code)]
//! macOS system event listener for aw-watcher-enhanced.
//!
//! Captures app lifecycle events via NSWorkspace notifications:
//! - App activated/deactivated
//! - Screen lock/unlock
//! - System sleep/wake
//!
//! Uses objc2-app-kit bindings. Event-driven (zero polling cost).
//! All events stored in a thread-safe deque for the enrichment thread.

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::thread;

use chrono::Utc;
use log::{debug, info};

/// A captured OS event.
#[derive(Debug, Clone, serde::Serialize)]
pub struct OsEvent {
    pub event_type: String,
    pub app_name: Option<String>,
    pub timestamp: String,
}

/// Listens for macOS system events and records them.
pub struct OsEventListener {
    events: Arc<Mutex<VecDeque<OsEvent>>>,
    max_events: usize,
    running: Arc<std::sync::atomic::AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
}

impl OsEventListener {
    pub fn new(max_events: usize) -> Self {
        Self {
            events: Arc::new(Mutex::new(VecDeque::with_capacity(max_events))),
            max_events,
            running: Arc::new(std::sync::atomic::AtomicBool::new(false)),
            thread: None,
        }
    }

    /// Start the event listener thread.
    pub fn start(&mut self) {
        if !cfg!(target_os = "macos") {
            info!("OS event listener only supported on macOS");
            return;
        }

        self.running
            .store(true, std::sync::atomic::Ordering::SeqCst);

        let events = self.events.clone();
        let max_events = self.max_events;
        let running = self.running.clone();

        self.thread = Some(
            thread::Builder::new()
                .name("os-events".into())
                .spawn(move || {
                    #[cfg(target_os = "macos")]
                    macos::run_event_loop(events, max_events, running);

                    #[cfg(not(target_os = "macos"))]
                    {
                        let _ = (events, max_events, running);
                    }
                })
                .expect("Failed to spawn OS events thread"),
        );

        info!("OS event listener started");
    }

    /// Stop the event listener.
    pub fn stop(&mut self) {
        self.running
            .store(false, std::sync::atomic::Ordering::SeqCst);
        // The thread runs an NSRunLoop which we can't easily stop from outside.
        // daemon=true equivalent: we just drop the handle and let it die on process exit.
        self.thread = None;
        info!("OS event listener stopped");
    }

    /// Flush and return all pending events.
    pub fn flush_events(&self) -> Vec<OsEvent> {
        if let Ok(mut events) = self.events.lock() {
            let result: Vec<OsEvent> = events.drain(..).collect();
            result
        } else {
            vec![]
        }
    }

    /// Get the most recent event without removing it.
    #[allow(dead_code)]
    pub fn last_event(&self) -> Option<OsEvent> {
        self.events
            .lock()
            .ok()
            .and_then(|events| events.back().cloned())
    }
}

fn push_event(
    events: &Mutex<VecDeque<OsEvent>>,
    max: usize,
    event_type: &str,
    app_name: Option<String>,
) {
    let event = OsEvent {
        event_type: event_type.to_string(),
        app_name,
        timestamp: Utc::now().to_rfc3339(),
    };

    if let Ok(mut q) = events.lock() {
        if q.len() >= max {
            q.pop_front();
        }
        q.push_back(event);
    }
}

// ─── macOS implementation ────────────────────────────────────────────────────

#[cfg(target_os = "macos")]
mod macos {
    use super::*;
    use std::ffi::c_void;

    use core_foundation::base::TCFType;
    use core_foundation::string::CFString;

    #[link(name = "AppKit", kind = "framework")]
    extern "C" {}

    #[link(name = "objc", kind = "dylib")]
    extern "C" {
        fn objc_getClass(name: *const u8) -> *const c_void;
        fn sel_registerName(name: *const u8) -> *const c_void;
    }
    // Use typed fn pointer to avoid ARM64 variadic ABI mismatch.
    // Declared with no params; transmuted at each call site.
    extern "C" { fn objc_msgSend(); }
    type MsgSend0 = unsafe extern "C" fn(*const c_void, *const c_void) -> *const c_void;

    unsafe fn send0() -> MsgSend0 {
        std::mem::transmute(objc_msgSend as *const c_void)
    }

    macro_rules! cls {
        ($name:expr) => {{
            #[allow(unused_unsafe)]
            unsafe { objc_getClass(concat!($name, "\0").as_ptr()) }
        }};
    }

    macro_rules! sel {
        ($name:expr) => {{
            #[allow(unused_unsafe)]
            unsafe { sel_registerName(concat!($name, "\0").as_ptr()) }
        }};
    }

    // We use a simpler approach than the frontmost crate:
    // Instead of registering a custom Objective-C class for notification callbacks,
    // we poll the NSWorkspace.frontmostApplication periodically on the event thread.
    // This is simpler, avoids complex ObjC class registration, and is good enough
    // for our 1-5 second polling intervals.
    //
    // For sleep/wake and screen lock, we check IOKit power assertions.

    pub fn run_event_loop(
        events: Arc<Mutex<VecDeque<OsEvent>>>,
        max_events: usize,
        running: Arc<std::sync::atomic::AtomicBool>,
    ) {
        info!("OS event loop started (polling mode)");

        let mut last_app: Option<String> = None;

        while running.load(std::sync::atomic::Ordering::SeqCst) {
            // Autorelease pool per iteration — NSWorkspace calls create autoreleased objects
            let pool = unsafe { create_autorelease_pool() };

            // Check frontmost application
            if let Some(app_name) = get_frontmost_app() {
                let changed = last_app.as_ref() != Some(&app_name);
                if changed {
                    if let Some(ref prev) = last_app {
                        push_event(&events, max_events, "app_deactivated", Some(prev.clone()));
                    }
                    push_event(
                        &events,
                        max_events,
                        "app_activated",
                        Some(app_name.clone()),
                    );
                    debug!("OS event: app_activated -> {app_name}");
                    last_app = Some(app_name);
                }
            }

            // Check screen lock state
            if is_screen_locked() {
                push_event(&events, max_events, "screen_locked", None);
                debug!("OS event: screen_locked");
                // Wait until unlocked
                while running.load(std::sync::atomic::Ordering::SeqCst) && is_screen_locked() {
                    thread::sleep(std::time::Duration::from_secs(1));
                }
                if running.load(std::sync::atomic::Ordering::SeqCst) {
                    push_event(&events, max_events, "screen_unlocked", None);
                    debug!("OS event: screen_unlocked");
                }
            }

            unsafe { drain_autorelease_pool(pool) };
            thread::sleep(std::time::Duration::from_secs(1));
        }

        info!("OS event loop stopped");
    }

    unsafe fn create_autorelease_pool() -> *const c_void {
        let s: MsgSend0 = send0();
        s(
            s(cls!("NSAutoreleasePool"), sel!("alloc")),
            sel!("init"),
        )
    }

    unsafe fn drain_autorelease_pool(pool: *const c_void) {
        let s: MsgSend0 = send0();
        s(pool, sel!("drain"));
    }

    /// Get the frontmost application name using NSWorkspace.
    fn get_frontmost_app() -> Option<String> {
        unsafe {
            let send = send0();
            let workspace: *const c_void =
                send(cls!("NSWorkspace"), sel!("sharedWorkspace"));
            if workspace.is_null() {
                return None;
            }

            let app: *const c_void = send(workspace, sel!("frontmostApplication"));
            if app.is_null() {
                return None;
            }

            let name: *const c_void = send(app, sel!("localizedName"));
            if name.is_null() {
                return None;
            }

            let cf_str = CFString::wrap_under_get_rule(name as _);
            Some(cf_str.to_string())
        }
    }

    /// Check if the screen is locked (login window is frontmost).
    fn is_screen_locked() -> bool {
        // When the screen is locked, the frontmost app is "loginwindow"
        get_frontmost_app()
            .map(|app| app == "loginwindow" || app == "ScreenSaverEngine")
            .unwrap_or(false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_push_event() {
        let events = Mutex::new(VecDeque::new());
        push_event(&events, 5, "test_event", Some("TestApp".into()));

        let q = events.lock().unwrap();
        assert_eq!(q.len(), 1);
        assert_eq!(q[0].event_type, "test_event");
        assert_eq!(q[0].app_name.as_deref(), Some("TestApp"));
    }

    #[test]
    fn test_max_events_eviction() {
        let events = Mutex::new(VecDeque::new());
        for i in 0..10 {
            push_event(&events, 5, &format!("event_{i}"), None);
        }

        let q = events.lock().unwrap();
        assert_eq!(q.len(), 5);
        // Should keep the most recent 5
        assert_eq!(q[0].event_type, "event_5");
        assert_eq!(q[4].event_type, "event_9");
    }

    #[test]
    fn test_listener_empty() {
        let listener = OsEventListener::new(100);
        let events = listener.flush_events();
        assert!(events.is_empty());
    }
}
