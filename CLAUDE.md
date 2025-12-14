# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Table of Contents

- [Quick Reference](#quick-reference)
- [Architecture](#architecture)
- [Data Flow](#data-flow)
- [Key Config](#key-config-configjson)
- [Critical Patterns](#critical-patterns)
- [Settings Persistence](#settings-persistence)
- [Logging Tags](#logging-tags)
- [Photo Storage Structure](#photo-storage-structure)
- [Web Interface](#web-interface)
- [Common Issues](#common-issues)
- [Hardware](#hardware)

## Quick Reference

**Run the app:**
```bash
python3 main.py              # GUI app (camera takes ~60 seconds to initialize)
```

**Web interface:**
```bash
cd web_interface && python3 server.py       # Local: http://192.168.3.218:8080
cd web_interface && python3 run_https.py    # HTTPS via Tailscale
```

**Public gallery:** https://raspberry5.tail23d264.ts.net (auth: birds/birdwatcher)

**SSH access:**
```bash
ssh jaysettle@192.168.3.218           # Local network
ssh jaysettle@100.112.148.47          # Via Tailscale
```

**Systemd services:**
```bash
sudo systemctl start bird-detection-watchdog   # Start watchdog (also starts main app)
sudo systemctl status bird-detection-watchdog  # Check status
sudo journalctl -u bird-detection-watchdog -f  # Live logs
```

**Camera check:**
```bash
lsusb | grep -i luxonis      # Should show OAK camera
```

## Architecture

```
main.py (794 lines)                    # Entry point, MainWindow, service orchestration
├── src/
│   ├── camera_controller.py (850+)   # OAK-D camera interface, motion detection, DepthAI pipeline
│   ├── ai_bird_identifier.py (370)   # OpenAI Vision API, species identification
│   ├── email_handler.py (600)        # Gmail SMTP notifications
│   ├── drive_uploader_simple.py (850)# Google Drive multi-process uploader
│   ├── cleanup_manager.py (350)      # Storage management (skips IdentifiedSpecies)
│   ├── config_manager.py (156)       # Config loading/saving
│   ├── species_tab.py (1100)         # Species gallery widget
│   ├── threads/
│   │   ├── camera_thread.py (122)    # QThread for camera ops, freeze detection
│   │   ├── service_monitor.py (54)   # Monitors systemd services
│   │   ├── drive_stats_monitor.py    # Google Drive folder statistics
│   │   └── gallery_loader.py (82)    # Background image loading
│   └── ui/
│       ├── camera_tab.py (1494)      # Camera preview, ROI selection, settings save
│       ├── gallery_tab.py (1239)     # Photo viewer, date organization, multi-select
│       ├── config_tab.py (1208)      # Settings UI, API testing
│       ├── services_tab.py (468)     # Service enable/disable, status
│       ├── logs_tab.py (140)         # Real-time log viewer
│       ├── themes.py (232)           # Dark theme styling
│       ├── preview_widgets.py (157)  # InteractivePreviewLabel for ROI
│       └── dialogs/image_viewer.py   # Full-size image dialog with email
├── web_interface/
│   ├── server.py (1000+)             # Flask API, mobile gallery, auth
│   ├── run_https.py                  # HTTPS server with Tailscale certs
│   ├── static/js/app.js (1000+)      # Gallery JS, swipe nav, calendar
│   └── static/css/style.css          # Mobile-optimized dark theme
└── misc/
    └── bird_watchdog.py (233)        # External process monitor, auto-restart
```

## Data Flow

1. **OAK-D camera** → frame differencing in ROI → motion detected
2. **capture_still()** → JPEG saved to `~/BirdPhotos/YYYY-MM-DD/motion_*.jpeg`
3. **AIBirdIdentifier** → OpenAI Vision API (2 min rate limit) → species JSON
4. **Identified** → copy to `~/BirdPhotos/IdentifiedSpecies/{Species_Name}/`
5. **Not a bird** → image deleted to save space
6. **Optional:** Upload to Google Drive (2 workers, 400ms delay)
7. **Optional:** Email reports (hourly/daily via Gmail SMTP)

## Key Config (config.json)

```json
{
  "camera": {
    "resolution": "13mp",
    "preview_resolution": "THE_1080_P",
    "focus": 119,
    "exposure_ms": 1.78,
    "iso_min": 100,
    "iso_max": 145,
    "ev_compensation": 3,
    "white_balance": 6637,
    "brightness": 0,
    "orientation": "rotate_180"
  },
  "motion_detection": {
    "threshold": 100,
    "min_area": 500,
    "debounce_time": 4,
    "current_roi": {"x": 216, "y": 272, "width": 641, "height": 259}
  },
  "storage": {
    "save_dir": "/home/jaysettle/BirdPhotos",
    "max_size_gb": 7,
    "cleanup_time": "23:30",
    "cleanup_enabled": true
  }
}
```

## Critical Patterns

### X_LINK Error Handling (camera_controller.py)
All DepthAI queue operations catch RuntimeError and check for USB disconnect:
```python
except RuntimeError as e:
    error_msg = str(e).lower()
    if 'x_link' in error_msg or 'usb' in error_msg:
        self._mark_disconnected()
        raise ConnectionError(f"Camera USB disconnected: {e}")
```
CameraThread catches ConnectionError and triggers automatic reconnection every 5 seconds.

### Freeze Detection (Two Layers)

**Layer 1 - GUI Watchdog** (main.py):
- QTimer fires every 15 seconds
- Writes timestamp to `logs/heartbeat.txt`
- Checks frame update timing

**Layer 2 - External Watchdog** (misc/bird_watchdog.py):
- Runs as systemd service
- Checks heartbeat file every 60 seconds
- If stale > 60s → kills frozen process, restarts app

### Thread Safety
- Camera operations in QThread (camera_thread.py)
- AI identification in daemon thread
- Google Drive uploads in multiprocessing workers
- Email sending in background thread with pyqtSignal for UI updates
- All GUI updates via Qt signals/slots only

## Settings Persistence

Camera settings load BEFORE camera connects. Settings that need camera connection must be applied in `_apply_initial_settings()`:

```python
# In camera_controller.py _apply_initial_settings():
ev_compensation = self.config.get('ev_compensation', 0)
if ev_compensation != 0:
    ctrl.setAutoExposureCompensation(ev_compensation)
```

### Config File Path
`camera_tab.py` uses a constant for the config path (NOT `os.path.dirname(__file__)`):
```python
APP_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = APP_ROOT / 'config.json'
```

### ROI Loading
ROI is loaded from `self.config` in `load_default_roi()`, not from a separate file read:
```python
motion_config = self.config.get('motion_detection', {})
roi_config = motion_config.get('current_roi', {})
```

### Save Button Feedback
When settings are saved, the save button turns green with "✓ Saved" for 3 seconds:
```python
self.save_settings_btn.setText("✓ Saved")
self.save_settings_btn.setStyleSheet("background-color: #4CAF50; ...")
# Resets after 3 seconds via QTimer
```

## Logging Tags

```bash
# Camera heartbeat
grep "HEARTBEAT" logs/bird_detection.log

# Freeze detection
grep "FREEZE-DETECT\|FREEZE-WATCHDOG" logs/bird_detection.log

# X_LINK/USB errors
grep -i "x_link\|usb" logs/bird_detection.log

# EV compensation
grep "\[EV\]" logs/bird_detection.log

# Exposure changes
grep "\[EXPOSURE\]" logs/bird_detection.log

# ROI loading/saving
grep -a "ROI LOAD\|ROI SAVE\|ROI set" logs/bird_detection.log

# Motion detection
grep "Motion detected in ROI" logs/bird_detection.log

# AI identification
grep "Identified:\|No bird detected" logs/bird_detection.log

# Gallery loading performance
grep "\[GALLERY-LOAD\]" logs/bird_detection.log

# Frame timing
grep "\[FRAME-SLOW\]" logs/bird_detection.log

# Config file operations
grep "\[FILE-IO\]" logs/bird_detection.log

# External watchdog
grep "GUI FROZEN\|Application restarted" logs/watchdog.log
```

## Photo Storage Structure

```
~/BirdPhotos/
├── YYYY-MM-DD/                    # Daily folders (cleaned by cleanup_manager)
│   ├── species_name/              # Identified species subfolder
│   │   └── motion_*.jpeg
│   └── unidentified/
│       └── motion_*.jpeg
├── IdentifiedSpecies/             # NEVER deleted - species gallery copies
│   └── Species_Name/
│       └── motion_*.jpeg
└── .thumbnails/                   # Web interface cache (300x300)
```

## Web Interface

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| / | GET | Main gallery page |
| /species | GET | Species gallery page |
| /debug | GET | Simple public gallery |
| /api/stats | GET | System status JSON |
| /api/gallery | GET | Paginated gallery (date, offset, limit) |
| /api/images | GET | Recent images |
| /api/thumbnail/{path} | GET | 300x300 thumbnail |
| /api/image/{path} | GET | Full resolution image |
| /api/photo-counts | GET | Image counts by date (for calendar) |
| /api/email-image | POST | Email specific image |
| /api/restart | POST | Restart application |
| /api/clear-thumbnail-cache | POST | Clear thumbnail cache |

Auth required for public access: `birds`/`birdwatcher`

### Mobile Gallery Features
- Thumbnail grid (300x300) with lazy loading
- Full image on tap
- Swipe left/right navigation in modal
- Email button in image viewer
- Calendar with photo counts per day
- Collapsible day sections
- Infinite scroll with intersection observer

## Common Issues

**Camera not detected:**
```bash
lsusb | grep -i luxonis  # Should show device
dmesg | grep -i usb      # Check for errors
```

**GUI freezes:**
- Check `logs/heartbeat.txt` age
- External watchdog should auto-restart
- Manual: `killall python3 && python3 main.py`

**Settings not persisting:**
- Settings load before camera connects
- Must be applied in `_apply_initial_settings()`
- Check logs for `[EV] Applied` or similar

**AI not identifying:**
- Config tab → "Test API Connection" button
- Check 2-minute rate limit
- Verify API key in config.json

**Species gallery empty:**
- Verify `~/BirdPhotos/IdentifiedSpecies/` has photos
- cleanup_manager.py should skip this folder

**ROI not loading/persisting:**
- ROI saved in config.json under `motion_detection.current_roi`
- Preview fixed at 960x540, camera at 1920x1080 (2x scaling)
- Must use `self.config` not file read (see Settings Persistence section)
- Check logs: `grep -a "ROI LOAD" logs/bird_detection.log`

**Watchdog failing:**
- Check path: `/home/jaysettle/.../misc/bird_watchdog.py`
- Uses `APP_DIR = Path(__file__).parent.parent` for paths

## Hardware

- **Raspberry Pi 5** (4GB+ RAM)
- **OAK-1 MAX** camera (Luxonis DepthAI)
- USB 3.0 connection (SuperSpeed)
- Power: 5V/5A for Pi + dedicated supply for camera recommended
