//! Idle detection for aw-watcher-enhanced.
//!
//! Detects user inactivity via HID idle time:
//! - macOS: IOKit HID system idle time
//! - Linux: XScreenSaver idle time via xprintidle
//! - Windows: GetLastInputInfo

use std::time::Instant;

/// Get the system idle time in seconds.
pub fn get_idle_time() -> f64 {
    #[cfg(target_os = "macos")]
    return macos::get_idle_time();

    #[cfg(target_os = "linux")]
    return linux::get_idle_time();

    #[cfg(target_os = "windows")]
    return windows::get_idle_time();

    #[cfg(not(any(target_os = "macos", target_os = "linux", target_os = "windows")))]
    0.0
}

/// Idle detector with threshold-based state tracking.
pub struct IdleDetector {
    threshold: f64,
    idle_since: Option<Instant>,
}

impl IdleDetector {
    pub fn new(threshold: f64) -> Self {
        Self {
            threshold,
            idle_since: None,
        }
    }

    /// Check if the user is currently idle.
    pub fn is_idle(&mut self) -> bool {
        let idle_time = get_idle_time();
        let is_idle = idle_time >= self.threshold;

        if is_idle && self.idle_since.is_none() {
            self.idle_since = Some(Instant::now());
        } else if !is_idle {
            self.idle_since = None;
        }

        is_idle
    }

    /// Check if idle with a custom threshold (0 = any idle time counts).
    #[allow(dead_code)]
    pub fn is_idle_with_threshold(&self, threshold: f64) -> bool {
        get_idle_time() >= threshold
    }

    /// Get how long the user has been continuously idle (None if not idle).
    #[allow(dead_code)]
    pub fn idle_duration(&self) -> Option<f64> {
        self.idle_since
            .map(|since| since.elapsed().as_secs_f64())
    }

    /// Get the current idle time from the system.
    #[allow(dead_code)]
    pub fn current_idle_time(&self) -> f64 {
        get_idle_time()
    }
}

// ─── macOS ───────────────────────────────────────────────────────────────────

#[cfg(target_os = "macos")]
mod macos {
    use std::ffi::c_void;

    #[link(name = "IOKit", kind = "framework")]
    extern "C" {
        fn IOServiceGetMatchingService(
            main_port: u32,
            matching: *const c_void,
        ) -> u32;
        fn IOServiceMatching(name: *const u8) -> *const c_void;
        fn IORegistryEntryCreateCFProperty(
            entry: u32,
            key: *const c_void,
            allocator: *const c_void,
            options: u32,
        ) -> *const c_void;
        fn IOObjectRelease(object: u32) -> i32;
    }

    #[link(name = "CoreFoundation", kind = "framework")]
    extern "C" {
        fn CFStringCreateWithCString(
            alloc: *const c_void,
            c_str: *const u8,
            encoding: u32,
        ) -> *const c_void;
        fn CFNumberGetValue(
            number: *const c_void,
            the_type: i64,
            value_ptr: *mut c_void,
        ) -> bool;
        fn CFRelease(cf: *const c_void);
    }

    const K_CF_STRING_ENCODING_UTF8: u32 = 0x08000100;
    const K_CF_NUMBER_SINT64_TYPE: i64 = 4;

    pub fn get_idle_time() -> f64 {
        unsafe {
            let service_name = b"IOHIDSystem\0";
            let matching = IOServiceMatching(service_name.as_ptr());
            if matching.is_null() {
                return 0.0;
            }

            let service = IOServiceGetMatchingService(0, matching);
            // matching is consumed by IOServiceGetMatchingService
            if service == 0 {
                return 0.0;
            }

            let key_str = b"HIDIdleTime\0";
            let key = CFStringCreateWithCString(
                std::ptr::null(),
                key_str.as_ptr(),
                K_CF_STRING_ENCODING_UTF8,
            );
            if key.is_null() {
                IOObjectRelease(service);
                return 0.0;
            }

            let value = IORegistryEntryCreateCFProperty(service, key, std::ptr::null(), 0);
            CFRelease(key);
            IOObjectRelease(service);

            if value.is_null() {
                return 0.0;
            }

            let mut idle_ns: i64 = 0;
            let ok = CFNumberGetValue(
                value,
                K_CF_NUMBER_SINT64_TYPE,
                &mut idle_ns as *mut i64 as *mut c_void,
            );
            CFRelease(value);

            if ok {
                idle_ns as f64 / 1_000_000_000.0
            } else {
                0.0
            }
        }
    }
}

// ─── Linux ───────────────────────────────────────────────────────────────────

#[cfg(target_os = "linux")]
mod linux {
    use std::process::Command;

    pub fn get_idle_time() -> f64 {
        // xprintidle returns idle time in milliseconds
        Command::new("xprintidle")
            .output()
            .ok()
            .and_then(|o| {
                if o.status.success() {
                    String::from_utf8_lossy(&o.stdout)
                        .trim()
                        .parse::<f64>()
                        .ok()
                        .map(|ms| ms / 1000.0)
                } else {
                    None
                }
            })
            .unwrap_or(0.0)
    }
}

// ─── Windows ─────────────────────────────────────────────────────────────────

#[cfg(target_os = "windows")]
mod windows {
    use windows::Win32::UI::Input::KeyboardAndMouse::{GetLastInputInfo, LASTINPUTINFO};

    pub fn get_idle_time() -> f64 {
        unsafe {
            let mut lii = LASTINPUTINFO {
                cbSize: std::mem::size_of::<LASTINPUTINFO>() as u32,
                dwTime: 0,
            };
            if GetLastInputInfo(&mut lii).as_bool() {
                let tick_count = windows::Win32::System::SystemInformation::GetTickCount();
                let idle_ms = tick_count - lii.dwTime;
                idle_ms as f64 / 1000.0
            } else {
                0.0
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_idle_time() {
        let idle = get_idle_time();
        // Should return non-negative; in CI may be 0
        assert!(idle >= 0.0);
    }

    #[test]
    fn test_idle_detector() {
        let mut detector = IdleDetector::new(3600.0); // High threshold
        // With a 1-hour threshold, we should not be idle
        assert!(!detector.is_idle());
        assert!(detector.idle_duration().is_none());
    }

    #[test]
    fn test_idle_with_zero_threshold() {
        let detector = IdleDetector::new(60.0);
        // With threshold 0, idle time >= 0 should be true
        assert!(detector.is_idle_with_threshold(0.0));
    }
}
