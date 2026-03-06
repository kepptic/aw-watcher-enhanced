//! Document context extraction from window titles.
//!
//! Parses window titles to extract filename, project, and document type.
//! Zero-allocation regex-based parsing, compiled once at startup.

/// Parsed document context from a window title.
#[derive(Debug, Clone, Default)]
pub struct DocumentContext {
    pub filename: Option<String>,
    pub project: Option<String>,
    pub doc_type: Option<String>,
    pub extension: Option<String>,
    #[allow(dead_code)]
    pub path: Option<String>,
}

/// Parse document context from app name and window title.
pub fn parse_document_context(app: &str, title: &str) -> Option<DocumentContext> {
    if app.is_empty() || title.is_empty() {
        return None;
    }

    let app_lower = app.to_lowercase();

    // VS Code / Cursor / Windsurf
    if is_vscode_app(&app_lower) {
        return parse_vscode_title(title);
    }

    // JetBrains IDEs
    if is_jetbrains_app(&app_lower) {
        return parse_jetbrains_title(title);
    }

    // Browsers
    if is_browser_app(&app_lower) {
        return Some(DocumentContext {
            doc_type: Some("browser".into()),
            filename: Some(title.to_string()),
            ..Default::default()
        });
    }

    // Terminal apps
    if is_terminal_app(&app_lower) {
        return Some(DocumentContext {
            doc_type: Some("terminal".into()),
            ..Default::default()
        });
    }

    // Generic: try to extract filename from title
    parse_generic_title(title)
}

fn is_vscode_app(app: &str) -> bool {
    matches!(
        app,
        "code" | "visual studio code" | "cursor" | "windsurf" | "code.exe"
    ) || app.contains("visual studio code")
}

fn is_jetbrains_app(app: &str) -> bool {
    app.contains("pycharm")
        || app.contains("intellij")
        || app.contains("idea")
        || app.contains("webstorm")
        || app.contains("phpstorm")
        || app.contains("rider")
        || app.contains("goland")
        || app.contains("clion")
        || app.contains("datagrip")
        || app.contains("rubymine")
        || app.contains("android studio")
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
    )
}

/// Parse VS Code / Cursor title formats:
/// - "filename.py — project-name" (macOS)
/// - "filename.py - project-name - Visual Studio Code" (Windows/Linux)
/// - "filename.py - Visual Studio Code"
fn parse_vscode_title(title: &str) -> Option<DocumentContext> {
    // Split on dash variants surrounded by spaces: " - ", " – ", " — "
    // This preserves hyphens within filenames and project names.
    let parts: Vec<&str> = split_on_title_separators(title);

    if parts.is_empty() {
        return None;
    }

    // Filter out "Visual Studio Code" suffix
    let meaningful: Vec<&str> = parts
        .iter()
        .filter(|p| !p.contains("Visual Studio Code"))
        .copied()
        .collect();

    let (filename, project) = match meaningful.len() {
        0 => return None,
        1 => (Some(meaningful[0].to_string()), None),
        _ => (
            Some(meaningful[0].to_string()),
            Some(meaningful[1].to_string()),
        ),
    };

    // Check if the "filename" is actually a version number (e.g., "2.1.69")
    // or other non-file string. Real filenames have alphabetic chars before the dot.
    let filename = filename.filter(|f| {
        // Must contain at least one alphabetic character before the last dot
        if let Some(dot_pos) = f.rfind('.') {
            f[..dot_pos].chars().any(|c| c.is_alphabetic())
        } else {
            true // no dot, keep it (e.g., "Untitled-1")
        }
    });

    let extension = filename
        .as_ref()
        .and_then(|f| f.rsplit('.').next().map(|e| e.to_lowercase()))
        .filter(|e| e.len() <= 10 && e != filename.as_deref().unwrap_or(""));

    Some(DocumentContext {
        filename,
        project,
        doc_type: Some("code".into()),
        extension,
        path: None,
    })
}

/// Split a window title on separator characters surrounded by spaces.
/// Handles " - ", " – ", " — " (ASCII dash, en dash, em dash).
fn split_on_title_separators(title: &str) -> Vec<&str> {
    // Split on " — " (em dash), " – " (en dash), " - " (hyphen-minus)
    // Use the longest match first to avoid partial matches
    let mut result = Vec::new();
    let mut remaining = title;

    loop {
        // Find the earliest separator
        let separators = [" — ", " – ", " - "];
        let mut earliest: Option<(usize, usize)> = None; // (pos, sep_len)

        for sep in &separators {
            if let Some(pos) = remaining.find(sep) {
                if earliest.is_none() || pos < earliest.unwrap().0 {
                    earliest = Some((pos, sep.len()));
                }
            }
        }

        match earliest {
            Some((pos, sep_len)) => {
                let part = remaining[..pos].trim();
                if !part.is_empty() {
                    result.push(part);
                }
                remaining = &remaining[pos + sep_len..];
            }
            None => {
                let part = remaining.trim();
                if !part.is_empty() {
                    result.push(part);
                }
                break;
            }
        }
    }

    result
}

/// Parse JetBrains title: "project – file.py [path]"
fn parse_jetbrains_title(title: &str) -> Option<DocumentContext> {
    let parts = split_on_title_separators(title);

    if parts.is_empty() {
        return None;
    }

    let (project, filename) = if parts.len() >= 2 {
        // "project – file.py [path]"
        let file_part = parts[1];
        let file = if let Some(bracket_pos) = file_part.find('[') {
            file_part[..bracket_pos].trim()
        } else {
            file_part
        };
        (Some(parts[0].to_string()), Some(file.to_string()))
    } else {
        (Some(parts[0].to_string()), None)
    };

    let extension = filename
        .as_ref()
        .and_then(|f| f.rsplit('.').next().map(|e| e.to_lowercase()))
        .filter(|e| e.len() <= 10);

    Some(DocumentContext {
        filename,
        project,
        doc_type: Some("code".into()),
        extension,
        path: None,
    })
}

/// Try to extract filename from generic window title.
fn parse_generic_title(title: &str) -> Option<DocumentContext> {
    // Look for file-like patterns (something.ext)
    let parts = split_on_title_separators(title);

    if parts.is_empty() {
        return None;
    }

    let first = parts[0];
    if first.contains('.') && first.len() < 200 {
        let extension = first
            .rsplit('.')
            .next()
            .map(|e| e.to_lowercase())
            .filter(|e| e.len() <= 10 && e.chars().all(|c| c.is_alphanumeric()));

        return Some(DocumentContext {
            filename: Some(first.to_string()),
            project: parts.get(1).map(|s| s.to_string()),
            doc_type: extension.as_ref().map(|e| classify_extension(e)),
            extension,
            path: None,
        });
    }

    None
}

/// Classify a file extension into a document type.
fn classify_extension(ext: &str) -> String {
    match ext {
        "py" | "rs" | "go" | "java" | "js" | "ts" | "tsx" | "jsx" | "rb" | "php" | "c"
        | "cpp" | "h" | "cs" | "swift" | "kt" | "scala" | "sh" | "bash" | "zsh" => {
            "code".to_string()
        }
        "md" | "txt" | "rst" | "tex" => "text".to_string(),
        "doc" | "docx" | "odt" | "rtf" => "document".to_string(),
        "xls" | "xlsx" | "csv" => "spreadsheet".to_string(),
        "ppt" | "pptx" => "presentation".to_string(),
        "pdf" => "pdf".to_string(),
        "html" | "css" | "scss" | "less" | "vue" | "svelte" => "web".to_string(),
        "json" | "yaml" | "yml" | "toml" | "ini" | "xml" | "env" => "config".to_string(),
        "sql" => "database".to_string(),
        "ipynb" => "notebook".to_string(),
        _ => "other".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vscode_macos_title() {
        let ctx = parse_document_context("Code", "main.py — aw-watcher-enhanced").unwrap();
        assert_eq!(ctx.filename.as_deref(), Some("main.py"));
        assert_eq!(ctx.project.as_deref(), Some("aw-watcher-enhanced"));
        assert_eq!(ctx.doc_type.as_deref(), Some("code"));
        assert_eq!(ctx.extension.as_deref(), Some("py"));
    }

    #[test]
    fn test_vscode_windows_title() {
        let ctx = parse_document_context(
            "Code",
            "main.py - aw-watcher-enhanced - Visual Studio Code",
        )
        .unwrap();
        assert_eq!(ctx.filename.as_deref(), Some("main.py"));
        assert_eq!(ctx.project.as_deref(), Some("aw-watcher-enhanced"));
    }

    #[test]
    fn test_vscode_no_project() {
        let ctx =
            parse_document_context("Code", "Untitled-1 - Visual Studio Code").unwrap();
        assert_eq!(ctx.filename.as_deref(), Some("Untitled-1"));
        assert_eq!(ctx.project, None);
    }

    #[test]
    fn test_jetbrains_title() {
        let ctx =
            parse_document_context("PyCharm", "myproject – main.py [src/main.py]").unwrap();
        assert_eq!(ctx.project.as_deref(), Some("myproject"));
        assert_eq!(ctx.filename.as_deref(), Some("main.py"));
    }

    #[test]
    fn test_browser_title() {
        let ctx = parse_document_context("Google Chrome", "GitHub - rust-lang/rust").unwrap();
        assert_eq!(ctx.doc_type.as_deref(), Some("browser"));
    }

    #[test]
    fn test_terminal() {
        let ctx = parse_document_context("iTerm2", "~/projects — zsh").unwrap();
        assert_eq!(ctx.doc_type.as_deref(), Some("terminal"));
    }

    #[test]
    fn test_empty_inputs() {
        assert!(parse_document_context("", "title").is_none());
        assert!(parse_document_context("app", "").is_none());
    }

    #[test]
    fn test_cursor_app() {
        let ctx = parse_document_context("Cursor", "lib.rs — my-project").unwrap();
        assert_eq!(ctx.filename.as_deref(), Some("lib.rs"));
        assert_eq!(ctx.doc_type.as_deref(), Some("code"));
    }
}
