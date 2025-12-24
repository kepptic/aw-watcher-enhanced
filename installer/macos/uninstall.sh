#!/bin/bash
# ============================================================================
# ActivityWatch Enhanced Watcher - macOS Uninstaller
# ============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PLIST_NAME="com.dagtech.aw-watcher-enhanced"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
CONFIG_DIR="$HOME/Library/Application Support/activitywatch/aw-watcher-enhanced"
LOG_DIR="$HOME/Library/Logs/activitywatch"

# ActivityWatch app locations to check for tray integration
AW_APP_PATHS=(
    "/Applications/ActivityWatch.app"
    "$HOME/Applications/ActivityWatch.app"
)

echo ""
echo "============================================================"
echo "   ActivityWatch Enhanced Watcher - Uninstaller"
echo "============================================================"
echo ""

# Stop and remove launchd service
if [[ -f "$PLIST_PATH" ]]; then
    echo -e "${YELLOW}Stopping service...${NC}"
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm "$PLIST_PATH"
    echo -e "${GREEN}Service removed.${NC}"
else
    echo "No launchd service found."
fi

echo ""

# Remove ActivityWatch tray integration
for aw_path in "${AW_APP_PATHS[@]}"; do
    WRAPPER_SCRIPT="$aw_path/Contents/MacOS/aw-watcher-enhanced"
    if [[ -f "$WRAPPER_SCRIPT" ]]; then
        echo -e "${YELLOW}Removing ActivityWatch tray integration...${NC}"
        rm -f "$WRAPPER_SCRIPT"
        echo -e "${GREEN}Tray integration removed.${NC}"
        echo "    NOTE: Restart ActivityWatch to update the tray menu."
        break
    fi
done

echo ""

# Ask about config removal
read -p "Remove configuration files? (y/n): " remove_config
if [[ "$remove_config" == "y" ]]; then
    if [[ -d "$CONFIG_DIR" ]]; then
        rm -rf "$CONFIG_DIR"
        echo -e "${GREEN}Configuration removed.${NC}"
    else
        echo "No configuration directory found."
    fi
fi

# Ask about log removal
read -p "Remove log files? (y/n): " remove_logs
if [[ "$remove_logs" == "y" ]]; then
    rm -f "$LOG_DIR/aw-watcher-enhanced.log" 2>/dev/null || true
    rm -f "$LOG_DIR/aw-watcher-enhanced.error.log" 2>/dev/null || true
    echo -e "${GREEN}Logs removed.${NC}"
fi

# Ask about package removal
read -p "Uninstall Python package? (y/n): " remove_pkg
if [[ "$remove_pkg" == "y" ]]; then
    pip3 uninstall -y aw-watcher-enhanced 2>/dev/null || true
    echo -e "${GREEN}Package removed.${NC}"
fi

echo ""
echo "============================================================"
echo "   Uninstallation Complete!"
echo "============================================================"
echo ""
echo "Note: ActivityWatch data (events) are stored separately and not removed."
echo "To remove watcher data, delete the bucket in ActivityWatch web UI."
echo ""
