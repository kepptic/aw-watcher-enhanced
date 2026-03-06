//! Cross-platform active window capture.
//!
//! On macOS: Uses Core Graphics (CGWindowList) and Accessibility APIs
//! to get the focused app name and window title. All CF/AX objects are
//! automatically released by Rust's ownership model — no autorelease pools needed.


/// Basic window info.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WindowInfo {
    pub app: String,
    pub title: String,
}

/// Get the currently focused window (app name + title).
///
/// This is the fast path called every 1s heartbeat. On macOS it uses
/// the Accessibility API (AXUIElement) which is lightweight and returns
/// immediately. No CGWindowList calls needed for the fast path.
pub fn get_current_window() -> Option<WindowInfo> {
    #[cfg(target_os = "macos")]
    return macos::get_current_window();

    #[cfg(target_os = "windows")]
    return windows::get_current_window();

    #[cfg(target_os = "linux")]
    return linux::get_current_window();

    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    {
        warn!("Unsupported platform for window capture");
        None
    }
}

// ─── macOS ───────────────────────────────────────────────────────────────────

#[cfg(target_os = "macos")]
mod macos {
    use super::WindowInfo;
    use core_foundation::base::{CFType, TCFType};
    use core_foundation::string::CFString;
    use std::ffi::c_void;

    // Accessibility framework bindings (not in core-graphics crate)
    #[link(name = "ApplicationServices", kind = "framework")]
    extern "C" {
        fn AXUIElementCreateSystemWide() -> *mut c_void;
        fn AXUIElementCopyAttributeValue(
            element: *mut c_void,
            attribute: *const c_void, // CFStringRef
            value: *mut *mut c_void,
        ) -> i32; // AXError
        fn CFRelease(cf: *const c_void);
    }

    // AXError codes
    const AX_ERROR_SUCCESS: i32 = 0;

    /// Get CF string attribute from an AX element. Returns None on failure.
    unsafe fn ax_get_string(element: *mut c_void, attr: &str) -> Option<String> {
        let cf_attr = CFString::new(attr);
        let mut value: *mut c_void = std::ptr::null_mut();
        let err = AXUIElementCopyAttributeValue(
            element,
            cf_attr.as_concrete_TypeRef() as *const c_void,
            &mut value,
        );
        if err != AX_ERROR_SUCCESS || value.is_null() {
            return None;
        }

        // Try to read as CFString
        let cf_type = CFType::wrap_under_create_rule(value as _);
        let type_id = cf_type.type_of();
        if type_id == core_foundation::string::CFString::type_id() {
            let cf_str: CFString = CFString::wrap_under_get_rule(value as _);
            Some(cf_str.to_string())
        } else {
            None
        }
    }

    /// Get a child AX element attribute (e.g., AXFocusedWindow from AXFocusedApplication).
    unsafe fn ax_get_element(element: *mut c_void, attr: &str) -> Option<*mut c_void> {
        let cf_attr = CFString::new(attr);
        let mut value: *mut c_void = std::ptr::null_mut();
        let err = AXUIElementCopyAttributeValue(
            element,
            cf_attr.as_concrete_TypeRef() as *const c_void,
            &mut value,
        );
        if err != AX_ERROR_SUCCESS || value.is_null() {
            return None;
        }
        Some(value)
    }

    pub fn get_current_window() -> Option<WindowInfo> {
        // Try AX API first (gives both app name and window title)
        if let Some(info) = get_via_ax() {
            return Some(info);
        }

        // Fallback to NSWorkspace (always works, but no window title)
        get_via_nsworkspace()
    }

    /// Get window info via Accessibility API (requires permission).
    fn get_via_ax() -> Option<WindowInfo> {
        unsafe {
            let system_wide = AXUIElementCreateSystemWide();
            if system_wide.is_null() {
                return None;
            }

            let focused_app = ax_get_element(system_wide, "AXFocusedApplication");
            CFRelease(system_wide);

            let focused_app = match focused_app {
                Some(app) => app,
                None => return None,
            };

            let app_name = ax_get_string(focused_app, "AXTitle").unwrap_or_default();

            let title = if let Some(focused_window) =
                ax_get_element(focused_app, "AXFocusedWindow")
            {
                let t = ax_get_string(focused_window, "AXTitle").unwrap_or_default();
                CFRelease(focused_window);
                t
            } else {
                String::new()
            };

            CFRelease(focused_app);

            if app_name.is_empty() {
                return None;
            }

            if matches!(
                app_name.as_str(),
                "loginwindow" | "SecurityAgent" | "loginwindow.app"
            ) {
                return None;
            }

            Some(WindowInfo {
                app: app_name,
                title,
            })
        }
    }

    /// Fallback: get frontmost app via NSWorkspace (no Accessibility permission needed).
    fn get_via_nsworkspace() -> Option<WindowInfo> {
        use core_foundation::string::CFString;

        #[link(name = "objc", kind = "dylib")]
        extern "C" {
            fn objc_getClass(name: *const u8) -> *const c_void;
            fn sel_registerName(name: *const u8) -> *const c_void;
        }
        // Use typed fn pointer to avoid ARM64 variadic ABI mismatch
        extern "C" { fn objc_msgSend(); }
        type MsgSend0 = unsafe extern "C" fn(*const c_void, *const c_void) -> *const c_void;
        let send: MsgSend0 = unsafe { std::mem::transmute(objc_msgSend as *const c_void) };

        unsafe {
            let workspace: *const c_void = send(
                objc_getClass(b"NSWorkspace\0".as_ptr()),
                sel_registerName(b"sharedWorkspace\0".as_ptr()),
            );
            if workspace.is_null() {
                return None;
            }

            let app: *const c_void = send(
                workspace,
                sel_registerName(b"frontmostApplication\0".as_ptr()),
            );
            if app.is_null() {
                return None;
            }

            let name_ns: *const c_void = send(
                app,
                sel_registerName(b"localizedName\0".as_ptr()),
            );
            if name_ns.is_null() {
                return None;
            }

            let cf_str = CFString::wrap_under_get_rule(name_ns as _);
            let app_name = cf_str.to_string();

            if app_name.is_empty()
                || matches!(
                    app_name.as_str(),
                    "loginwindow" | "SecurityAgent" | "loginwindow.app"
                )
            {
                return None;
            }

            Some(WindowInfo {
                app: app_name,
                title: String::new(),
            })
        }
    }
}

// ─── Windows ─────────────────────────────────────────────────────────────────

#[cfg(target_os = "windows")]
mod windows {
    use super::WindowInfo;
    use windows::Win32::Foundation::HWND;
    use windows::Win32::System::ProcessStatus::GetModuleFileNameExW;
    use windows::Win32::System::Threading::{
        OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION,
    };
    use windows::Win32::UI::WindowsAndMessaging::{
        GetForegroundWindow, GetWindowTextW, GetWindowThreadProcessId,
    };

    pub fn get_current_window() -> Option<WindowInfo> {
        unsafe {
            let hwnd = GetForegroundWindow();
            if hwnd.0 == 0 {
                return None;
            }

            // Get window title
            let mut title_buf = [0u16; 512];
            let len = GetWindowTextW(hwnd, &mut title_buf);
            let title = String::from_utf16_lossy(&title_buf[..len as usize]);

            // Get process ID
            let mut pid = 0u32;
            GetWindowThreadProcessId(hwnd, Some(&mut pid));

            // Get app name from process
            let app = get_process_name(pid).unwrap_or_else(|| "unknown".to_string());

            Some(WindowInfo { app, title })
        }
    }

    unsafe fn get_process_name(pid: u32) -> Option<String> {
        let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid).ok()?;
        let mut buf = [0u16; 260];
        let len = GetModuleFileNameExW(Some(handle), None, &mut buf);
        if len == 0 {
            return None;
        }
        let full_path = String::from_utf16_lossy(&buf[..len as usize]);
        full_path
            .rsplit('\\')
            .next()
            .map(|s| s.to_string())
    }
}

// ─── Linux ───────────────────────────────────────────────────────────────────

#[cfg(target_os = "linux")]
mod linux {
    use super::WindowInfo;
    use std::process::Command;

    pub fn get_current_window() -> Option<WindowInfo> {
        // Use xdotool as a lightweight approach (works on X11)
        // For Wayland, would need different approach
        let output = Command::new("xdotool")
            .args(["getactivewindow", "getwindowname"])
            .output()
            .ok()?;

        if !output.status.success() {
            return None;
        }

        let title = String::from_utf8_lossy(&output.stdout).trim().to_string();

        // Get window class (app name)
        let class_output = Command::new("xdotool")
            .args(["getactivewindow", "getwindowclassname"])
            .output()
            .ok()?;

        let app = if class_output.status.success() {
            String::from_utf8_lossy(&class_output.stdout)
                .trim()
                .to_string()
        } else {
            "unknown".to_string()
        };

        Some(WindowInfo { app, title })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_get_current_window_returns_some_or_none() {
        // Should not panic regardless of platform
        let result = get_current_window();
        // In test environments (CI, headless), this may return None
        if let Some(info) = result {
            assert!(!info.app.is_empty());
        }
    }

    #[test]
    fn test_window_info_eq() {
        let a = WindowInfo {
            app: "Code".into(),
            title: "main.rs".into(),
        };
        let b = a.clone();
        assert_eq!(a, b);
    }
}
