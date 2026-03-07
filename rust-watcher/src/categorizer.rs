//! Activity categorization based on app name, title, and document context.
//!
//! Maps window events to semantic categories like "coding", "browsing",
//! "communication", etc.

/// Categorize an event based on app name, title, and optionally URL/domain.
pub fn categorize(app: &str, title: &str) -> &'static str {
    categorize_with_url(app, title, "", "")
}

/// Categorize with URL/domain context for more specific browser categories.
pub fn categorize_with_url(app: &str, title: &str, url: &str, domain: &str) -> &'static str {
    let app_lower = app.to_lowercase();
    let title_lower = title.to_lowercase();

    // IDE / Coding
    if is_coding_app(&app_lower) {
        return "coding";
    }

    // Terminal
    if is_terminal_app(&app_lower) {
        if title_lower.contains("docker")
            || title_lower.contains("kubectl")
            || title_lower.contains("terraform")
        {
            return "devops";
        }
        return "terminal";
    }

    // Remote Desktop — detect before browser since RDP apps aren't browsers
    if is_remote_desktop_app(&app_lower) {
        return "remote-desktop";
    }

    // Browser — subcategorize by title, URL, and domain
    if is_browser_app(&app_lower) {
        return categorize_browser(&title_lower, url, domain);
    }

    // Communication / Meeting
    if is_communication_app(&app_lower) {
        if is_meeting_context(&app_lower, &title_lower) {
            return "meeting";
        }
        return "communication";
    }

    // Design
    if is_design_app(&app_lower) {
        return "design";
    }

    // Documents / Office
    if is_document_app(&app_lower) {
        return "documents";
    }

    // Media
    if is_media_app(&app_lower) {
        return "media";
    }

    // System
    if is_system_app(&app_lower) {
        return "system";
    }

    "other"
}

fn is_coding_app(app: &str) -> bool {
    app.contains("code")
        || app.contains("cursor")
        || app.contains("windsurf")
        || app.contains("pycharm")
        || app.contains("intellij")
        || app.contains("idea")
        || app.contains("webstorm")
        || app.contains("vim")
        || app.contains("nvim")
        || app.contains("emacs")
        || app.contains("sublime")
        || app.contains("atom")
        || app.contains("android studio")
        || app.contains("xcode")
}

fn is_terminal_app(app: &str) -> bool {
    matches!(
        app,
        "terminal"
            | "iterm2"
            | "iterm"
            | "alacritty"
            | "kitty"
            | "wezterm"
            | "warp"
            | "hyper"
            | "konsole"
            | "gnome-terminal"
            | "cmd.exe"
            | "powershell"
            | "windowsterminal"
    )
}

fn is_browser_app(app: &str) -> bool {
    matches!(
        app,
        "google chrome"
            | "chrome"
            | "firefox"
            | "safari"
            | "microsoft edge"
            | "edge"
            | "brave browser"
            | "brave"
            | "arc"
            | "opera"
            | "vivaldi"
            | "chromium"
            | "orion"
            | "zen browser"
            | "zen"
    )
}

fn is_remote_desktop_app(app: &str) -> bool {
    app.contains("remote desktop")
        || app.contains("microsoft remote")
        || app.contains("windows app")
        || app.contains("rd client")
        || app.contains("mstsc")
        || app.contains("citrix")
        || app.contains("citrix workspace")
        || app.contains("vmware horizon")
        || app.contains("parallels")
        || app.contains("anydesk")
        || app.contains("teamviewer")
        || app.contains("rustdesk")
        || app.contains("parsec")
        || app.contains("splashtop")
        || app.contains("connectwise control")
        || app.contains("screenconnect")
        || app.contains("datto rmm")
}

fn is_communication_app(app: &str) -> bool {
    app.contains("slack")
        || app.contains("teams")
        || app.contains("discord")
        || app.contains("zoom")
        || app.contains("8x8")
        || app.contains("virtual office")
        || app.contains("skype")
        || app.contains("facetime")
        || app.contains("messages")
        || app.contains("telegram")
        || app.contains("signal")
        || app.contains("whatsapp")
        || app.contains("webex")
        || app.contains("ringcentral")
        || app.contains("goto")
}

/// Detect if a communication app is in a meeting/call context.
fn is_meeting_context(app: &str, title: &str) -> bool {
    // Zoom: "Zoom Meeting" in title when in a call
    if app.contains("zoom") {
        return title.contains("meeting")
            || title.contains("zoom meeting")
            || title.contains("webinar");
    }
    // Teams: various meeting indicators
    if app.contains("teams") {
        return title.contains("meeting")
            || title.contains("call")
            || title.contains("| meeting");
    }
    // 8x8: meeting/call context
    if app.contains("8x8") || app.contains("virtual office") {
        return title.contains("meeting")
            || title.contains("call")
            || title.contains("room");
    }
    // Generic
    title.contains("meeting")
        || title.contains("call")
        || title.contains("huddle")
}

fn is_design_app(app: &str) -> bool {
    app.contains("figma")
        || app.contains("sketch")
        || app.contains("photoshop")
        || app.contains("illustrator")
        || app.contains("canva")
        || app.contains("gimp")
        || app.contains("inkscape")
}

fn is_document_app(app: &str) -> bool {
    app.contains("word")
        || app.contains("excel")
        || app.contains("powerpoint")
        || app.contains("pages")
        || app.contains("numbers")
        || app.contains("keynote")
        || app.contains("notion")
        || app.contains("obsidian")
        || app.contains("evernote")
        || app.contains("google docs")
        || app.contains("libreoffice")
        || app.contains("preview")
}

fn is_media_app(app: &str) -> bool {
    app.contains("spotify")
        || app.contains("music")
        || app.contains("vlc")
        || app.contains("youtube")
        || app.contains("netflix")
        || app.contains("quicktime")
        || app.contains("mpv")
}

fn is_system_app(app: &str) -> bool {
    matches!(
        app,
        "finder"
            | "explorer"
            | "system preferences"
            | "system settings"
            | "activity monitor"
            | "task manager"
    )
}

fn categorize_browser(title: &str, url: &str, domain: &str) -> &'static str {
    let url_lower = url.to_lowercase();
    let domain_lower = domain.to_lowercase();

    // IT Management / RMM / PSA tools
    if domain_lower.contains("datto.com")
        || domain_lower.contains("rmm.") || domain_lower.contains(".rmm")
        || domain_lower.contains("connectwise")
        || domain_lower.contains("ninjaone") || domain_lower.contains("ninjarmm")
        || domain_lower.contains("atera.com")
        || domain_lower.contains("syncro.com")
        || domain_lower.contains("autotask")
        || domain_lower.contains("halo") && (domain_lower.contains("psa") || domain_lower.contains("itsm"))
        || title.contains("datto") || title.contains("rmm")
        || title.contains("connectwise")
        || title.contains("autotask")
    {
        return "it-management";
    }

    // Cloud / Infrastructure
    if domain_lower.contains("portal.azure.com")
        || domain_lower.contains("console.aws")
        || domain_lower.contains("console.cloud.google")
        || domain_lower.contains("console.firebase")
        || domain_lower.contains("vercel.com")
        || domain_lower.contains("netlify.com")
        || domain_lower.contains("heroku.com")
        || domain_lower.contains("cloudflare.com")
        || domain_lower.contains("dev.azure.com")
        || title.contains("azure portal")
        || title.contains("aws console")
    {
        return "cloud-infra";
    }

    // Microsoft 365 / Admin
    if domain_lower.contains("admin.microsoft.com")
        || domain_lower.contains("entra.microsoft.com")
        || domain_lower.contains("intune.microsoft.com")
        || domain_lower.contains("security.microsoft.com")
        || domain_lower.contains("compliance.microsoft.com")
        || domain_lower.contains("exchange.microsoft.com")
        || domain_lower.contains("admin.exchange")
        || url_lower.contains("admin.teams.microsoft")
    {
        return "it-admin";
    }

    // Development
    if domain_lower.contains("github.com")
        || domain_lower.contains("gitlab.com")
        || domain_lower.contains("bitbucket.org")
        || domain_lower.contains("stackoverflow.com")
        || domain_lower.contains("docs.rs")
        || domain_lower.contains("crates.io")
        || domain_lower.contains("npmjs.com")
        || domain_lower.contains("pypi.org")
        || title.contains("github")
        || title.contains("gitlab")
        || title.contains("bitbucket")
        || title.contains("stackoverflow")
        || title.contains("stack overflow")
        || title.contains("developer")
        || title.contains("documentation")
        || title.contains("api reference")
    {
        return "coding";
    }

    // Communication
    if domain_lower.contains("mail.google.com")
        || domain_lower.contains("outlook.live.com")
        || domain_lower.contains("outlook.office")
        || title.contains("gmail")
        || title.contains("outlook")
        || title.contains("mail")
        || title.contains("slack")
        || title.contains("discord")
        || title.contains("teams")
    {
        return "communication";
    }

    // Documents
    if domain_lower.contains("docs.google.com")
        || domain_lower.contains("sheets.google.com")
        || domain_lower.contains("slides.google.com")
        || domain_lower.contains("notion.so")
        || domain_lower.contains("confluence")
        || title.contains("google docs")
        || title.contains("google sheets")
        || title.contains("google slides")
        || title.contains("notion")
        || title.contains("confluence")
    {
        return "documents";
    }

    // Project management
    if domain_lower.contains("jira")
        || domain_lower.contains("linear.app")
        || domain_lower.contains("asana.com")
        || domain_lower.contains("trello.com")
        || domain_lower.contains("monday.com")
        || title.contains("jira")
        || title.contains("linear")
        || title.contains("asana")
        || title.contains("trello")
        || title.contains("monday")
    {
        return "project-management";
    }

    // Social / News
    if title.contains("twitter")
        || title.contains("reddit")
        || title.contains("hacker news")
        || title.contains("linkedin")
        || title.contains("facebook")
    {
        return "social";
    }

    // Meeting (browser-based)
    if domain_lower.contains("meet.google.com")
        || domain_lower.contains("zoom.us")
        || domain_lower.contains("teams.microsoft.com") && title.contains("meeting")
        || domain_lower.contains("8x8.vc")
        || domain_lower.contains("jitsi")
        || title.contains("zoom meeting")
        || title.contains("teams meeting")
        || title.contains("google meet")
    {
        return "meeting";
    }

    // Communication (browser-based) — 8x8, Teams chat, etc.
    if domain_lower.contains("teams.microsoft.com")
        || domain_lower.contains("8x8.com")
        || domain_lower.contains("app.8x8.com")
        || domain_lower.contains("webex.com")
        || domain_lower.contains("ringcentral.com")
    {
        return "communication";
    }

    // Remote desktop (browser-based)
    if domain_lower.contains("remotedesktop.google.com")
        || domain_lower.contains("gotomypc")
        || domain_lower.contains("screenconnect")
        || domain_lower.contains("connectwise.com") && url_lower.contains("control")
    {
        return "remote-desktop";
    }

    "browsing"
}

/// Extract the remote host name from a Remote Desktop window title.
/// Common patterns: "DC01 - Remote Desktop Connection", "PC01 - Windows App", "user@host"
pub fn extract_remote_host(app: &str, title: &str) -> Option<String> {
    let app_lower = app.to_lowercase();
    if !is_remote_desktop_app(&app_lower) {
        return None;
    }
    let title_clean = title.trim();
    // "HOSTNAME - Remote Desktop" / "HOSTNAME - Windows App" / "HOSTNAME - Citrix"
    if let Some(idx) = title_clean.find(" - ") {
        let host = title_clean[..idx].trim();
        if !host.is_empty() && host.len() < 64 {
            return Some(host.to_string());
        }
    }
    // "user@hostname" pattern (SSH-like)
    if let Some(idx) = title_clean.find('@') {
        let host = title_clean[idx + 1..].split_whitespace().next().unwrap_or("");
        if !host.is_empty() {
            return Some(host.to_string());
        }
    }
    None
}

/// Extract client/tenant name from known IT management tool URLs.
/// Returns (client_name, tool_name).
pub fn extract_it_client(url: &str, domain: &str, title: &str) -> Option<(String, &'static str)> {
    let domain_lower = domain.to_lowercase();
    let title_lower = title.to_lowercase();

    // Datto RMM: URL pattern https://*.rmm.datto.com/device/... or /site/...
    // Title pattern: "DeviceName - Datto RMM" or "SiteName - Datto RMM"
    // The site breadcrumb shows: "Sites / SITENAME / DEVICENAME"
    if domain_lower.contains("rmm.datto.com") {
        // Try to extract site from URL path: /site/<id>/<sitename> or /device/<id>/<name>
        if let Some(client) = extract_datto_rmm_client(title, url) {
            return Some((client, "datto-rmm"));
        }
    }

    // ConnectWise Manage/Automate
    if domain_lower.contains("connectwise") {
        if let Some(name) = extract_before_separator(&title_lower, " - connectwise") {
            return Some((name, "connectwise"));
        }
    }

    // Autotask / Datto PSA
    if domain_lower.contains("autotask") || domain_lower.contains("psa.datto.com") {
        if let Some(name) = extract_before_separator(&title_lower, " - autotask")
            .or_else(|| extract_before_separator(&title_lower, " - datto"))
        {
            return Some((name, "datto-psa"));
        }
    }

    // NinjaOne / NinjaRMM
    if domain_lower.contains("ninja") {
        if let Some(name) = extract_before_separator(&title_lower, " - ninja") {
            return Some((name, "ninjaone"));
        }
    }

    None
}

fn extract_datto_rmm_client(title: &str, url: &str) -> Option<String> {
    // Title format: "DEVICENAME - Datto RMM" — extract the part before " - Datto"
    let title_clean = title.trim();
    if let Some(idx) = title_clean.find(" - Datto") {
        let name = title_clean[..idx].trim();
        if !name.is_empty() {
            return Some(name.to_string());
        }
    }

    // Fallback: extract from URL path segments
    // e.g., /device/7832893/dc01 → "dc01"
    if let Some(path_start) = url.find("rmm.datto.com") {
        let path = &url[path_start + 13..]; // after "rmm.datto.com"
        let segments: Vec<&str> = path.split('/').filter(|s| !s.is_empty()).collect();
        // /device/<id>/<name> or /site/<id>/<name>
        if segments.len() >= 3 {
            let name = segments[2];
            if !name.is_empty() && name.chars().any(|c| c.is_alphabetic()) {
                return Some(name.to_string());
            }
        }
    }

    None
}

fn extract_before_separator(text: &str, separator: &str) -> Option<String> {
    if let Some(idx) = text.find(separator) {
        let name = text[..idx].trim();
        if !name.is_empty() {
            return Some(name.to_string());
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_coding_apps() {
        assert_eq!(categorize("Code", "main.rs"), "coding");
        assert_eq!(categorize("Cursor", "lib.rs"), "coding");
        assert_eq!(categorize("PyCharm", "app.py"), "coding");
    }

    #[test]
    fn test_terminal() {
        assert_eq!(categorize("iTerm2", "~/projects"), "terminal");
        assert_eq!(categorize("Alacritty", "docker compose up"), "devops");
    }

    #[test]
    fn test_browser_subcategories() {
        assert_eq!(
            categorize("Google Chrome", "rust-lang/rust - GitHub"),
            "coding"
        );
        assert_eq!(
            categorize("Firefox", "Gmail - Inbox"),
            "communication"
        );
        assert_eq!(
            categorize("Safari", "The Verge - News"),
            "browsing"
        );
    }

    #[test]
    fn test_communication() {
        assert_eq!(categorize("Slack", "general"), "communication");
        assert_eq!(categorize("Slack", "Huddle with team"), "meeting");
        assert_eq!(categorize("8x8 Work", "Contacts"), "communication");
        assert_eq!(categorize("8x8 Work", "Active Call - John"), "meeting");
        assert_eq!(categorize("8x8 Work", "Meeting Room"), "meeting");
    }

    #[test]
    fn test_meeting_detection() {
        assert_eq!(categorize("zoom.us", "Zoom Meeting"), "meeting");
        assert_eq!(categorize("Microsoft Teams", "Team call with dev"), "meeting");
        assert_eq!(categorize("Microsoft Teams", "#general"), "communication");
    }

    #[test]
    fn test_remote_desktop() {
        assert_eq!(categorize("Microsoft Remote Desktop", "DC01 - RDP"), "remote-desktop");
        assert_eq!(categorize("Windows App", "SERVER01"), "remote-desktop");
        assert_eq!(categorize("Citrix Workspace", "VDI Session"), "remote-desktop");
        assert_eq!(categorize("AnyDesk", "123456"), "remote-desktop");
        assert_eq!(categorize("ConnectWise Control", "Client PC"), "remote-desktop");
    }

    #[test]
    fn test_remote_host_extraction() {
        assert_eq!(
            extract_remote_host("Microsoft Remote Desktop", "DC01 - Remote Desktop Connection"),
            Some("DC01".into())
        );
        assert_eq!(
            extract_remote_host("Windows App", "SERVER01 - Windows App"),
            Some("SERVER01".into())
        );
        assert_eq!(
            extract_remote_host("Google Chrome", "some page"),
            None
        );
    }

    #[test]
    fn test_unknown_app() {
        assert_eq!(categorize("SomeRandomApp", "title"), "other");
    }
}
