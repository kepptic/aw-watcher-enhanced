#!/bin/bash
# ============================================================================
# ActivityWatch Enhanced Watcher - macOS Installer
# ============================================================================
# Installs aw-watcher-enhanced via pip and registers it with aw-qt.
#
# How it works:
#   1. pip install creates an `aw-watcher-enhanced` executable on PATH
#      (via console_scripts entry point in pyproject.toml)
#   2. aw-qt discovers any `aw-*` executable on PATH at startup
#   3. aw-qt.toml tells aw-qt to autostart our watcher
#
# This survives ActivityWatch updates because both the pip-installed
# executable and aw-qt.toml live outside the .app bundle.
#
# Usage:
#   ./install.sh              # Interactive installation
#   ./install.sh --service    # Also install launchd service
#   ./install.sh --help       # Show help
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
PLIST_NAME="com.kepptic.aw-watcher-enhanced"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
LOG_DIR="$HOME/Library/Logs/activitywatch"
CONFIG_DIR="$HOME/Library/Application Support/activitywatch/aw-watcher-enhanced"

# Print functions
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

show_header() {
    echo ""
    echo "============================================================"
    echo "   ActivityWatch Enhanced Watcher - macOS Installer"
    echo "============================================================"
    echo ""
}

# Check requirements
check_requirements() {
    info "Checking requirements..."

    # Check Python
    if ! command -v python3 &> /dev/null; then
        error "Python 3 is not installed."
        echo "Install with: brew install python3"
        exit 1
    fi
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    success "Python $PYTHON_VERSION found"

    # Check pip
    if ! python3 -m pip --version &> /dev/null; then
        error "pip is not available."
        exit 1
    fi
    success "pip available"

    # Check if ActivityWatch is installed/running
    if curl -s http://localhost:5600/api/0/info &> /dev/null; then
        success "ActivityWatch server is running"
    else
        warn "ActivityWatch server is not running."
        echo "    Make sure to start ActivityWatch before using this watcher."
    fi

    echo ""
}

# Request accessibility permissions
request_permissions() {
    info "Checking accessibility permissions..."
    echo ""
    echo "This app requires Accessibility permissions to capture window titles."
    echo ""
    echo "To grant permissions:"
    echo "  1. Open System Settings > Privacy & Security > Accessibility"
    echo "  2. Click the + button"
    echo "  3. Add Terminal.app (or your terminal app) to the list"
    echo ""

    # Try to trigger the permission dialog
    osascript -e 'tell application "System Events" to get name of first process' &> /dev/null || true

    read -p "Press Enter after granting permissions (or 's' to skip): " response
    if [[ "$response" != "s" ]]; then
        success "Permissions check completed"
    fi
    echo ""
}

# Install Python package via pip
install_package() {
    info "Installing aw-watcher-enhanced..."

    # pip install with console_scripts creates an executable on PATH.
    # aw-qt scans PATH for aw-* executables, so this is all we need
    # for discovery. No wrapper scripts in the .app bundle required.
    PIP_FLAGS="--break-system-packages"

    # Check if --break-system-packages is supported (Python 3.11+)
    if ! pip3 install --help 2>&1 | grep -q "break-system-packages"; then
        PIP_FLAGS=""
    fi

    pip3 install -e "$PROJECT_DIR" $PIP_FLAGS --quiet 2>&1 || {
        error "pip install failed. Trying without --break-system-packages..."
        pip3 install -e "$PROJECT_DIR" --quiet
    }

    # Verify the executable is on PATH
    if command -v aw-watcher-enhanced &> /dev/null; then
        EXEC_PATH=$(command -v aw-watcher-enhanced)
        success "Package installed: $EXEC_PATH"
    else
        warn "Package installed but aw-watcher-enhanced not found on PATH."
        echo "    You may need to add pip's bin directory to your PATH."
        echo "    Try: pip3 show aw-watcher-enhanced"
    fi
    echo ""
}

# Register with aw-qt for autostart
register_with_awqt() {
    info "Registering with ActivityWatch..."

    AW_QT_CONFIG="$HOME/Library/Application Support/activitywatch/aw-qt/aw-qt.toml"

    if [[ -f "$AW_QT_CONFIG" ]]; then
        if grep -q "aw-watcher-enhanced" "$AW_QT_CONFIG"; then
            info "Already registered in aw-qt.toml"
        else
            info "Adding aw-watcher-enhanced to aw-qt autostart..."
            # Read existing autostart_modules and append ours
            # Simple approach: rewrite the config with our module added
            cat > "$AW_QT_CONFIG" << 'TOML'
[aw-qt]
autostart_modules = ["aw-server", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]

[aw-qt-testing]
autostart_modules = ["aw-server", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]
TOML
            success "Updated aw-qt.toml"
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

# Create default config
create_config() {
    info "Creating configuration..."

    mkdir -p "$CONFIG_DIR"

    if [[ ! -f "$CONFIG_DIR/config.yaml" ]]; then
        cat > "$CONFIG_DIR/config.yaml" << 'EOF'
# ActivityWatch Enhanced Watcher Configuration
# See README.md for full documentation

watcher:
  heartbeat_interval: 1.0  # Fast heartbeat for gap-free timeline (seconds)
  poll_time: 5.0            # Enrichment capture base frequency (seconds)

ocr:
  enabled: true
  trigger: adaptive   # adaptive, smart, window_change, periodic
  periodic_interval: 30
  engine: auto
  extract_mode: keywords
  max_keywords: 20

llm:
  model: gemma3:4b
  timeout: 10.0
  enabled: true

privacy:
  exclude_apps:
    - "1Password 7"
    - "Keychain Access"
    - "System Preferences"
  exclude_titles:
    - ".*[Pp]assword.*"
    - ".*[Pp]rivate.*"
  exclude_urls:
    - ".*bank.*"

categorization:
  enabled: true
  use_rag: true
  client_keywords: {}
EOF
        success "Created default config: $CONFIG_DIR/config.yaml"
    else
        info "Config already exists: $CONFIG_DIR/config.yaml"
    fi
}

# Create launchd plist (optional, for running independently of aw-qt)
create_launchd_plist() {
    info "Creating launchd service..."

    mkdir -p "$HOME/Library/LaunchAgents"
    mkdir -p "$LOG_DIR"

    EXEC_PATH=$(command -v aw-watcher-enhanced)
    if [[ -z "$EXEC_PATH" ]]; then
        EXEC_PATH="$(python3 -c 'import sysconfig; print(sysconfig.get_path("scripts"))')/aw-watcher-enhanced"
    fi

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
</dict>
</plist>
EOF

    success "Created launchd plist: $PLIST_PATH"
}

# Load launchd service
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

# Create uninstall script
create_uninstall_script() {
    UNINSTALL_SCRIPT="$PROJECT_DIR/installer/macos/uninstall.sh"
    cat > "$UNINSTALL_SCRIPT" << 'EOF'
#!/bin/bash
# Uninstall aw-watcher-enhanced from macOS

PLIST_NAME="com.kepptic.aw-watcher-enhanced"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "Uninstalling ActivityWatch Enhanced Watcher..."

# Stop and unload launchd service
if [[ -f "$PLIST_PATH" ]]; then
    echo "Stopping service..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm "$PLIST_PATH"
    echo "Service removed."
fi

# Ask about config removal
read -p "Remove configuration files? (y/n): " remove_config
if [[ "$remove_config" == "y" ]]; then
    rm -rf "$HOME/Library/Application Support/activitywatch/aw-watcher-enhanced"
    echo "Configuration removed."
fi

# Uninstall Python package (removes the executable from PATH)
read -p "Uninstall Python package? (y/n): " remove_pkg
if [[ "$remove_pkg" == "y" ]]; then
    pip3 uninstall -y aw-watcher-enhanced 2>/dev/null || true
    echo "Package uninstalled."
fi

echo ""
echo "Uninstallation complete."
echo "Note: ActivityWatch data (events) are stored separately and not removed."
echo "You may want to remove aw-watcher-enhanced from aw-qt.toml:"
echo "  $HOME/Library/Application Support/activitywatch/aw-qt/aw-qt.toml"
EOF
    chmod +x "$UNINSTALL_SCRIPT"
}

# Show completion message
show_completion() {
    echo ""
    echo "============================================================"
    echo "   Installation Complete!"
    echo "============================================================"
    echo ""
    echo "How it works:"
    echo "  pip install created 'aw-watcher-enhanced' on PATH"
    echo "  aw-qt discovers it automatically (no .app bundle changes)"
    echo "  Survives ActivityWatch updates"
    echo ""
    echo "Usage:"
    echo "  Run manually:    aw-watcher-enhanced"
    echo "  With verbose:    aw-watcher-enhanced --verbose"
    echo "  Without OCR:     aw-watcher-enhanced --no-ocr"
    echo "  Daily summary:   aw-watcher-enhanced --summary"
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
    echo "  $CONFIG_DIR/config.yaml"
    echo ""
    echo "Restart ActivityWatch to activate the watcher."
    echo ""
}

# Main installation flow
main() {
    show_header

    INSTALL_SERVICE=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --service|-s)
                INSTALL_SERVICE=true
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [options]"
                echo ""
                echo "Options:"
                echo "  --service, -s    Also install as launchd service (auto-start)"
                echo "  --help, -h       Show this help message"
                echo ""
                echo "The standard installation uses pip install + aw-qt.toml."
                echo "aw-qt discovers the watcher on PATH and manages its lifecycle."
                echo "The --service option adds a launchd service as a fallback."
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
    install_package
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
