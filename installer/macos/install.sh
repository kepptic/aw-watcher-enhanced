#!/bin/bash
# ============================================================================
# ActivityWatch Enhanced Watcher - macOS Installer (Rust)
# ============================================================================
# Compiles the Rust watcher and installs the binary to /usr/local/bin.
# aw-qt discovers any `aw-*` executable on PATH at startup.
#
# Usage:
#   ./install.sh              # Build + install binary
#   ./install.sh --service    # Also install launchd service
#   ./install.sh --prebuilt   # Skip build, use existing binary
#   ./install.sh --help       # Show help
# ============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
RUST_DIR="$PROJECT_DIR/rust-watcher"
BINARY_NAME="aw-watcher-enhanced"
INSTALL_DIR="/usr/local/bin"
PLIST_NAME="com.kepptic.aw-watcher-enhanced"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
LOG_DIR="$HOME/Library/Logs/activitywatch"
CONFIG_DIR="$HOME/Library/Application Support/activitywatch/aw-watcher-enhanced"

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

show_header() {
    echo ""
    echo "============================================================"
    echo "   ActivityWatch Enhanced Watcher v1.0.0 - macOS Installer"
    echo "============================================================"
    echo ""
}

check_requirements() {
    info "Checking requirements..."

    # Check Rust toolchain
    if ! command -v cargo &> /dev/null; then
        error "Rust toolchain not found."
        echo "Install with: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
        exit 1
    fi
    RUST_VERSION=$(rustc --version | cut -d' ' -f2)
    success "Rust $RUST_VERSION found"

    # Check macOS version (need 12+ for ScreenCaptureKit)
    MACOS_VERSION=$(sw_vers -productVersion)
    success "macOS $MACOS_VERSION"

    # Check if ActivityWatch is running
    if curl -s http://localhost:5600/api/0/info &> /dev/null; then
        success "ActivityWatch server is running"
    else
        warn "ActivityWatch server is not running."
        echo "    Make sure to start ActivityWatch before using this watcher."
    fi

    echo ""
}

request_permissions() {
    info "Checking permissions..."
    echo ""
    echo "This app requires two macOS permissions:"
    echo ""
    echo "  1. Accessibility — for window title capture"
    echo "     System Settings > Privacy & Security > Accessibility"
    echo ""
    echo "  2. Screen Recording — for OCR screen capture"
    echo "     System Settings > Privacy & Security > Screen Recording"
    echo ""
    echo "  Add your terminal app (Terminal.app, iTerm, etc.) to both lists."
    echo "  If using launchd service, also add the binary itself."
    echo ""

    # Trigger accessibility permission dialog
    osascript -e 'tell application "System Events" to get name of first process' &> /dev/null || true

    read -p "Press Enter after granting permissions (or 's' to skip): " response
    if [[ "$response" != "s" ]]; then
        success "Permissions acknowledged"
    fi
    echo ""
}

build_binary() {
    info "Building aw-watcher-enhanced (release mode)..."
    echo "    This may take a few minutes on first build."
    echo ""

    cd "$RUST_DIR"
    cargo build --release 2>&1

    if [[ ! -f "$RUST_DIR/target/release/$BINARY_NAME" ]]; then
        error "Build failed — binary not found."
        exit 1
    fi

    BINARY_SIZE=$(du -h "$RUST_DIR/target/release/$BINARY_NAME" | cut -f1 | xargs)
    success "Build complete: $BINARY_SIZE"
    echo ""
}

install_binary() {
    info "Installing binary to $INSTALL_DIR..."

    # Create dir if needed
    if [[ ! -d "$INSTALL_DIR" ]]; then
        sudo mkdir -p "$INSTALL_DIR"
    fi

    # Stop existing instance if running
    if pgrep -x "$BINARY_NAME" > /dev/null 2>&1; then
        warn "Stopping running instance..."
        pkill -x "$BINARY_NAME" 2>/dev/null || true
        sleep 1
    fi

    sudo cp "$RUST_DIR/target/release/$BINARY_NAME" "$INSTALL_DIR/$BINARY_NAME"
    sudo chmod +x "$INSTALL_DIR/$BINARY_NAME"

    if command -v "$BINARY_NAME" &> /dev/null; then
        EXEC_PATH=$(command -v "$BINARY_NAME")
        success "Installed: $EXEC_PATH"
    else
        warn "Binary installed but not found on PATH."
        echo "    Add $INSTALL_DIR to your PATH."
    fi
    echo ""
}

create_config() {
    info "Setting up configuration..."

    mkdir -p "$CONFIG_DIR"

    if [[ ! -f "$CONFIG_DIR/config.toml" ]]; then
        cat > "$CONFIG_DIR/config.toml" << 'TOML'
# ActivityWatch Enhanced Watcher Configuration

[watcher]
poll_time = 5.0        # Enrichment capture frequency (seconds)
heartbeat_time = 1.0   # Heartbeat interval (seconds)

[ocr]
enabled = true
min_interval = 10.0    # Minimum seconds between OCR captures
max_keywords = 20

[llm]
enabled = true
model = "gemma3:1b"    # Ollama model for OCR summarization
timeout = 10.0

[privacy]
exclude_apps = ["1Password", "Keychain Access"]
exclude_titles = [".*[Pp]assword.*", ".*[Pp]rivate.*"]
TOML
        success "Created config: $CONFIG_DIR/config.toml"
    else
        info "Config already exists: $CONFIG_DIR/config.toml"
    fi
    echo ""
}

register_with_awqt() {
    info "Registering with ActivityWatch..."

    AW_QT_CONFIG="$HOME/Library/Application Support/activitywatch/aw-qt/aw-qt.toml"

    if [[ -f "$AW_QT_CONFIG" ]]; then
        if grep -q "aw-watcher-enhanced" "$AW_QT_CONFIG"; then
            info "Already registered in aw-qt.toml"
        else
            info "Adding aw-watcher-enhanced to aw-qt autostart..."
            # Read existing config and append our module
            if grep -q "autostart_modules" "$AW_QT_CONFIG"; then
                # Add to existing autostart_modules list
                sed -i '' 's/autostart_modules = \[/autostart_modules = ["aw-watcher-enhanced", /' "$AW_QT_CONFIG"
                success "Updated aw-qt.toml"
            else
                echo '' >> "$AW_QT_CONFIG"
                echo '[aw-qt]' >> "$AW_QT_CONFIG"
                echo 'autostart_modules = ["aw-server", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]' >> "$AW_QT_CONFIG"
                success "Appended to aw-qt.toml"
            fi
        fi
    else
        mkdir -p "$(dirname "$AW_QT_CONFIG")"
        cat > "$AW_QT_CONFIG" << 'TOML'
[aw-qt]
autostart_modules = ["aw-server", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]

[aw-qt-testing]
autostart_modules = ["aw-server", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]
TOML
        success "Created aw-qt.toml"
    fi

    success "Registered with ActivityWatch (restart aw-qt to activate)"
    echo ""
}

create_launchd_plist() {
    info "Creating launchd service..."

    mkdir -p "$HOME/Library/LaunchAgents"
    mkdir -p "$LOG_DIR"

    EXEC_PATH="$INSTALL_DIR/$BINARY_NAME"

    cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${EXEC_PATH}</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
        <key>Crashed</key>
        <true/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>30</integer>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/aw-watcher-enhanced.log</string>

    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/aw-watcher-enhanced.error.log</string>

    <key>ProcessType</key>
    <string>Background</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>RUST_LOG</key>
        <string>info</string>
    </dict>
</dict>
</plist>
EOF

    success "Created launchd plist: $PLIST_PATH"
}

load_service() {
    info "Loading launchd service..."

    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    launchctl load "$PLIST_PATH"

    success "Service loaded"

    sleep 2
    if launchctl list | grep -q "$PLIST_NAME"; then
        success "Service is running"
    else
        warn "Service may not have started. Check logs:"
        echo "    tail -f $LOG_DIR/aw-watcher-enhanced.log"
    fi
}

create_uninstall_script() {
    UNINSTALL_SCRIPT="$SCRIPT_DIR/uninstall.sh"
    cat > "$UNINSTALL_SCRIPT" << 'EOF'
#!/bin/bash
# Uninstall aw-watcher-enhanced from macOS

PLIST_NAME="com.kepptic.aw-watcher-enhanced"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
BINARY="/usr/local/bin/aw-watcher-enhanced"

echo "Uninstalling ActivityWatch Enhanced Watcher..."

# Stop running instance
if pgrep -x "aw-watcher-enhanced" > /dev/null 2>&1; then
    echo "Stopping running instance..."
    pkill -x "aw-watcher-enhanced" 2>/dev/null || true
fi

# Stop and remove launchd service
if [[ -f "$PLIST_PATH" ]]; then
    echo "Removing launchd service..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm "$PLIST_PATH"
    echo "Service removed."
fi

# Remove binary
if [[ -f "$BINARY" ]]; then
    echo "Removing binary..."
    sudo rm "$BINARY"
    echo "Binary removed."
fi

# Ask about config removal
read -p "Remove configuration files? (y/n): " remove_config
if [[ "$remove_config" == "y" ]]; then
    rm -rf "$HOME/Library/Application Support/activitywatch/aw-watcher-enhanced"
    echo "Configuration removed."
fi

echo ""
echo "Uninstallation complete."
echo "Note: ActivityWatch data (events) are stored separately and not removed."
echo "You may want to remove aw-watcher-enhanced from aw-qt.toml:"
echo "  $HOME/Library/Application Support/activitywatch/aw-qt/aw-qt.toml"
EOF
    chmod +x "$UNINSTALL_SCRIPT"
}

show_completion() {
    echo ""
    echo "============================================================"
    echo "   Installation Complete!"
    echo "============================================================"
    echo ""
    echo "The Rust binary is installed at: $INSTALL_DIR/$BINARY_NAME"
    echo "aw-qt discovers it on PATH automatically."
    echo ""
    echo "Usage:"
    echo "  Run manually:     aw-watcher-enhanced"
    echo "  With verbose:     RUST_LOG=debug aw-watcher-enhanced"
    echo "  Test mode:        aw-watcher-enhanced --testing"
    echo ""

    if [[ "$INSTALL_SERVICE" == "true" ]]; then
        echo "Service commands:"
        echo "  Status:  launchctl list | grep aw-watcher"
        echo "  Stop:    launchctl unload $PLIST_PATH"
        echo "  Start:   launchctl load $PLIST_PATH"
        echo "  Logs:    tail -f $LOG_DIR/aw-watcher-enhanced.log"
        echo ""
    fi

    echo "Configuration:"
    echo "  $CONFIG_DIR/config.toml"
    echo ""
    echo "Restart ActivityWatch to activate the watcher."
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────

main() {
    show_header

    INSTALL_SERVICE=false
    SKIP_BUILD=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --service|-s)
                INSTALL_SERVICE=true
                shift
                ;;
            --prebuilt)
                SKIP_BUILD=true
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [options]"
                echo ""
                echo "Options:"
                echo "  --service, -s    Also install as launchd service (auto-start)"
                echo "  --prebuilt       Skip compilation, use existing release binary"
                echo "  --help, -h       Show this help"
                echo ""
                echo "Requires: Rust toolchain (rustup.rs), macOS 12+"
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    check_requirements
    request_permissions

    if [[ "$SKIP_BUILD" == "false" ]]; then
        build_binary
    else
        if [[ ! -f "$RUST_DIR/target/release/$BINARY_NAME" ]]; then
            error "No prebuilt binary found. Run without --prebuilt to compile."
            exit 1
        fi
        info "Using prebuilt binary"
    fi

    install_binary
    create_config
    register_with_awqt
    create_uninstall_script

    if [[ "$INSTALL_SERVICE" == "true" ]]; then
        create_launchd_plist
        load_service
    fi

    show_completion
}

main "$@"
