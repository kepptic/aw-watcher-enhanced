//! Activity categorization based on app name, title, and document context.
//!
//! Maps window events to semantic categories like "coding", "browsing",
//! "communication", etc.

/// Categorize an event based on app name and title.
pub fn categorize(app: &str, title: &str) -> &'static str {
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

    // Browser — subcategorize by title
    if is_browser_app(&app_lower) {
        return categorize_browser_title(&title_lower);
    }

    // Communication
    if is_communication_app(&app_lower) {
        if title_lower.contains("meeting")
            || title_lower.contains("call")
            || title_lower.contains("huddle")
        {
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

fn is_communication_app(app: &str) -> bool {
    app.contains("slack")
        || app.contains("teams")
        || app.contains("discord")
        || app.contains("zoom")
        || app.contains("skype")
        || app.contains("facetime")
        || app.contains("messages")
        || app.contains("telegram")
        || app.contains("signal")
        || app.contains("whatsapp")
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

fn categorize_browser_title(title: &str) -> &'static str {
    // Development
    if title.contains("github")
        || title.contains("gitlab")
        || title.contains("bitbucket")
        || title.contains("stackoverflow")
        || title.contains("stack overflow")
        || title.contains("docs.rs")
        || title.contains("crates.io")
        || title.contains("developer")
        || title.contains("documentation")
        || title.contains("api reference")
    {
        return "coding";
    }

    // Communication
    if title.contains("gmail")
        || title.contains("outlook")
        || title.contains("mail")
        || title.contains("slack")
        || title.contains("discord")
        || title.contains("teams")
    {
        return "communication";
    }

    // Documents
    if title.contains("google docs")
        || title.contains("google sheets")
        || title.contains("google slides")
        || title.contains("notion")
        || title.contains("confluence")
    {
        return "documents";
    }

    // Project management
    if title.contains("jira")
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

    // Meeting
    if title.contains("meet.google")
        || title.contains("zoom")
        || title.contains("teams meeting")
    {
        return "meeting";
    }

    "browsing"
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
    }

    #[test]
    fn test_unknown_app() {
        assert_eq!(categorize("SomeRandomApp", "title"), "other");
    }
}
