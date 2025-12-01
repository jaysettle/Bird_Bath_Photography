#!/bin/bash
# DEPRECATED: This script contains hardcoded paths
# Use install_watchdog_dynamic.sh instead!

echo "⚠️  DEPRECATED SCRIPT ⚠️"
echo "This script contains hardcoded paths and is no longer supported."
echo ""
echo "Please use the new dynamic installer instead:"
echo "  ./install_watchdog_dynamic.sh"
echo ""
echo "The new installer:"
echo "  ✅ Works for any user and directory"
echo "  ✅ No hardcoded paths"
echo "  ✅ Interactive setup with confirmations"
echo "  ✅ Better error handling"
echo ""
read -p "Continue with deprecated script anyway? [y/N]: " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled. Please use: ./install_watchdog_dynamic.sh"
    exit 0
fi

echo "Installing Bird Detection Watchdog Service (deprecated method)..."

# Copy service file (HARDCODED - WILL FAIL FOR OTHER USERS)
sudo cp services/bird-detection-watchdog.service.deprecated /etc/systemd/system/bird-detection-watchdog.service

# Reload systemd
sudo systemctl daemon-reload

# Enable the service
sudo systemctl enable bird-detection-watchdog.service

echo "Watchdog service installed successfully!"
echo ""
echo "To start the watchdog service:"
echo "sudo systemctl start bird-detection-watchdog.service"
echo ""
echo "To check status:"
echo "sudo systemctl status bird-detection-watchdog.service"
echo ""
echo "To view logs:"
echo "sudo journalctl -u bird-detection-watchdog.service -f"
echo ""
echo "To stop the service:"
echo "sudo systemctl stop bird-detection-watchdog.service"
echo ""
echo "Note: The watchdog will automatically start the Bird Detection application"
echo "and restart it if it crashes. Make sure to stop any manually running"
echo "instances before starting the watchdog service."