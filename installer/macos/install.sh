#!/bin/bash
# ============================================================================
# ActivityWatch Enhanced Watcher - macOS Installer
# ============================================================================
# This script installs aw-watcher-enhanced on macOS and optionally sets it up
# as a launchd service for automatic startup.
#
# Usage:
#   ./install.sh           # Interactive installation
#   ./install.sh --service # Install with launchd service
#   ./install.sh --help    # Show help
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
PLIST_NAME="com.dagtech.aw-watcher-enhanced"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
LOG_DIR="$HOME/Library/Logs/activitywatch"
CONFIG_DIR="$HOME/Library/Application Support/activitywatch/aw-watcher-enhanced"

# ActivityWatch app locations to check
AW_APP_PATHS=(
    "/Applications/ActivityWatch.app"
    "$HOME/Applications/ActivityWatch.app"
)
AW_DIR=""

# Print functions
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Show header
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

    # Check if ActivityWatch is installed
    if curl -s http://localhost:5600/api/0/info &> /dev/null; then
        success "ActivityWatch server is running"
    else
        warn "ActivityWatch server is not running."
        echo "    Make sure to start ActivityWatch before using this watcher."
    fi

    # Find ActivityWatch installation
    for aw_path in "${AW_APP_PATHS[@]}"; do
        if [[ -d "$aw_path" ]]; then
            AW_DIR="$aw_path/Contents/MacOS"
            success "Found ActivityWatch at: $aw_path"
            break
        fi
    done

    if [[ -z "$AW_DIR" ]]; then
        warn "ActivityWatch.app not found. Tray integration will not be available."
    fi

    echo ""
}

# Integrate with ActivityWatch tray menu
integrate_with_activitywatch() {
    if [[ -z "$AW_DIR" ]]; then
        return
    fi

    info "ActivityWatch tray integration..."
    echo ""
    echo "This will add aw-watcher-enhanced to the ActivityWatch modules view."
    echo "The watcher will appear in the ActivityWatch tray menu."
    echo ""

    read -p "Add to ActivityWatch tray menu? (y/n): " response
    if [[ "$response" != "y" ]]; then
        info "Skipping tray integration"
        return
    fi

    # Determine Python path
    if [[ "$USE_VENV" == "true" ]]; then
        PYTHON_PATH="$PROJECT_DIR/venv/bin/python3"
    else
        PYTHON_PATH=$(which python3)
    fi

    # Create a wrapper script in the ActivityWatch directory
    # ActivityWatch discovers watchers named aw-watcher-* in its directory
    WRAPPER_SCRIPT="$AW_DIR/aw-watcher-enhanced"

    cat > "$WRAPPER_SCRIPT" << EOF
#!/bin/bash
# ActivityWatch Enhanced Watcher wrapper
# This script allows ActivityWatch to discover and manage this watcher

export PYTHONPATH="${PROJECT_DIR}:\$PYTHONPATH"
exec "${PYTHON_PATH}" -m aw_watcher_enhanced "\$@"
EOF

    chmod +x "$WRAPPER_SCRIPT"

    if [[ -f "$WRAPPER_SCRIPT" ]]; then
        success "Created wrapper script: $WRAPPER_SCRIPT"

        # Update aw-qt.toml to include our watcher in autostart_modules
        AW_QT_CONFIG="$HOME/Library/Application Support/activitywatch/aw-qt/aw-qt.toml"
        if [[ -f "$AW_QT_CONFIG" ]]; then
            # Check if our watcher is already in the config
            if ! grep -q "aw-watcher-enhanced" "$AW_QT_CONFIG"; then
                info "Adding aw-watcher-enhanced to aw-qt autostart modules..."
                # Update or create autostart_modules line
                cat > "$AW_QT_CONFIG" << 'TOML'
[aw-qt]
autostart_modules = ["aw-server", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]

[aw-qt-testing]
autostart_modules = ["aw-server", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]
TOML
                success "Updated aw-qt.toml with autostart configuration"
            else
                info "aw-watcher-enhanced already in aw-qt.toml"
            fi
        else
            # Create the config file if it doesn't exist
            mkdir -p "$(dirname "$AW_QT_CONFIG")"
            cat > "$AW_QT_CONFIG" << 'TOML'
[aw-qt]
autostart_modules = ["aw-server", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]

[aw-qt-testing]
autostart_modules = ["aw-server", "aw-watcher-afk", "aw-watcher-window", "aw-watcher-enhanced"]
TOML
            success "Created aw-qt.toml with autostart configuration"
        fi

        success "Tray integration complete!"
        echo ""
        echo "    NOTE: Restart ActivityWatch to see the watcher in the tray menu."
        TRAY_INTEGRATED=true
    else
        error "Failed to create wrapper script. You may need to run with sudo."
        TRAY_INTEGRATED=false
    fi
    echo ""
}

# Request accessibility permissions
request_permissions() {
    info "Checking accessibility permissions..."

    # Check if Terminal has accessibility access
    # This is required for window title capture on macOS

    echo ""
    echo "This app requires Accessibility permissions to capture window titles."
    echo ""
    echo "To grant permissions:"
    echo "  1. Open System Preferences > Security & Privacy > Privacy"
    echo "  2. Select 'Accessibility' in the left panel"
    echo "  3. Click the lock icon and enter your password"
    echo "  4. Add Terminal.app (or your terminal app) to the list"
    echo ""

    # Try to trigger the permission dialog
    osascript -e 'tell application "System Events" to get name of first process' &> /dev/null || true

    read -p "Press Enter after granting permissions (or 's' to skip): " response
    if [[ "$response" != "s" ]]; then
        success "Permissions check completed"
    fi
    echo ""
}

# Install Python package
install_package() {
    info "Installing aw-watcher-enhanced..."

    # Check if we should create a virtual environment
    if [[ "$USE_VENV" == "true" ]]; then
        VENV_DIR="$PROJECT_DIR/venv"
        if [[ ! -d "$VENV_DIR" ]]; then
            info "Creating virtual environment..."
            python3 -m venv "$VENV_DIR"
        fi
        source "$VENV_DIR/bin/activate"
        success "Virtual environment activated"
    fi

    # Install package with macOS dependencies
    pip3 install -e "$PROJECT_DIR[macos,ocr]" --quiet

    success "Package installed"
    echo ""
}

# Create launchd plist
create_launchd_plist() {
    info "Creating launchd service..."

    # Ensure LaunchAgents directory exists
    mkdir -p "$HOME/Library/LaunchAgents"

    # Determine Python path
    if [[ "$USE_VENV" == "true" ]]; then
        PYTHON_PATH="$PROJECT_DIR/venv/bin/python3"
    else
        PYTHON_PATH=$(which python3)
    fi

    # Create log directory
    mkdir -p "$LOG_DIR"

    # Create plist file
    cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>-m</string>
        <string>aw_watcher_enhanced</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>PYTHONPATH</key>
        <string>${PROJECT_DIR}</string>
    </dict>

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

    # Unload if already loaded
    launchctl unload "$PLIST_PATH" 2>/dev/null || true

    # Load the service
    launchctl load "$PLIST_PATH"

    success "Service loaded"

    # Check if running
    sleep 2
    if launchctl list | grep -q "$PLIST_NAME"; then
        success "Service is running"
    else
        warn "Service may not have started. Check logs:"
        echo "    tail -f $LOG_DIR/aw-watcher-enhanced.log"
    fi
}

# Create config directory and default config
create_config() {
    info "Creating configuration..."

    mkdir -p "$CONFIG_DIR"

    if [[ ! -f "$CONFIG_DIR/config.yaml" ]]; then
        cat > "$CONFIG_DIR/config.yaml" << 'EOF'
# ActivityWatch Enhanced Watcher Configuration
# See README.md for full documentation

watcher:
  poll_time: 5.0      # Seconds between checks
  pulsetime: 6.0      # Heartbeat merge window

ocr:
  enabled: true
  trigger: window_change  # window_change, periodic, or both
  periodic_interval: 30   # Seconds (if periodic)
  engine: auto            # auto, tesseract
  extract_mode: keywords  # keywords, entities, full_text
  max_keywords: 20
  # Multi-monitor support
  capture_all_monitors: false  # Set to true for multi-monitor OCR

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
  use_rag: true  # Use RAG database for client detection
  # Add custom client keywords here if needed
  client_keywords: {}
EOF
        success "Created default config: $CONFIG_DIR/config.yaml"
    else
        info "Config already exists: $CONFIG_DIR/config.yaml"
    fi
}

# Create uninstall script
create_uninstall_script() {
    UNINSTALL_SCRIPT="$PROJECT_DIR/installer/macos/uninstall.sh"
    cat > "$UNINSTALL_SCRIPT" << 'EOF'
#!/bin/bash
# Uninstall aw-watcher-enhanced from macOS

PLIST_NAME="com.dagtech.aw-watcher-enhanced"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

# ActivityWatch app locations
AW_APP_PATHS=(
    "/Applications/ActivityWatch.app"
    "$HOME/Applications/ActivityWatch.app"
)

echo "Uninstalling ActivityWatch Enhanced Watcher..."

# Stop and unload service
if [[ -f "$PLIST_PATH" ]]; then
    echo "Stopping service..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm "$PLIST_PATH"
    echo "Service removed."
fi

# Remove ActivityWatch tray integration
for aw_path in "${AW_APP_PATHS[@]}"; do
    WRAPPER_SCRIPT="$aw_path/Contents/MacOS/aw-watcher-enhanced"
    if [[ -f "$WRAPPER_SCRIPT" ]]; then
        echo "Removing ActivityWatch tray integration..."
        rm -f "$WRAPPER_SCRIPT"
        echo "Tray integration removed."
        break
    fi
done

# Ask about config removal
read -p "Remove configuration files? (y/n): " remove_config
if [[ "$remove_config" == "y" ]]; then
    rm -rf "$HOME/Library/Application Support/activitywatch/aw-watcher-enhanced"
    echo "Configuration removed."
fi

# Ask about package removal
read -p "Uninstall Python package? (y/n): " remove_pkg
if [[ "$remove_pkg" == "y" ]]; then
    pip3 uninstall -y aw-watcher-enhanced 2>/dev/null || true
    echo "Package removed."
fi

echo ""
echo "Uninstallation complete."
echo "Note: ActivityWatch data (events) are stored separately and not removed."
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
    echo "Usage:"
    echo "  Run manually:    aw-watcher-enhanced"
    echo "  With verbose:    aw-watcher-enhanced --verbose"
    echo "  Without OCR:     aw-watcher-enhanced --no-ocr"
    echo ""

    if [[ "$INSTALL_SERVICE" == "true" ]]; then
        echo "Service commands:"
        echo "  Status:  launchctl list | grep aw-watcher"
        echo "  Stop:    launchctl unload $PLIST_PATH"
        echo "  Start:   launchctl load $PLIST_PATH"
        echo "  Logs:    tail -f $LOG_DIR/aw-watcher-enhanced.log"
        echo ""
    fi

    if [[ "$TRAY_INTEGRATED" == "true" ]]; then
        echo "Tray Integration:"
        echo "  The watcher appears in the ActivityWatch tray menu."
        echo "  Restart ActivityWatch if it doesn't appear immediately."
        echo ""
    fi

    echo "Configuration:"
    echo "  $CONFIG_DIR/config.yaml"
    echo ""
    echo "Logs:"
    echo "  $LOG_DIR/"
    echo ""
}

# Main installation flow
main() {
    show_header

    # Parse arguments
    INSTALL_SERVICE=false
    USE_VENV=false
    TRAY_INTEGRATED=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --service|-s)
                INSTALL_SERVICE=true
                shift
                ;;
            --venv|-v)
                USE_VENV=true
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [options]"
                echo ""
                echo "Options:"
                echo "  --service, -s    Install as launchd service (auto-start)"
                echo "  --venv, -v       Create and use virtual environment"
                echo "  --help, -h       Show this help message"
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    # Interactive mode if no arguments
    if [[ "$INSTALL_SERVICE" == "false" ]]; then
        read -p "Install as auto-starting service? (y/n): " response
        if [[ "$response" == "y" ]]; then
            INSTALL_SERVICE=true
        fi
    fi

    if [[ "$USE_VENV" == "false" ]]; then
        read -p "Create virtual environment? (y/n): " response
        if [[ "$response" == "y" ]]; then
            USE_VENV=true
        fi
    fi

    # Run installation steps
    check_requirements
    request_permissions
    install_package
    create_config
    create_uninstall_script

    # ActivityWatch tray integration
    integrate_with_activitywatch

    if [[ "$INSTALL_SERVICE" == "true" ]]; then
        create_launchd_plist
        load_service
    fi

    show_completion
}

# Run main
main "$@"
