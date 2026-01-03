# Bird Detection System - New Pi Setup Guide

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone Repository](#2-clone-repository)
3. [Run Setup Script](#3-run-setup-script)
4. [Configure API Keys](#4-configure-api-keys)
5. [Connect Camera](#5-connect-camera)
6. [Test Application](#6-test-application)
7. [Enable Services](#7-enable-services)
8. [Optional: Tailscale Setup](#8-optional-tailscale-setup)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Prerequisites

Before starting, ensure you have:

- [ ] Raspberry Pi 5 (4GB+ RAM recommended)
- [ ] Raspberry Pi OS installed and updated
- [ ] OAK-1 MAX camera with USB 3.0 cable
- [ ] Internet connection
- [ ] SSH or direct terminal access

**Update the system first:**
```bash
sudo apt update && sudo apt upgrade -y
```

---

## 2. Clone Repository

- [ ] Create the app directory:
  ```bash
  mkdir -p ~/BirdApp
  cd ~/BirdApp
  ```

- [ ] Clone the repository:
  ```bash
  git clone https://github.com/jaysettle/Bird_Bath_Photography.git BirdBathPhotographyUsingOakCameraRaspPi5a
  ```

- [ ] Enter the directory:
  ```bash
  cd BirdBathPhotographyUsingOakCameraRaspPi5a
  ```

- [ ] Switch to dev branch (if needed):
  ```bash
  git checkout dev
  git pull origin dev
  ```

---

## 3. Run Setup Script

The setup script automates most of the installation:

- [ ] Make the script executable:
  ```bash
  chmod +x setup.sh
  ```

- [ ] Run the setup script:
  ```bash
  ./setup.sh
  ```

**What the script does:**
- Installs system dependencies (python3-pyqt6, opencv, samba, etc.)
- Creates required directories:
  - `~/BirdPhotos/` - Main photo storage
  - `~/BirdPhotos/.thumbnails/` - Web thumbnail cache
  - `~/BirdPhotos/IdentifiedSpecies/` - AI-identified bird photos
  - `~/BirdPhotos/InstaPush/` - Instagram export folder
  - `logs/` - Application logs
- Sets up Python virtual environment with all packages
- Creates `config.json` template
- Installs systemd services
- Optionally configures Samba network share

---

## 4. Configure API Keys

Edit the configuration file:
```bash
nano config.json
```

### Shared Keys (same as main Pi)

These API keys can be shared between multiple Pi setups:

| Key | Location in config.json | Notes |
|-----|------------------------|-------|
| OpenAI API | `openai.api_key` | Bird identification - same key works on multiple devices |
| OpenWeatherMap | `weather.api_key` | Weather data - same key works everywhere |
| Gmail App Password | `email.password` | Email notifications - same account works |

**To copy keys from the main Pi:**
```bash
# On main Pi, show the keys:
cat config.json | grep -E "api_key|password"

# Then paste them into the new Pi's config.json
```

### Location-Specific Settings

Update these for the new Pi's location:

- [ ] `weather.latitude` - New location latitude
- [ ] `weather.longitude` - New location longitude
- [ ] `storage.save_dir` - Update username if different

### Enable Services

After adding keys, enable the features:

- [ ] Set `openai.enabled` to `true`
- [ ] Set `weather.enabled` to `true`
- [ ] Set `email.enabled` to `true` (if you want notifications)

### Example config.json changes:
```json
{
  "openai": {
    "api_key": "sk-xxxxx",
    "enabled": true
  },
  "weather": {
    "api_key": "xxxxx",
    "enabled": true,
    "latitude": 39.7042,
    "longitude": -86.3994
  },
  "email": {
    "sender": "jaysettle@gmail.com",
    "password": "xxxx xxxx xxxx xxxx",
    "enabled": true
  }
}
```

---

## 5. Connect Camera

- [ ] Connect OAK-1 MAX camera to a **USB 3.0 port** (blue port)
  - Use a quality USB 3.0 cable (thick cable recommended)
  - Powered USB hub can help with stability

- [ ] Verify camera is detected:
  ```bash
  lsusb | grep -i luxonis
  ```

  **Expected output:**
  ```
  Bus 001 Device 002: ID 03e7:f63b Intel Movidius MyriadX
  ```

  **If you see `03e7:2485` instead:**
  - Camera is in bootloader mode
  - Unplug for 30 seconds, then replug
  - Or start the app (it will boot the camera)

---

## 6. Test Application

Run the app manually first to verify everything works:

- [ ] Activate the virtual environment:
  ```bash
  source venv/bin/activate
  ```

- [ ] Start the desktop application:
  ```bash
  python3 main.py
  ```

- [ ] Verify these work:
  - [ ] Camera preview appears in Camera tab
  - [ ] Live view shows the bird bath
  - [ ] Motion detection triggers (wave hand in front)
  - [ ] Gallery tab shows any captured photos

- [ ] Test web interface:
  - [ ] Open browser to `http://<pi-ip>:8080`
  - [ ] Login with `birds` / `birdwatcher`
  - [ ] Gallery loads correctly

- [ ] Stop the app with `Ctrl+C` when done testing

---

## 7. Enable Services

Once testing passes, enable automatic startup:

- [ ] Enable both services:
  ```bash
  sudo systemctl enable bird-detection-watchdog bird-gallery-https
  ```

- [ ] Start both services:
  ```bash
  sudo systemctl start bird-detection-watchdog bird-gallery-https
  ```

- [ ] Verify they're running:
  ```bash
  sudo systemctl status bird-detection-watchdog
  sudo systemctl status bird-gallery-https
  ```

- [ ] Check the app is running:
  ```bash
  ps aux | grep python | grep -v grep
  ```

### Service Commands Reference

| Command | Description |
|---------|-------------|
| `sudo systemctl start bird-detection-watchdog` | Start desktop app |
| `sudo systemctl stop bird-detection-watchdog` | Stop desktop app |
| `sudo systemctl restart bird-detection-watchdog` | Restart desktop app |
| `sudo systemctl status bird-detection-watchdog` | Check status |
| `journalctl -u bird-detection-watchdog -f` | View live logs |
| `sudo systemctl restart bird-gallery-https` | Restart web server |

---

## 8. Optional: Tailscale Setup

For secure remote access via HTTPS:

- [ ] Install Tailscale:
  ```bash
  curl -fsSL https://tailscale.com/install.sh | sh
  ```

- [ ] Authenticate:
  ```bash
  sudo tailscale up
  ```
  - Follow the URL to log in
  - Device will appear in your Tailscale network

- [ ] Get the Tailscale IP:
  ```bash
  tailscale ip -4
  ```

- [ ] Access remotely:
  ```
  https://<tailscale-hostname>.tail23d264.ts.net
  ```

---

## 9. Troubleshooting

### Camera Not Detected

```bash
# Check USB devices
lsusb | grep -i luxonis

# Check dmesg for USB errors
dmesg | tail -20

# Try different USB port or cable
```

### App Won't Start

```bash
# Check logs
journalctl -u bird-detection-watchdog -n 50

# Check if display is available
echo $DISPLAY  # Should show :0

# Run manually to see errors
source venv/bin/activate
python3 main.py
```

### Web Interface Not Loading

```bash
# Check if gunicorn is running
ps aux | grep gunicorn

# Check web server logs
journalctl -u bird-gallery-https -n 50

# Test locally
curl http://localhost:8080/
```

### High CPU Usage

- Normal: 55-70% when camera is active
- Check with: `top` or `htop`
- VNC adds significant CPU load

### Config Not Loading

```bash
# Validate JSON syntax
python3 -m json.tool config.json

# Check file permissions
ls -la config.json
```

---

## Quick Reference

| Item | Value |
|------|-------|
| Web URL | `http://<pi-ip>:8080` |
| Web Login | `birds` / `birdwatcher` |
| Photos Location | `~/BirdPhotos/` |
| Config File | `config.json` |
| Logs | `logs/bird_detection.log` |
| Desktop App | `python3 main.py` |
| Watchdog Service | `bird-detection-watchdog` |
| Web Service | `bird-gallery-https` |

---

## Files You'll Need to Customize

| File | What to Change |
|------|----------------|
| `config.json` | API keys, location coordinates, email settings |
| ROI in app | Draw motion detection region for your bird bath position |

The ROI (Region of Interest) is set through the desktop app's Camera tab - draw a rectangle around where birds appear.
