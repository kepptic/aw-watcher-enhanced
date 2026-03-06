#![allow(dead_code)]
//! Screen capture and OCR for aw-watcher-enhanced.
//!
//! macOS: ScreenCaptureKit (capture) + Vision framework (OCR).
//! Captures the current screen and extracts text using Apple's native
//! VNRecognizeTextRequest. Zero external dependencies for OCR.

use log::{info, warn};
use std::collections::HashSet;
use std::time::Instant;

/// OCR result with extracted text and keywords.
#[derive(Debug, Clone, Default)]
pub struct OcrResult {
    pub full_text: String,
    pub keywords: Vec<String>,
}

/// Screen capture + OCR engine.
pub struct OcrEngine {
    last_capture_time: Instant,
    min_interval: f64,
    max_keywords: usize,
    available: bool,
}

impl OcrEngine {
    pub fn new(min_interval: f64, max_keywords: usize) -> Self {
        let available = cfg!(target_os = "macos");
        if available {
            info!("OCR engine: Apple Vision (ScreenCaptureKit + VNRecognizeTextRequest)");
        } else {
            info!("OCR engine: not available on this platform");
        }

        Self {
            last_capture_time: Instant::now() - std::time::Duration::from_secs(999),
            min_interval,
            max_keywords,
            available,
        }
    }

    pub fn is_available(&self) -> bool {
        self.available
    }

    /// Capture the screen and run OCR. Returns None if too soon or unavailable.
    pub fn capture_and_ocr(&mut self) -> Option<OcrResult> {
        if !self.available {
            return None;
        }

        let now = Instant::now();
        if now.duration_since(self.last_capture_time).as_secs_f64() < self.min_interval {
            return None;
        }
        self.last_capture_time = now;

        #[cfg(target_os = "macos")]
        {
            match macos::capture_and_ocr(self.max_keywords) {
                Ok(result) => Some(result),
                Err(e) => {
                    warn!("OCR capture failed: {e}");
                    None
                }
            }
        }

        #[cfg(not(target_os = "macos"))]
        None
    }
}

/// Extract significant keywords from OCR text.
fn extract_keywords(text: &str, max: usize) -> Vec<String> {
    // Common stop words to skip
    static STOP_WORDS: &[&str] = &[
        "the", "and", "for", "are", "but", "not", "you", "all", "can", "had", "her", "was",
        "one", "our", "out", "has", "have", "from", "been", "some", "them", "than", "this",
        "that", "with", "will", "each", "make", "like", "just", "over", "such", "take",
        "file", "edit", "view", "help", "window", "menu", "new", "open", "save", "close",
        "copy", "paste", "undo", "redo", "find", "replace", "select", "delete",
    ];

    let stop_set: HashSet<&str> = STOP_WORDS.iter().copied().collect();

    let mut seen = HashSet::new();
    text.split(|c: char| !c.is_alphanumeric() && c != '_' && c != '-')
        .filter(|w| {
            let lower = w.to_lowercase();
            w.len() >= 4
                && w.len() <= 40
                && !stop_set.contains(lower.as_str())
                && w.chars().any(|c| c.is_alphabetic())
                && seen.insert(lower)
        })
        .take(max)
        .map(|w| w.to_string())
        .collect()
}

// ─── macOS implementation ────────────────────────────────────────────────────

#[cfg(target_os = "macos")]
mod macos {
    use super::{extract_keywords, OcrResult};
    use std::ffi::c_void;

    // ScreenCaptureKit capture via CGWindowList (simpler, no permission prompts for own display)
    #[link(name = "CoreGraphics", kind = "framework")]
    extern "C" {
        fn CGMainDisplayID() -> u32;
        fn CGDisplayBounds(display: u32) -> CGRect;
        fn CGWindowListCreateImage(
            screen_bounds: CGRect,
            list_option: u32,
            window_id: u32,
            image_option: u32,
        ) -> *const c_void; // CGImageRef
        fn CGImageGetWidth(image: *const c_void) -> usize;
        fn CGImageGetHeight(image: *const c_void) -> usize;
    }

    #[link(name = "Foundation", kind = "framework")]
    extern "C" {
        fn CFRelease(cf: *const c_void);
    }

    // Vision framework
    #[link(name = "Vision", kind = "framework")]
    extern "C" {}

    #[repr(C)]
    #[derive(Copy, Clone)]
    struct CGPoint {
        x: f64,
        y: f64,
    }

    #[repr(C)]
    #[derive(Copy, Clone)]
    struct CGSize {
        width: f64,
        height: f64,
    }

    #[repr(C)]
    #[derive(Copy, Clone)]
    struct CGRect {
        origin: CGPoint,
        size: CGSize,
    }

    // CGWindowListOption
    const K_CG_WINDOW_LIST_OPTION_ON_SCREEN_ONLY: u32 = 1;
    // CGWindowImageOption
    const K_CG_WINDOW_IMAGE_DEFAULT: u32 = 0;
    const K_CG_NULL_WINDOW_ID: u32 = 0;

    /// Capture the main display and run Vision OCR on it.
    pub fn capture_and_ocr(max_keywords: usize) -> Result<OcrResult, String> {
        unsafe {
            // Create an autorelease pool to drain all autoreleased ObjC objects
            // (NSArray, VNRecognizedText, etc.) created during OCR.
            // Without this, autoreleased objects accumulate forever in non-main threads.
            #[link(name = "objc", kind = "dylib")]
            extern "C" {
                fn objc_getClass(name: *const u8) -> *const c_void;
                fn sel_registerName(name: *const u8) -> *const c_void;
            }
            extern "C" { fn objc_msgSend(); }
            type MsgSend0 = unsafe extern "C" fn(*const c_void, *const c_void) -> *const c_void;
            let send0: MsgSend0 = std::mem::transmute(objc_msgSend as *const c_void);
            let pool = send0(
                send0(objc_getClass(b"NSAutoreleasePool\0".as_ptr()), sel_registerName(b"alloc\0".as_ptr())),
                sel_registerName(b"init\0".as_ptr()),
            );

            // 1. Capture screen using CGWindowList (works without ScreenCaptureKit permission)
            let display_id = CGMainDisplayID();
            let bounds = CGDisplayBounds(display_id);

            let image = CGWindowListCreateImage(
                bounds,
                K_CG_WINDOW_LIST_OPTION_ON_SCREEN_ONLY,
                K_CG_NULL_WINDOW_ID,
                K_CG_WINDOW_IMAGE_DEFAULT,
            );

            if image.is_null() {
                send0(pool, sel_registerName(b"drain\0".as_ptr()));
                return Err("Failed to capture screen".into());
            }

            let _width = CGImageGetWidth(image);
            let _height = CGImageGetHeight(image);

            // 2. Run Vision OCR using objc_msgSend
            let text = run_vision_ocr(image);
            CFRelease(image);

            // 3. Drain the autorelease pool before returning
            send0(pool, sel_registerName(b"drain\0".as_ptr()));

            let text = text?;

            // 4. Extract keywords
            let keywords = extract_keywords(&text, max_keywords);

            Ok(OcrResult {
                full_text: text,
                keywords,
            })
        }
    }

    /// Run VNRecognizeTextRequest on a CGImage using Objective-C runtime.
    ///
    /// On ARM64 macOS, `objc_msgSend` uses the standard C calling convention
    /// (register-based), NOT a variadic calling convention. Rust's `extern "C" fn(...)`
    /// variadic declaration causes the compiler to use the wrong ABI (stack-based for
    /// variadic args). We must cast `objc_msgSend` to typed function pointers for every
    /// call that passes arguments beyond (receiver, selector).
    unsafe fn run_vision_ocr(cg_image: *const c_void) -> Result<String, String> {
        use core_foundation::base::TCFType;
        use core_foundation::string::CFString;

        #[link(name = "objc", kind = "dylib")]
        extern "C" {
            fn objc_getClass(name: *const u8) -> *const c_void;
            fn sel_registerName(name: *const u8) -> *const c_void;
        }

        // The raw objc_msgSend symbol — we transmute it for each call site.
        extern "C" {
            fn objc_msgSend();
        }
        let msg_send = objc_msgSend as *const c_void;

        macro_rules! cls {
            ($name:expr) => {
                objc_getClass(concat!($name, "\0").as_ptr())
            };
        }

        macro_rules! sel {
            ($name:expr) => {
                sel_registerName(concat!($name, "\0").as_ptr())
            };
        }

        // Typed function pointer aliases for objc_msgSend
        type MsgSend0 = unsafe extern "C" fn(*const c_void, *const c_void) -> *const c_void;
        type MsgSend1Ptr = unsafe extern "C" fn(*const c_void, *const c_void, *const c_void) -> *const c_void;
        type MsgSend1Int = unsafe extern "C" fn(*const c_void, *const c_void, i64) -> *const c_void;
        type MsgSend2Ptr = unsafe extern "C" fn(*const c_void, *const c_void, *const c_void, *const c_void) -> *const c_void;
        type MsgSend1Usize = unsafe extern "C" fn(*const c_void, *const c_void, usize) -> *const c_void;

        let send0: MsgSend0 = std::mem::transmute(msg_send);
        let send1p: MsgSend1Ptr = std::mem::transmute(msg_send);
        let send1i: MsgSend1Int = std::mem::transmute(msg_send);
        let send2p: MsgSend2Ptr = std::mem::transmute(msg_send);
        let send1u: MsgSend1Usize = std::mem::transmute(msg_send);

        // VNRecognizeTextRequest *request = [[VNRecognizeTextRequest alloc] init];
        let vn_class = cls!("VNRecognizeTextRequest");
        let request = send0(send0(vn_class, sel!("alloc")), sel!("init"));
        if request.is_null() {
            return Err("Failed to create VNRecognizeTextRequest".into());
        }

        // [request setRecognitionLevel:VNRequestTextRecognitionLevelAccurate] (1)
        send1i(request, sel!("setRecognitionLevel:"), 1i64);
        // [request setUsesLanguageCorrection:YES]
        send1i(request, sel!("setUsesLanguageCorrection:"), 1i64);

        // VNImageRequestHandler *handler = [[VNImageRequestHandler alloc] initWithCGImage:cg_image options:nil];
        let handler_class = cls!("VNImageRequestHandler");
        let handler = send2p(
            send0(handler_class, sel!("alloc")),
            sel!("initWithCGImage:options:"),
            cg_image,
            std::ptr::null(),
        );
        if handler.is_null() {
            CFRelease(request);
            return Err("Failed to create VNImageRequestHandler".into());
        }

        // NSArray *requests = @[request];
        let requests = send1p(cls!("NSArray"), sel!("arrayWithObject:"), request);

        // [handler performRequests:requests error:&error];
        let mut error: *const c_void = std::ptr::null();
        type MsgSendPerform = unsafe extern "C" fn(
            *const c_void, *const c_void, *const c_void, *mut *const c_void,
        ) -> *const c_void;
        let send_perform: MsgSendPerform = std::mem::transmute(msg_send);
        let result = send_perform(
            handler,
            sel!("performRequests:error:"),
            requests,
            &mut error,
        );
        let success = !result.is_null() && result as usize != 0;

        if !success || !error.is_null() {
            CFRelease(request);
            CFRelease(handler);
            return Err("Vision OCR request failed".into());
        }

        // NSArray<VNRecognizedTextObservation *> *observations = request.results;
        let observations = send0(request, sel!("results"));

        let mut full_text = String::new();

        if !observations.is_null() {
            let count = send0(observations, sel!("count")) as usize;

            for i in 0..count {
                let observation = send1u(observations, sel!("objectAtIndex:"), i);
                if observation.is_null() {
                    continue;
                }

                // NSArray<VNRecognizedText *> *candidates = [observation topCandidates:1];
                let candidates = send1u(observation, sel!("topCandidates:"), 1usize);
                if candidates.is_null() {
                    continue;
                }

                let candidate_count = send0(candidates, sel!("count")) as usize;
                if candidate_count == 0 {
                    continue;
                }

                let candidate = send1u(candidates, sel!("objectAtIndex:"), 0usize);
                if candidate.is_null() {
                    continue;
                }

                // NSString *text = candidate.string;
                let ns_string = send0(candidate, sel!("string"));
                if ns_string.is_null() {
                    continue;
                }

                // Convert NSString to Rust String via CFString
                let cf_str = CFString::wrap_under_get_rule(ns_string as _);
                let line = cf_str.to_string();
                if !line.is_empty() {
                    full_text.push_str(&line);
                    full_text.push('\n');
                }
            }
        }

        CFRelease(handler);
        CFRelease(request);

        Ok(full_text)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_keywords() {
        let text = "Visual Studio Code main.py dagtech-api src/routes/auth.py def login_user password_hash database connection pool";
        let kw = extract_keywords(text, 10);
        assert!(!kw.is_empty());
        assert!(kw.len() <= 10);
        // Should skip short words and stop words
        assert!(!kw.contains(&"def".to_string()));
        assert!(!kw.contains(&"the".to_string()));
    }

    #[test]
    fn test_extract_keywords_dedup() {
        let text = "Rust rust RUST programming Programming language";
        let kw = extract_keywords(text, 10);
        // "rust" should appear only once (case-insensitive dedup)
        let rust_count = kw.iter().filter(|w| w.to_lowercase() == "rust").count();
        assert_eq!(rust_count, 1);
    }

    #[test]
    fn test_extract_keywords_empty() {
        let kw = extract_keywords("", 10);
        assert!(kw.is_empty());
    }

    #[test]
    fn test_ocr_engine_unavailable_platform() {
        // On non-macOS this should be unavailable
        let engine = OcrEngine::new(5.0, 20);
        if !cfg!(target_os = "macos") {
            assert!(!engine.is_available());
        }
    }

    #[test]
    fn test_ocr_engine_creation() {
        // Just verify the engine can be created without panic
        let engine = OcrEngine::new(5.0, 20);
        // On macOS it should be available
        if cfg!(target_os = "macos") {
            assert!(engine.is_available());
        }
    }
}
