#!/bin/bash
# Dynamic Bird Detection Watchdog Service Installer
# Works for any user and project directory

set -e

# Get current directory and user
CURRENT_DIR="$(cd "$(dirname "$0")" && pwd)"
CURRENT_USER="$(whoami)"

echo "Installing Bird Detection Watchdog Service..."
echo "Project Directory: $CURRENT_DIR"
echo "User: $CURRENT_USER"

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "ERROR: Don't run this script as root!"
    echo "Run as regular user - script will ask for sudo when needed"
    exit 1
fi

# Check if template exists
if [ ! -f "$CURRENT_DIR/services/bird-detection-watchdog.service.template" ]; then
    echo "ERROR: Service template not found!"
    echo "Expected: $CURRENT_DIR/services/bird-detection-watchdog.service.template"
    exit 1
fi

# Create service file from template
SERVICE_FILE="/tmp/bird-detection-watchdog.service"
sed "s|__USER__|$CURRENT_USER|g; s|__WORKDIR__|$CURRENT_DIR|g" \
    "$CURRENT_DIR/services/bird-detection-watchdog.service.template" > "$SERVICE_FILE"

echo "Generated service file:"
cat "$SERVICE_FILE"
echo ""

# Ask for confirmation
read -p "Install this watchdog service? [y/N]: " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled"
    rm -f "$SERVICE_FILE"
    exit 0
fi

# Install with sudo
echo "Installing service (requires sudo)..."
sudo cp "$SERVICE_FILE" /etc/systemd/system/bird-detection-watchdog.service
sudo systemctl daemon-reload
sudo systemctl enable bird-detection-watchdog.service

# Clean up
rm -f "$SERVICE_FILE"

echo ""
echo "✅ Watchdog service installed successfully!"
echo ""
echo "📋 Available commands:"
echo "   Start:   sudo systemctl start bird-detection-watchdog.service"
echo "   Stop:    sudo systemctl stop bird-detection-watchdog.service"
echo "   Status:  sudo systemctl status bird-detection-watchdog.service"
echo "   Logs:    sudo journalctl -u bird-detection-watchdog.service -f"
echo "   Disable: sudo systemctl disable bird-detection-watchdog.service"
echo ""
echo "⚠️  IMPORTANT:"
echo "   - Stop any manually running instances before starting watchdog"
echo "   - The watchdog will auto-restart the app if it crashes"
echo "   - Logs are available via journalctl and logs/watchdog.log"
echo ""
read -p "Start the watchdog service now? [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl start bird-detection-watchdog.service
    echo "✅ Watchdog service started!"
    echo "Check status: sudo systemctl status bird-detection-watchdog.service"
fi