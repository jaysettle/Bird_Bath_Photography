#!/bin/bash
#
# Bird Detection System Setup Script
# Run this after cloning the repo on a fresh Raspberry Pi 5
#
# Usage: ./setup.sh
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Bird Detection System Setup${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"
USER_HOME="$HOME"
PHOTOS_DIR="$USER_HOME/BirdPhotos"

echo -e "${YELLOW}App directory:${NC} $APP_DIR"
echo -e "${YELLOW}Photos directory:${NC} $PHOTOS_DIR"
echo ""

# Step 1: System Dependencies
echo -e "${GREEN}[1/7] Installing system dependencies...${NC}"
sudo apt update
sudo apt install -y \
    python3-pip python3-venv python3-pyqt6 \
    libgl1-mesa-glx libglib2.0-0 libxcb-cursor0 \
    samba samba-common-bin

# Step 2: Create directories
echo -e "${GREEN}[2/7] Creating directories...${NC}"
mkdir -p "$PHOTOS_DIR/.thumbnails"
mkdir -p "$PHOTOS_DIR/IdentifiedSpecies"
mkdir -p "$PHOTOS_DIR/InstaPush"
mkdir -p "$APP_DIR/logs"
echo "  Created: $PHOTOS_DIR/.thumbnails"
echo "  Created: $PHOTOS_DIR/IdentifiedSpecies"
echo "  Created: $PHOTOS_DIR/InstaPush"
echo "  Created: $APP_DIR/logs"

# Step 3: Python virtual environment
echo -e "${GREEN}[3/7] Setting up Python virtual environment...${NC}"
cd "$APP_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "  Created virtual environment"
else
    echo "  Virtual environment already exists"
fi

source venv/bin/activate
echo "  Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
echo "  Python packages installed"

# Step 4: Create config.json template if it doesn't exist
echo -e "${GREEN}[4/7] Checking configuration...${NC}"
if [ ! -f "$APP_DIR/config.json" ]; then
    echo "  Creating config.json template..."
    cat > "$APP_DIR/config.json" << 'CONFIGEOF'
{
  "camera": {
    "focus": 124,
    "exposure_ms": 2.29,
    "white_balance": 5952,
    "iso_min": 100,
    "iso_max": 145,
    "resolution": "12mp",
    "preview_resolution": "THE_1080_P",
    "socket": "rgb",
    "orientation": "rotate_180",
    "ev_compensation": 2
  },
  "motion_detection": {
    "threshold": 100,
    "min_area": 500,
    "debounce_time": 4,
    "current_roi": {
      "x": 166,
      "y": 239,
      "width": 701,
      "height": 281
    }
  },
  "storage": {
    "save_dir": "/home/jaysettle/BirdPhotos",
    "max_size_gb": 7,
    "cleanup_time": "23:30",
    "cleanup_enabled": true
  },
  "email": {
    "sender": "YOUR_EMAIL@gmail.com",
    "password": "YOUR_APP_PASSWORD",
    "receivers": {
      "primary": "YOUR_EMAIL@gmail.com"
    },
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 465,
    "enabled": false
  },
  "openai": {
    "api_key": "YOUR_OPENAI_API_KEY",
    "enabled": false,
    "max_images_per_hour": 18
  },
  "logging": {
    "enabled": false,
    "level": "ERROR"
  },
  "weather": {
    "enabled": false,
    "api_key": "YOUR_OPENWEATHERMAP_API_KEY",
    "latitude": 39.7042,
    "longitude": -86.3994,
    "check_interval_minutes": 60,
    "pause_on_rain": true
  }
}
CONFIGEOF
    echo -e "  ${YELLOW}IMPORTANT: Edit config.json with your API keys!${NC}"
else
    echo "  config.json already exists"
fi

# Step 5: Create systemd services
echo -e "${GREEN}[5/7] Setting up systemd services...${NC}"

# Watchdog service
sudo tee /etc/systemd/system/bird-detection-watchdog.service > /dev/null << SERVICEEOF
[Unit]
Description=Bird Detection System Watchdog
After=network.target
Wants=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_DIR/misc/bird_watchdog.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=bird-detection-watchdog

Environment=PYTHONPATH=$APP_DIR
Environment=DISPLAY=:0
Environment=XAUTHORITY=$USER_HOME/.Xauthority

[Install]
WantedBy=multi-user.target
SERVICEEOF
echo "  Created bird-detection-watchdog.service"

# Web gallery service
sudo tee /etc/systemd/system/bird-gallery-https.service > /dev/null << SERVICEEOF
[Unit]
Description=Bird Gallery HTTPS Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$APP_DIR/web_interface
ExecStart=$APP_DIR/venv/bin/gunicorn -w 4 --threads 2 -b 0.0.0.0:8080 server:app
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICEEOF
echo "  Created bird-gallery-https.service"

sudo systemctl daemon-reload
echo "  Reloaded systemd daemon"

# Step 6: Configure Samba (optional - prompt user)
echo -e "${GREEN}[6/7] Samba network share setup...${NC}"
read -p "  Set up Samba share for InstaPush folder? (y/n): " setup_samba
if [[ "$setup_samba" =~ ^[Yy]$ ]]; then
    # Check if share already exists
    if ! grep -q "\[InstaPush\]" /etc/samba/smb.conf 2>/dev/null; then
        sudo tee -a /etc/samba/smb.conf > /dev/null << SAMBAEOF

[InstaPush]
   path = $PHOTOS_DIR/InstaPush
   browseable = yes
   read only = no
   guest ok = no
   public = no
   create mask = 0644
   directory mask = 0755
   force user = $USER
SAMBAEOF
        echo "  Added InstaPush share to smb.conf"
    else
        echo "  InstaPush share already configured"
    fi

    echo "  Setting Samba password for $USER..."
    sudo smbpasswd -a $USER
    sudo systemctl restart smbd
    echo "  Samba configured and restarted"
else
    echo "  Skipping Samba setup"
fi

# Step 7: Summary and next steps
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo "1. Edit config.json with your API keys:"
echo "   nano $APP_DIR/config.json"
echo ""
echo "   Required keys:"
echo "   - openai.api_key (for bird identification)"
echo "   - weather.api_key (OpenWeatherMap, for rain pause)"
echo "   - email.password (Gmail app password)"
echo "   - weather.latitude/longitude (your location)"
echo ""
echo "2. Connect OAK camera via USB 3.0 and verify:"
echo "   lsusb | grep -i luxonis"
echo ""
echo "3. Test the app manually first:"
echo "   source $APP_DIR/venv/bin/activate"
echo "   python3 $APP_DIR/main.py"
echo ""
echo "4. Enable and start services:"
echo "   sudo systemctl enable bird-detection-watchdog bird-gallery-https"
echo "   sudo systemctl start bird-detection-watchdog bird-gallery-https"
echo ""
echo "5. Check service status:"
echo "   sudo systemctl status bird-detection-watchdog"
echo "   sudo systemctl status bird-gallery-https"
echo ""
echo "6. View logs:"
echo "   journalctl -u bird-detection-watchdog -f"
echo ""
echo -e "${GREEN}Web interface will be at: http://$(hostname -I | awk '{print $1}'):8080${NC}"
echo "  Username: birds"
echo "  Password: birdwatcher"
echo ""
