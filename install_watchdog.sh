#!/bin/bash
# Install Bird Detection Watchdog Service

echo "Installing Bird Detection Watchdog Service..."

# Copy service file
sudo cp /home/jaysettle/JayModel/MotionRevamp/services/bird-detection-watchdog.service /etc/systemd/system/

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