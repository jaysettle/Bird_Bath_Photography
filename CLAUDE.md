# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Installation & Setup
```bash
./install.sh                 # Full system installation with dependencies
source bird_env/bin/activate # Activate virtual environment (if created)
pip install -r requirements.txt
```

### Running the Application
```bash
python3 main.py              # Start main GUI application (camera takes ~60 seconds to initialize)
cd web_interface && python3 server.py  # Start mobile web interface (port 8080)
```

### Testing Camera Connection
```bash
lsusb | grep -i movidius      # Check for OAK camera (Movidius VPU)
lsusb | grep -i luxonis       # Check for OAK camera (Luxonis)
```

### Services & Background Processes
```bash
./install_watchdog_dynamic.sh # Install system service for automatic startup (interactive)
sudo systemctl start bird-detection-watchdog   # Start watchdog service
sudo systemctl stop bird-detection-watchdog    # Stop watchdog service
sudo systemctl status bird-detection-watchdog  # Check service status
sudo systemctl enable bird-detection-watchdog  # Enable autostart on reboot (done by install script)
sudo systemctl disable bird-detection-watchdog # Disable autostart
sudo journalctl -u bird-detection-watchdog -f  # View live logs
```

### Web Interface
- Main app runs Flask server on port 5000
- Mobile interface in `web_interface/` directory
- Access via http://hostname:5000 or http://hostname:8080

### Logs and Debugging
```bash
tail -f ~/BirdApp/BirdBathPhotographyUsingOakCameraRaspPi5a/logs/bird_detection.log  # Main application log
dmesg | grep -i usb           # Check USB device messages for camera connectivity
ps aux | grep python3         # Check running Python processes

# Freeze detection logs (see Freeze Detection Logging section below)
grep "HEARTBEAT" logs/bird_detection.log          # Camera thread alive
grep "FREEZE-DETECT" logs/bird_detection.log      # Automatic freeze detection and recovery
grep "FREEZE-CHECK" logs/bird_detection.log       # Frame update tracking
grep "FREEZE-WATCHDOG" logs/bird_detection.log    # GUI responsiveness
```

## Recent Updates (2025-10-30 to 2025-11-03)

### Configuration & Email Fixes
1. **Email Password Saving** - Fixed email app password not saving correctly
   - Added `.strip()` to remove whitespace/newlines from email credentials (main.py:4985-4987)
   - Also strips OpenAI API key to prevent similar issues (main.py:5016)
   - Manually fixed existing config.json to remove trailing newline

2. **Send Test Email Button** - Fixed test email functionality in ALL tabs
   - **ConfigurationTab** (main.py:5153+): Creates temporary EmailHandler with current UI values
   - **ServicesTab** (main.py:3951-3989): Uses saved config, creates temporary handler
   - **GalleryTab**: Already working (uses existing email_handler)
   - All test buttons work without requiring save first
   - Provides helpful error messages for common issues

3. **Test API Connection Button** - Added visual feedback (2025-11-03)
   - Shows **✓ GOOD** (green) for 2 seconds on success
   - Shows **✗ BAD** (red) for 2 seconds on failure
   - Implementation: `_update_api_button_status()` and `_reset_api_button()` (main.py:4396-4441)
   - Applied to ALL error cases (401, 429, 402, timeout, connection error, etc.)

### Species Tab Fixes
4. **Species Gallery Display** - Fixed empty species gallery issue
   - **Root Cause**: Cleanup manager was deleting photos from IdentifiedSpecies folder
   - **Solution**: Updated cleanup_manager.py to skip IdentifiedSpecies folder:
     - `get_file_count()` - Skip IdentifiedSpecies (lines 49-51)
     - `get_oldest_files()` - Skip IdentifiedSpecies (lines 64-66)
     - `cleanup_by_age()` - Skip IdentifiedSpecies (lines 181-183)
   - **Result**: Species photos are now permanently preserved for gallery display
   - Updated CLAUDE.md to document preservation behavior (line 528)

### Freeze Detection Logging
5. **Comprehensive Freeze Detection System** - Added multi-layer logging to diagnose freezes
   - **Camera Thread Heartbeat** (main.py:495-504): Logs every 30 seconds
   - **Frame Emission Logging** (main.py:532-534): Tracks frame retrieval and emission
   - **Frame Update Tracking** (main.py:1042-1061): Detects gaps in GUI updates
   - **Qt Display Pipeline Logging** (main.py:1078-1101): Logs QImage/QPixmap creation
   - **GUI Watchdog Timer** (main.py:5319-5324, 5690-5713): Monitors event loop health
   - See "Freeze Detection Logging" section below for full details

### Camera Settings Fixes
6. **ISO Settings Now Work** - Fixed ISO sliders not affecting captures (2025-11-03)
   - **Root Cause**: ISO sliders only updated UI labels, didn't apply to camera
   - **Solution**:
     - Added 'iso' case to `update_camera_setting()` (camera_controller.py:693-696)
     - Fixed hardcoded ISO 800 in exposure settings (lines 690-692, 711-713)
     - Fixed hardcoded ISO 800 in initial setup (lines 249-250)
     - Connected UI sliders to camera controller (main.py:1214-1216, 1225-1227)
   - **Result**: ISO sliders now immediately affect both preview and captured images
   - **Important**: In DepthAI, `setManualExposure(exposure_us, iso)` takes BOTH parameters

7. **Exposure Range Improved** - Changed exposure slider range for better control (2025-11-03)
   - **Old Range**: 1-33ms (1ms increments)
   - **New Range**: 0.5-10ms (0.1ms increments)
   - **Implementation**: Slider uses units of 0.1ms (range 5-100), converted to/from ms in UI
   - **Benefits**: Finer control for fast-moving subjects, prevents overexposure in bright conditions
   - **Files Changed**: main.py lines 773-778, 1186-1192, 1681-1683, 1749-1753

8. **Camera Settings Metadata Overlay** - Added exposure and ISO to captured images (2025-11-03)
   - **Added to overlay**: Exposure and ISO values burned into top-left of each captured image
   - **Purpose**: Verify actual camera settings being used, not just UI values
   - **Display format**:
     - Date/Time (white)
     - Focus: 135 (green)
     - Exposure: 2.0ms (green)
     - ISO: 184 (green)
   - **Implementation**: camera_controller.py lines 530-541

9. **Fixed ISO/Exposure Not Updating in Overlay** - Critical fix (2025-11-03)
   - **Problem**: Slider showed ISO 184, but captured image showed ISO 900
   - **Root Cause**: `update_camera_setting()` sent values to camera but didn't update config
   - **Solution**: Update config when settings change so overlay reads correct values
   - **Files Changed**:
     - camera_controller.py line 708: Update `config['exposure_ms']`
     - camera_controller.py line 712: Update `config['iso_max']`
   - **Result**: Overlay now shows actual slider values being applied to camera

### How to Use Recent Fixes
- **Email**: Configure in Configuration tab, use "Send Test Email" to verify (works in Config and Services tabs)
- **Test API Connection**: Button shows green (GOOD) or red (BAD) for 2 seconds after testing
- **Species Gallery**: Will populate as new birds are identified by OpenAI
- **ISO Settings**: Move sliders to see immediate effect in preview and captures
- **Freeze Detection**:
  - INFO level (default): Shows heartbeat, watchdog, and major events
  - DEBUG level: Shows detailed frame-by-frame tracking (verbose)
  - To enable DEBUG: Set `"level": "DEBUG"` in config.json under `"logging"` section
  - Restart app after changing logging level

## Recent Updates (2025-11-14) - ROI Persistence & Statistics Display

### 10. **ROI Persistence Fixed** - Critical fix for ROI coordinate saving/loading (2025-11-14)
**Problem**: ROI settings would not persist correctly across reboots. ROI saved at coordinates (182, 322, 600x227) would load as (208, 295, 691x208), appearing in a different position.

**Root Cause Identified**:
- `InteractivePreviewLabel.scale_for_fullscreen()` method (main.py:243-256) was overwriting `base_width` and `base_height` with hardcoded values (900x600 or 600x400)
- This corrupted the resolution-specific base dimensions that should remain constant at 605x506 (for THE_720_P)
- When saving ROI, the system calculated zoom as 1.0x instead of the actual 1.5x, resulting in incorrect base coordinates

**Solution Applied**:
- Changed `scale_for_fullscreen()` to use `zoom_factor` instead of modifying base dimensions:
  ```python
  # OLD (WRONG):
  self.base_width = 900  # Corrupted base dimensions
  self.base_height = 600

  # NEW (CORRECT):
  self.zoom_factor = 1.5  # Preserves base dimensions
  ```
- This preserves resolution-specific base dimensions while still scaling the widget display

**Enhanced Logging**:
- Added comprehensive "ROI SAVE TEST" logging before save operations (main.py:1890-1945)
- Added "ROI LOAD TEST" logging after restart (main.py:1668-1720)
- Logs show widget coordinates, base coordinates, zoom factors, and clamping operations
- Makes debugging ROI issues straightforward

**Verification Results**:
- ✅ Base dimensions now stay at 605x506 (correct for THE_720_P)
- ✅ Zoom calculated correctly as 1.50x
- ✅ ROI persists across reboots with ±1 pixel accuracy (acceptable for integer rounding)
- Test: Saved (179, 383, 612x237) → Restored (178, 382, 611x237)

**Debugging ROI Persistence**:
```bash
# View detailed save/load logs
grep -E "ROI SAVE TEST|ROI LOAD TEST" logs/bird_detection.log | tail -50

# Check saved ROI in config
cat config.json | grep -A 10 "current_roi"
```

### 11. **Camera Statistics Display Enhanced** - Added preview/capture info to Statistics section (2025-11-14)
**Added Fields**:
- Preview Resolution: Shows preview resolution (e.g., "720p", "1211x1013")
- Capture Resolution: Shows capture resolution (e.g., "13MP", "4K")
- Zoom Level: Shows current zoom factor (e.g., "1.50x") - updates every 5 seconds
- ROI Info: Shows ROI coordinates in base coordinate space or "None"

**Implementation**:
- Added new labels to Statistics section (main.py:1042-1058)
- Update logic in `update_camera_stats()` (main.py:1201-1243)
- Statistics refresh every 5 seconds automatically

**Display Format**:
```
Column 1: Model, Connection, Sensor|FPS, Resolution (capture)
Column 2: Photos|Events, Last Capture, Preview res, Capture res
Column 3: Zoom level, ROI coordinates
```

## Recent Updates (2025-11-08/09) - Freeze Recovery & Power Investigation

### 12. **Automatic Freeze Detection and Recovery** - Critical reliability improvement
**Problem**: GUI would freeze (display stopped updating) but camera thread continued running. System did not gracefully recover, requiring manual restart.

**Investigation Findings**:
- **Pattern Identified**: Camera thread logs showed frames being retrieved and emitted, but GUI stopped processing them
- **Root Cause**: Not a camera hardware issue or X_LINK error - the frame processing pipeline between camera thread and GUI event loop stalled
- **Power Investigation**: Initially suspected power issue. Verified:
  - OAK-1 MAX draws 2.5-4.5W (0.5-0.9A at 5V) under normal operation
  - Raspberry Pi 5 needs 8-15W typical, up to 15W under load
  - Combined system needs 10.5-19.5W (2.1-3.9A at 5V minimum)
  - Added second exclusive power supply to camera (5V/3A dedicated)
  - **Freezes persisted even with separate power** - ruled out power as root cause
- **Historical X_LINK Error**: Found one instance (2025-11-05 17:46:06) of `"Couldn't read data from stream: 'still'"` suggesting occasional USB communication issues, but not present in most freezes

**Solution - Automatic Recovery** (main.py:491-518):
Added watchdog logic in camera thread to detect stalled frame processing:

```python
last_successful_frame = time.time()
frame_timeout = 15  # Force reconnect if no frames processed for 15 seconds
consecutive_frame_failures = 0
max_frame_failures = 5

# In camera loop:
time_since_frame = current_time - last_successful_frame
if time_since_frame > frame_timeout and self.camera_controller.is_connected():
    logger.error(f"[FREEZE-DETECT] No frames processed for {time_since_frame:.1f}s - forcing camera reconnect to recover")
    self.camera_controller.disconnect()
    was_connected = False
    consecutive_frame_failures = 0
    continue  # Trigger automatic reconnection
```

**Key Features**:
- Tracks time since last successful frame emission
- If > 15 seconds with no frame processing, forces camera disconnect
- Triggers automatic reconnection loop (every 5 seconds)
- Resets frame timer after successful reconnection
- Also tracks consecutive frame retrieval failures (warns after 5)

**Heartbeat Enhancement** (main.py:507):
```python
logger.info(f"[HEARTBEAT] Camera thread alive - connected: {self.camera_controller.is_connected()}, errors: {self.connection_error_count}, frames_ok: {time.time() - last_successful_frame:.1f}s ago")
```
- Now includes time since last successful frame
- Changed to INFO level (was DEBUG) for critical monitoring
- Logs every 30 seconds

**Benefits**:
- **Graceful Failure**: System automatically recovers from GUI/camera pipeline stalls
- **No Manual Intervention**: Reconnects without user action
- **Early Detection**: 15-second timeout catches freezes quickly
- **Detailed Logging**: `[FREEZE-DETECT]` markers clearly identify recovery events

**Debugging Freeze Issues**:
```bash
# Check if automatic recovery is working
grep "FREEZE-DETECT" logs/bird_detection.log

# Monitor heartbeat to see frame processing health
grep "HEARTBEAT" logs/bird_detection.log | tail -10

# Check for X_LINK/USB errors (separate from freeze recovery)
grep "X_LINK" logs/bird_detection.log
```

**Common Freeze Patterns**:
1. **Camera Thread Stall**: No HEARTBEAT logs → Camera thread died (rare)
2. **Frame Pipeline Freeze**: HEARTBEAT shows `frames_ok: 15.0s ago` → Automatic recovery triggered
3. **X_LINK USB Error**: `"Couldn't read data from stream"` → Hardware communication issue
4. **GUI Event Loop Freeze**: Qt becomes unresponsive, signals not processed

**Power Supply Recommendations** (verified 2025-11-08):
- **Minimum**: 5V/5A (25W) power supply for Pi 5 + OAK camera
- **Recommended**: Dual power setup:
  - Pi 5: Official 5V/5A (27W) USB-C power supply
  - OAK camera: Dedicated 5V/3A supply via USB 3.0
- **Not Sufficient**: Single 5V/3A supply shared between Pi and camera (may cause brownouts)
- **Check**: `dmesg | grep -i "under-voltage"` to verify no power warnings

**When Automatic Recovery Fails**:
If system does not recover after multiple reconnection attempts:
1. Check USB connection: `lsusb | grep -i luxonis`
2. Check kernel USB logs: `dmesg | grep -i usb | tail -20`
3. Kill and restart app: `killall -9 python3 && python3 main.py`
4. Reboot if USB subsystem is unresponsive

### 11. **Qt Event Loop Freeze - Critical Discovery** (2025-11-09/10)
**Problem**: System still freezing despite camera-thread freeze detection. Further investigation revealed a **Qt-specific** freeze pattern.

**Critical Finding**: **Qt Event Loop Freeze**
- Camera thread continues running normally (HEARTBEAT logs show `frames_ok: 0.0s ago`)
- Camera thread emits frames via `frame_ready.emit(frame)` signal
- **GUI never receives signals** - Qt event loop completely frozen
- QTimer callbacks (including watchdog timer) never fire when event loop is frozen
- Process continues using CPU and memory but GUI is unresponsive

**Why Camera-Side Detection Failed**:
- Camera thread successfully gets frames from hardware
- Camera thread emits Qt signals (fire-and-forget, no acknowledgment)
- From camera thread's perspective, everything works fine
- Cannot detect that GUI stopped processing signals

**Solution - External Watchdog with Heartbeat File** (2025-11-10):
Implemented two-layer monitoring:

**Layer 1: GUI Watchdog (main.py:5798-5836)**
- QTimer fires every 15 seconds (when event loop works)
- Writes timestamp to `logs/heartbeat.txt`
- Checks frame display timing
- Logs: `[FREEZE-WATCHDOG] GUI event loop responsive`

**Layer 2: External Watchdog (bird_watchdog.py:136-163)**
- Runs as separate process (unaffected by Qt freeze)
- Checks heartbeat file every 60 seconds
- If heartbeat > 60 seconds old → GUI is frozen
- Kills frozen process and restarts application
- Logs: `GUI FROZEN: No heartbeat for {time}s - killing frozen process`

**Implementation Details**:

```python
# main.py - Write heartbeat
def gui_watchdog_check(self):
    current_time = time.time()
    heartbeat_file = Path(__file__).parent / 'logs' / 'heartbeat.txt'
    with open(heartbeat_file, 'w') as f:
        f.write(f"{current_time}\n")
```

```python
# bird_watchdog.py - Check heartbeat
def check_application_health(self):
    if heartbeat_file.exists():
        heartbeat_timestamp = float(f.read().strip())
        time_since_heartbeat = time.time() - heartbeat_timestamp
        if time_since_heartbeat > 60:
            logger.error(f"GUI FROZEN: No heartbeat for {time_since_heartbeat:.1f}s")
            return False  # Triggers kill and restart
    return True
```

**Benefits**:
- **Detects Qt event loop freezes** that internal timers cannot catch
- **Automatic recovery** without manual intervention
- **Process-level isolation** - watchdog immune to Qt issues
- **Proven effective**: Successfully detected and restarted frozen GUI (verified 2025-11-10 15:11:42)

**Debugging Qt Event Loop Freezes**:
```bash
# Check if GUI watchdog is running (should log every 15s)
grep "FREEZE-WATCHDOG.*responsive" logs/bird_detection.log | tail -5

# Check heartbeat file age
ls -lh logs/heartbeat.txt

# Check if external watchdog detected freeze
grep "GUI FROZEN" logs/watchdog.log

# Check watchdog restart history
grep "Application is not healthy" logs/watchdog.log
```

**Freeze Type Identification Matrix**:
| Symptom | Camera HEARTBEAT | FREEZE-WATCHDOG logs | Heartbeat file | Diagnosis |
|---------|-----------------|---------------------|---------------|-----------|
| No HEARTBEAT | ❌ Missing | ❌ Missing | ❌ Stale | Camera thread died |
| HEARTBEAT shows `15s+ ago` | ✅ Present | ✅ Present | ✅ Fresh | Camera frame pipeline stall |
| HEARTBEAT OK, no WATCHDOG | ✅ Present | ❌ Missing | ❌ Stale | **Qt event loop freeze** |
| All logs present | ✅ Present | ✅ Present | ✅ Fresh | System healthy |

**When External Watchdog Detects Freeze**:
1. Watchdog logs: `GUI FROZEN: No heartbeat for {time}s`
2. Watchdog kills frozen process: `kill -9 PID`
3. Watchdog waits 5 seconds
4. Watchdog restarts application
5. New process writes fresh heartbeat
6. Monitoring continues

**Root Cause Still Unknown**:
The underlying cause of Qt event loop freezes remains unidentified. Possible culprits:
- X11/XCB display server communication issue
- PyQt6 internal deadlock
- QImage/QPixmap memory corruption
- Signal/slot connection saturation
- Main thread blocked on I/O operation

**Current Status**: System now **automatically recovers** from Qt freezes via external watchdog, meeting the "fail gracefully" requirement.

## Architecture Overview

This is an AI-powered bird photography and identification system designed for Raspberry Pi with OAK-D cameras.

### Core Components

- **main.py**: PyQt6 GUI application with tabbed interface (Camera, Gallery, Species, Services, Configuration, Logs)
- **src/camera_controller.py**: OAK-D camera interface using DepthAI, motion detection, photo capture
- **src/ai_bird_identifier.py**: OpenAI Vision API integration for species identification
- **src/drive_uploader_simple.py**: Google Drive backup functionality with multi-process worker pool
- **src/email_handler.py**: Daily/hourly summary email reports
- **src/cleanup_manager.py**: Automated cleanup of old photos based on storage limits
- **src/species_tab.py**: Species gallery UI component
- **web_interface/server.py**: Mobile-optimized Flask web interface

### Data Flow
1. OAK-D camera detects motion via frame differencing → captures photo
2. Photo saved to ~/BirdPhotos/YYYY-MM-DD/ folder structure
3. AI identifies species using OpenAI Vision API (with rate limiting: 2 min between calls)
4. Photos organized into species subfolders within date directories
5. Optional: Upload to Google Drive via worker pool (2 workers, 400ms delay between uploads)
6. Optional: Send hourly/daily email reports
7. Web interface provides mobile access to date-organized galleries

### Configuration
- **config.json**: Main configuration (auto-created from config.example.json on first run)
- **species_database.json**: Species identification cache with sightings and daily stats
- All API keys and credentials stored in config.json
- Configuration managed by `ConfigManager` class in main.py with automatic path expansion

### Key Architectural Patterns

**Motion Detection Pipeline** (src/camera_controller.py):
- `MotionDetector` class uses frame differencing with Gaussian blur
- Configurable threshold and minimum contour area
- ROI (Region of Interest) support with visual overlay
- Debounce timer prevents duplicate captures

**Multi-Process Google Drive Upload** (src/drive_uploader_simple.py):
- Worker pool architecture (2 workers) to prevent GUI freezing
- Task queue for file uploads with retry logic (max 3 retries)
- Rate limiting: 400ms minimum delay between uploads
- OAuth2 authentication with token refresh
- Upload results tracked in drive_uploads.json

**PyQt6 GUI Structure** (main.py):
- Tab-based interface with QTabWidget
- Camera preview runs in separate thread to prevent UI blocking
- ConfigManager handles all config I/O with automatic path expansion
- Gallery supports multi-select with Ctrl/Shift keyboard modifiers
- Species gallery uses local copies in ~/BirdPhotos/species/ folder

**Photo Storage Structure**:
```
~/BirdPhotos/
├── YYYY-MM-DD/           # Daily folders
│   ├── species_name/     # Species subfolders (e.g., "northern_cardinal")
│   │   └── motion_*.jpeg
│   └── unidentified/     # Failed identifications
│       └── motion_*.jpeg
└── species/              # Species gallery copies (for UI)
    └── species_name/
        └── sample_*.jpeg
```

### Dependencies
- **PyQt6**: Desktop GUI framework
- **DepthAI**: OAK camera control and pipeline creation
- **OpenCV**: Image processing and motion detection
- **Flask**: Web interface server with CORS support
- **Google API clients**: Drive upload integration
- **OpenAI API**: Vision API for bird species identification
- **psutil**: System monitoring for web interface stats

### Hardware Requirements
- Raspberry Pi 5 (4GB+ RAM recommended)
- OAK-1 or OAK-D camera (Luxonis/DepthAI compatible)
- Internet connection for AI identification

### Background Services
- **bird_watchdog.py**: Monitors main.py process and restarts on crash
- Watchdog service managed via systemd (install with install_watchdog_dynamic.sh)
- Cleanup timer in CleanupManager removes oldest files when storage limit exceeded
- Email service sends hourly reports (if enabled) and daily summaries

### Important Implementation Details

**Camera Initialization** (src/camera_controller.py):
- OAK camera takes ~60 seconds to fully initialize
- Pipeline creation uses DepthAI ColorCamera and VideoEncoder nodes
- Resolution selector supports all DepthAI formats (4K, 1080p, 720p, etc.)
- Camera controls: focus, exposure, ISO, white balance, orientation (rotate_180)

**AI Identification Rate Limiting** (src/ai_bird_identifier.py):
- 2-minute minimum between OpenAI API calls
- Daily usage tracked in species_database.json
- Base64 image encoding for API transmission
- Species data cached to reduce repeated API calls
- Configuration tab includes "Test API Connection" button to verify API key validity

**Email Service** (src/email_handler.py):
- Hourly reports with recent detections
- Daily summary at configured time (default 16:30)
- Quiet hours support (default 23:00 - 05:00)
- Gmail SMTP with app password authentication

**Web Interface Features** (web_interface/server.py):
- Mobile-optimized for iPhone 16 (2556 x 1179 px)
- Endpoint: GET /api/stats - system status and detection counts
- Endpoint: GET /api/species - species gallery data
- Endpoint: GET /images/<path> - serve images from date folders
- Date folder detection via YYYY-MM-DD format validation

**Cleanup Manager** (src/cleanup_manager.py):
- Monitors total storage size in GB
- Deletes oldest files first when max_size_gb exceeded
- Walks all subdirectories including date folders and species folders
- Runs on timer based on cleanup_time config (default 23:30)

## Critical Bug Fixes & Error Handling

### X_LINK Error Handling (Camera USB Disconnect)
**Problem**: Application would freeze when OAK camera experienced USB disconnection or X_LINK communication errors. Queue operations (preview_queue, still_queue, control_queue) could block indefinitely without detecting the disconnection.

**Solution** (src/camera_controller.py):
All methods that interact with DepthAI queues now detect X_LINK errors and raise ConnectionError:

1. **get_frame()** (lines 286-300): Detects X_LINK errors in preview frame retrieval
   ```python
   except RuntimeError as e:
       error_msg = str(e).lower()
       if ('x_link' in error_msg or 'xlink' in error_msg or
           'connection' in error_msg or 'usb' in error_msg):
           logger.error(f"X_LINK_ERROR detected: {e}")
           self._mark_disconnected()
           raise ConnectionError(f"Camera USB disconnected: {e}")
   ```

2. **get_captured_image()** (lines 462-476): X_LINK error detection for still image queue
3. **capture_still()** (lines 415-429): X_LINK error detection for capture command transmission
4. **update_camera_setting()** (lines 677-689): X_LINK error detection for camera control updates
5. **_apply_auto_exposure_region()** (lines 620-632): X_LINK error detection for AE region commands
6. **_apply_initial_settings()** (lines 272-284): X_LINK error detection during initialization
7. **process_motion()** (lines 415-420): Propagates ConnectionError from capture_still() to camera thread

**Pattern Used**:
- Catch `RuntimeError` (DepthAI's exception type for X_LINK errors)
- Check error message for keywords: 'x_link', 'xlink', 'connection', 'usb', 'device'
- Call `_mark_disconnected()` to clear stale queue references
- Raise `ConnectionError` to notify camera thread
- Camera thread (main.py lines 543+) catches ConnectionError and triggers automatic reconnection every 5 seconds

**Why This Works**: By detecting X_LINK errors early and marking the device as disconnected, we prevent indefinite blocking on queue operations. The camera thread's reconnection logic handles restoration of service without user intervention.

### GUI Freeze Fix (Frame Display)
**Problem**: GUI would freeze (display stopped updating) while backend continued to run and log events. This occurred when frame-to-QImage conversion or pixmap creation failed, causing Qt's signal/slot mechanism to silently catch exceptions and stop calling the update method.

**Solution** (main.py lines 1027-1073):
Added comprehensive error handling to `update_frame()` method in CameraTab:

```python
def update_frame(self, frame):
    """Update the camera preview with new frame"""
    try:
        # Validate frame data
        if frame is None or frame.size == 0:
            logger.warning("Received invalid frame")
            return

        # Validate dimensions
        height, width, channel = frame.shape
        if height == 0 or width == 0 or channel != 3:
            logger.error(f"Invalid frame dimensions: {height}x{width}x{channel}")
            return

        # Check for null QImage/QPixmap
        q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).rgbSwapped()
        if q_image.isNull():
            logger.error("Failed to create QImage from frame data")
            return

        pixmap = QPixmap.fromImage(q_image)
        if pixmap.isNull():
            logger.error("Failed to create QPixmap from QImage")
            return

        # Continue with display...
    except Exception as e:
        logger.error(f"Error updating frame display: {e}", exc_info=True)
```

**Key Improvements**:
- Validates frame before processing (null checks, dimension checks)
- Checks QImage.isNull() after creation
- Checks QPixmap.isNull() after creation
- Logs errors with full stack traces for debugging
- Gracefully continues even if individual frame updates fail

**Why This Works**: By catching and logging exceptions instead of letting them silently fail, the GUI continues to process subsequent frames even if one fails. The detailed logging helps diagnose the root cause of frame processing issues.

### Camera Reconnection Logic
**Implementation** (src/camera_controller.py lines 665-702):
```python
def reconnect(self, max_attempts=3, delay=2):
    """Attempt to reconnect to the camera"""
    if self.is_reconnecting:
        return False  # Prevent multiple simultaneous reconnection attempts

    self.is_reconnecting = True
    try:
        self.disconnect()  # Clean disconnect first

        for attempt in range(1, max_attempts + 1):
            time.sleep(delay)  # Wait to avoid thrashing USB bus

            if self.connect():
                logger.info("Camera reconnected successfully!")
                self.reconnect_attempts = 0
                self._post_reconnect_setup()  # Restore runtime state
                return True

        return False
    finally:
        self.is_reconnecting = False
```

**_post_reconnect_setup()** (lines 634-648): Restores camera state after reconnection
- Reapplies auto exposure region if defined
- Resets motion detector background to avoid stale frames
- Ensures ROI settings are preserved

**Why This Works**: Clean disconnect before reconnection prevents resource conflicts. Delay between attempts prevents USB bus thrashing. State restoration ensures camera operates with user's configured settings after reconnection.

### Freeze Detection Logging
**Purpose**: Comprehensive logging system to detect and diagnose GUI freezes and camera issues

**Implementation** (main.py):

**1. Camera Thread Heartbeat** (lines 495-504):
- Logs heartbeat every 30 seconds: `[HEARTBEAT] Camera thread alive`
- Reports connection status and error count
- Helps detect if camera thread has frozen or stopped

**2. Frame Emission Logging** (lines 532-534):
- Logs when frames are retrieved from camera
- Logs when frames are emitted to GUI
- Debug level logs include frame shape

**3. Frame Update Tracking** (CameraTab.update_frame, lines 1042-1061):
- Tracks time between frame updates
- Warns if gap > 5 seconds: `[FREEZE-CHECK] Long gap detected`
- Logs every 100 frames: `[FREEZE-CHECK] Frame update #100`
- Detects when update_frame stops being called

**4. Qt Image/Pixmap Creation Logging** (lines 1078-1101):
- Detailed logs at each step of frame conversion
- `[FREEZE-CHECK] Creating QImage`
- `[FREEZE-CHECK] QImage created successfully`
- `[FREEZE-CHECK] Failed to create QImage - THIS CAUSES GUI FREEZE`
- Identifies exact point of failure in display pipeline

**5. GUI Watchdog Timer** (MainWindow, lines 5319-5324, 5690-5713):
- Runs every 15 seconds in Qt event loop
- If called, confirms GUI event loop is responsive
- Checks time since last frame update
- Monitors camera thread status
- Logs: `[FREEZE-WATCHDOG] GUI event loop responsive`
- Warns if no frames for 30+ seconds

**Log Analysis for Freeze Diagnosis**:
```bash
# Check if camera thread is alive
grep "HEARTBEAT" logs/bird_detection.log

# Check frame update gaps
grep "Long gap detected" logs/bird_detection.log

# Check GUI responsiveness
grep "FREEZE-WATCHDOG" logs/bird_detection.log

# Check frame display failures
grep "Failed to create" logs/bird_detection.log

# See frame update count
grep "Frame update #" logs/bird_detection.log | tail -5
```

**Common Freeze Patterns**:
1. **Camera thread frozen**: No HEARTBEAT logs, no frame emissions
2. **Frame emission stopped**: HEARTBEAT present but no "[FRAME] emitted"
3. **GUI freeze**: No FREEZE-WATCHDOG logs (Qt event loop stopped)
4. **Display pipeline failure**: QImage/QPixmap creation fails, update_frame stops
5. **Slow updates**: Long gaps between frame updates but GUI still responsive

**Why This Works**: Multi-layer logging pinpoints exact location of freeze. Heartbeat proves thread liveness. Frame tracking shows data flow. Watchdog confirms event loop health. All timestamps enable timeline reconstruction.

## Feature Details & Implementation Guide

### 1. Motion Detection with ROI (Region of Interest)
**Location**: src/camera_controller.py (MotionDetector class, lines 19-78)

**How It Works**:
- Frame differencing: Compares current frame with previous frame using Gaussian blur
- Configurable threshold (default: 40) and minimum contour area (default: 500 pixels)
- ROI support: Only detects motion within user-defined rectangle
- Debounce timer (default: 5 seconds) prevents duplicate captures

**Key Methods**:
- `detect(frame)`: Returns (motion_detected: bool, contours: list)
- `update_settings(threshold, min_area)`: Dynamic threshold/area adjustment
- `reset()`: Clears previous frame (call after ROI changes)

**ROI Scaling** (lines 313-363):
- Handles mismatches between UI display size and camera frame size
- Automatically scales ROI coordinates to match actual frame dimensions
- Logs scaling operations for debugging

**User Interaction** (main.py CameraTab):
- Click and drag on preview to define ROI
- "Clear ROI" button removes region
- ROI saved to config.json and restored on startup
- Visual overlay shows ROI rectangle on preview

### 2. AI Bird Identification (OpenAI Vision API)
**Location**: src/ai_bird_identifier.py

**Complete Workflow**:

1. **Initialization** (lines 24-46):
   - Loads API key from config.json
   - Creates species_database.json if not exists
   - Initializes rate limiting (2 min between calls)

2. **Image Capture Callback** (main.py lines 5670-5730):
   ```python
   def on_image_captured(image_path):
       # Add to gallery immediately
       gallery_tab.add_new_image_immediately(image_path)

       # Queue for Google Drive upload
       uploader.queue_file(image_path)

       # AI identification in background thread
       if bird_identifier.enabled:
           threading.Thread(target=identify_bird, daemon=True).start()
   ```

3. **Identification Process** (lines 90-216):
   - Rate limiting check (returns early if < 2 min since last call)
   - Base64 encode image
   - Send to OpenAI Vision API with prompt requesting JSON response
   - Parse JSON from response (handles both JSON-only and text+JSON responses)
   - Extract species data: common_name, scientific_name, confidence, characteristics, behavior, conservation_status, fun_fact

4. **Result Handling**:
   - **Identified**: Record sighting, copy to IdentifiedSpecies folder, update species database
   - **Rate Limited**: Keep image, show countdown in status bar
   - **Not a bird**: Delete image to save space (configurable behavior)

5. **Species Organization** (lines 218-304):
   - Records sighting in database with timestamp, confidence, characteristics
   - Updates species info: sighting_count, last_photo, photo_gallery (keeps last 10 per species)
   - Copies photo to `/home/jaysettle/BirdPhotos/IdentifiedSpecies/{Species_Name}/`
   - Creates safe folder names (alphanumeric + underscores)

6. **Database Structure** (species_database.json):
   ```json
   {
     "species": {
       "Turdus migratorius": {
         "common_name": "American Robin",
         "scientific_name": "Turdus migratorius",
         "conservation_status": "LC",
         "characteristics": ["red breast", "gray back"],
         "fun_facts": ["State bird of Connecticut"],
         "first_seen": "2025-10-30T12:00:00",
         "sighting_count": 42,
         "last_photo": "/path/to/photo.jpeg",
         "photo_gallery": ["/path1.jpeg", "/path2.jpeg"]
       }
     },
     "sightings": [
       {
         "timestamp": "2025-10-30T12:00:00",
         "species": "Turdus migratorius",
         "confidence": 0.95,
         "image_path": "/path/to/photo.jpeg",
         "behavior": "foraging",
         "characteristics_observed": ["red breast"]
       }
     ],
     "daily_stats": {
       "2025-10-30": 15
     }
   }
   ```

**Rate Limiting Implementation**:
- Tracks `last_api_call_time` (line 172)
- Checks elapsed time before each call (lines 99-111)
- Daily API usage tracked in `daily_stats` (lines 68-79)
- Configuration: `max_images_per_hour` in config.json (not enforced, for reference only)

**Cost Management**:
- Only calls API once per photo (no retries on same image)
- 2-minute cooldown significantly reduces API usage
- Deletes non-bird images to prevent wasted storage and uploads
- Caches species data to avoid redundant lookups

### 3. Multi-Process Google Drive Upload
**Location**: src/drive_uploader_simple.py

**Architecture**:
- **Worker Pool**: 2 worker processes prevent GUI blocking
- **Task Queue**: Multiprocessing queue for file upload tasks
- **Manager Process**: SyncManager for shared state across processes
- **Rate Limiting**: 400ms minimum delay between uploads

**Upload Process**:
1. Main thread calls `queue_file(path)` (non-blocking)
2. Task added to multiprocessing queue
3. Worker process picks up task
4. Upload to Google Drive with retry logic (max 3 retries)
5. Result logged to drive_uploads.json
6. Manager tracks upload status

**OAuth2 Flow**:
- Uses `token.pickle` for stored credentials
- Automatically refreshes expired tokens
- Falls back to `credentials.json` for initial authentication
- Service account not supported (personal Google Drive only)

**Error Handling**:
- Gracefully handles missing files (already deleted by AI cleanup)
- Retries on network errors (max 3 attempts)
- Logs all upload results for auditing
- Does not block main application on upload failures

**Configuration** (config.json):
```json
{
  "services": {
    "drive_upload": {
      "enabled": false,
      "folder_name": "Bird Photos",
      "upload_delay": 3,
      "max_size_gb": 2,
      "cleanup_time": "02:00"
    }
  }
}
```

### 4. Email Notification Service
**Location**: src/email_handler.py

**Features**:
- **Startup Notification**: Sent when application starts
- **Hourly Reports**: Configurable, includes recent detections
- **Daily Summary**: Sent at configured time (default 16:30)
- **Quiet Hours**: No emails between specified hours (default 23:00 - 05:00)
- **Rate Limiting**: Prevents email spam

**Email Templates**:
1. **Startup**: "Bird detection system started at [time]"
2. **Hourly**: Last hour's detection count, sample images
3. **Daily**: Total detections, species diversity, rare sightings, storage usage

**Implementation Details**:
- Uses Gmail SMTP with app-specific password (smtp.gmail.com:465)
- Queues messages to avoid blocking
- Thread-safe message queue
- HTML email support with embedded images
- Configurable sender, receivers, and schedule

**Configuration** (config.json):
```json
{
  "email": {
    "sender": "your-email@gmail.com",
    "password": "app-specific-password",
    "receivers": {
      "primary": "recipient@gmail.com"
    },
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 465,
    "enabled": true,
    "hourly_reports": false,
    "daily_email_time": "16:30",
    "quiet_hours": {
      "start": 23,
      "end": 5
    }
  }
}
```

### 5. Species Gallery & Database
**Location**: src/species_tab.py, main.py (Species tab)

**Features**:
- Visual gallery of all identified species
- Displays: common name, scientific name, sighting count, conservation status, last seen
- Thumbnail preview with click-to-enlarge
- Species organized alphabetically
- Real-time updates when new species identified

**Implementation**:
- Loads data from species_database.json
- Uses QScrollArea for scalable display (handles 100+ species)
- Thumbnail generation with aspect ratio preservation
- Lazy loading for performance (loads thumbnails on demand)
- Species folder structure: `~/BirdPhotos/species/{species_name}/`

**Data Display**:
- Sighting count badge
- Conservation status indicator (color-coded)
- "Rare species" tag for < 3 sightings
- Last seen timestamp
- Click to view full-size image in separate window

### 6. Storage Cleanup Manager
**Location**: src/cleanup_manager.py

**How It Works**:
- **Daily Timer**: Checks at configured time (default 23:30)
- **Storage Monitoring**: Calculates total size of ~/BirdPhotos/
- **Deletion Strategy**: Oldest files first (by modification time)
- **Threshold**: Deletes files when total exceeds max_size_gb

**Cleanup Algorithm**:
1. Walk all subdirectories in ~/BirdPhotos/ (EXCEPT IdentifiedSpecies)
2. Collect all image files with metadata (size, mtime)
3. Sort by modification time (oldest first)
4. Calculate total size
5. If total > max_size_gb:
   - Delete oldest files until total <= max_size_gb
   - Log each deletion
   - Update database to remove deleted entries

**Safety Features**:
- Only deletes .jpeg, .jpg, .png files (preserves databases and configs)
- **PRESERVES IdentifiedSpecies folder** - species gallery photos are never deleted
- Skips locked/open files
- Logs all deletions for audit trail
- Only cleans date folders (YYYY-MM-DD format), not organized species folders

**Configuration** (config.json):
```json
{
  "storage": {
    "save_dir": "/home/jaysettle/BirdPhotos",
    "max_size_gb": 7,
    "cleanup_time": "23:30",
    "cleanup_enabled": true
  }
}
```

### 7. Web Interface (Mobile Access)
**Location**: web_interface/server.py

**API Endpoints**:
1. **GET /api/stats**: System status
   ```json
   {
     "status": "running",
     "uptime": "2 days",
     "total_detections": 342,
     "species_count": 15,
     "cpu_usage": 45.2,
     "memory_usage": 62.1,
     "storage_used_gb": 3.5
   }
   ```

2. **GET /api/species**: Species gallery data
   ```json
   {
     "species": [
       {
         "name": "American Robin",
         "scientific_name": "Turdus migratorius",
         "sightings": 42,
         "last_seen": "2025-10-30T12:00:00",
         "thumbnail": "/images/species/american_robin/thumb.jpeg"
       }
     ]
   }
   ```

3. **GET /api/dates**: Available date folders
4. **GET /api/photos/{date}**: Photos from specific date
5. **GET /images/{path}**: Serve image files

**Mobile Optimization**:
- Responsive design (optimized for iPhone 16: 2556 x 1179 px)
- Touch-friendly controls (44x44 minimum tap targets)
- Lazy image loading (only visible images loaded)
- Thumbnail generation for fast previews
- Swipe gestures for gallery navigation

**Security**:
- CORS enabled for local network access
- No authentication (designed for home network only)
- Read-only access (no file modifications)
- Path traversal protection

### 8. Camera Configuration & Controls
**Location**: main.py (Configuration tab), src/camera_controller.py

**Available Settings**:
1. **Focus**: Manual focus (0-255), off for infinity focus, higher for closer subjects
2. **Exposure**: Manual exposure time (0.5-10ms in 0.1ms increments)
3. **White Balance**: Color temperature in Kelvin (2000-10000)
4. **ISO**: Sensitivity range (100-3200)
5. **Sharpness**: Edge enhancement (-4 to 4)
6. **Saturation**: Color intensity (-4 to 4)
7. **Contrast**: Contrast adjustment (-4 to 4)
8. **Brightness**: Brightness adjustment (-4 to 4)
9. **Luma Denoise**: Luminance noise reduction (0-4)
10. **Chroma Denoise**: Color noise reduction (0-4)

**Resolution Settings**:
- **Capture Resolution**: 4K, 12MP, 13MP, 1080p, 720p, 5MP
- **Preview Resolution**: 1211x1013, 1250x1036, 1080p, 720p, 480p, 400p, 300p
- Note: Preview resolution affects UI display only, not saved images

**Orientation**:
- Normal or Rotate 180° (for upside-down mounting)

**Dynamic Updates**:
- Settings applied immediately via control queue
- Rate limiting prevents overwhelming camera (0.1s between commands)
- Test buttons for focus, exposure, white balance
- Visual feedback in preview

**Saved Configuration**:
- All settings saved to config.json
- Auto-loaded on application startup
- Per-camera settings supported (future: multiple cameras)

### 9. Application Window & UI
**Location**: main.py (MainWindow class, lines 5209+)

**Window Configuration**:
- **Default Size**: 1211x1013 pixels (configurable)
- **Minimum Size**: 1000x750 pixels
- **Resizable**: Yes, user can maximize or fullscreen
- **Title Format**: "Bird Detection System - {folder_name} - {time} - {dimensions}"

**Tab Structure**:
1. **Camera Tab**: Live preview, ROI controls, motion detection status
2. **Gallery Tab**: Date-organized photo viewer with multi-select
3. **Species Tab**: Species gallery with identification history
4. **Services Tab**: Enable/disable services (Drive, Email, Cleanup)
5. **Configuration Tab**: All settings with live preview
6. **Logs Tab**: Real-time log viewer with filtering

**UI Features**:
- **Clock Timer**: Updates title with current time every 10 seconds
- **Status Bar**: Shows last action, connection status, identification results
- **Keyboard Shortcuts**: Ctrl+Q (quit), Ctrl+R (reconnect camera), etc.
- **Mouse Interactions**: Click-drag for ROI, scroll-zoom (future), right-click context menus

**Theme & Styling**:
- Dark mode support (system theme detection)
- High contrast for outdoor visibility
- Monospace fonts for technical data
- Color-coded status indicators (green=good, yellow=warning, red=error)

## Window Size Configuration
The application window size is set in main.py (lines 5217-5222):
```python
# Set window size to 1211x1013
self.resize(1211, 1013)
self.setWindowTitle(f"{self.base_title} - {current_time} - 1211x1013")
self.setMinimumSize(1000, 750)
```

To change default window size:
1. Modify `self.resize(width, height)`
2. Update window title string to match
3. Optionally adjust `setMinimumSize(width, height)` for minimum constraints

## Preview Resolution vs Window Size
- **Preview Resolution** (camera_controller.py): Camera stream resolution (affects bandwidth, CPU)
- **Window Size** (main.py): GUI window dimensions (affects UI layout)
- These are independent settings
- Preview is scaled to fit window size with aspect ratio preservation

## Troubleshooting Common Issues

### Camera Not Detected
1. Check USB connection: `lsusb | grep -i luxonis`
2. Check USB speed: Should show "SuperSpeed" (USB 3.0)
3. Restart DepthAI service: `sudo systemctl restart depthai`
4. Check dmesg: `dmesg | tail -20 | grep -i usb`

### Application Freezes
- **Symptoms**: GUI stops updating, no frame updates
- **Check**: logs/bird_detection.log for errors
- **X_LINK errors**: Camera USB disconnected, will auto-reconnect
- **GUI freeze**: Frame display error, check logs for "Error updating frame display"

### AI Identification Not Working
1. Check API key: Configuration tab → Test API Connection
2. Check rate limiting: Wait 2 minutes between identifications
3. Check logs for OpenAI API errors (401 = invalid key, 429 = rate limit)
4. Verify internet connection

### High CPU Usage
- Reduce preview resolution (Configuration tab)
- Increase motion detection debounce time
- Disable real-time features (hourly emails, frequent uploads)
- Check for memory leaks: `ps aux | grep python3`

### Storage Full
- Check cleanup settings: Configuration tab → Storage
- Lower max_size_gb threshold
- Verify cleanup_time is correct
- Manual cleanup: Delete old date folders in ~/BirdPhotos/

## Development Best Practices

### Error Handling Pattern
Always handle DepthAI X_LINK errors:
```python
try:
    # DepthAI operation
    result = queue.tryGet()
except RuntimeError as e:
    error_msg = str(e).lower()
    if 'x_link' in error_msg or 'usb' in error_msg:
        self._mark_disconnected()
        raise ConnectionError(f"Camera disconnected: {e}")
    else:
        logger.error(f"Other error: {e}")
```

### GUI Threading
- **Camera Thread**: Separate QThread for frame capture (prevents blocking)
- **AI Identification**: Background daemon thread (non-blocking)
- **File Uploads**: Multiprocessing (completely isolated)
- **UI Updates**: Only from main thread via signals/slots

### Logging Best Practices
```python
logger.info("High-level operation completed")     # User-visible events
logger.debug("Detailed variable state")           # Debugging info
logger.warning("Unexpected but handled condition") # Potential issues
logger.error("Operation failed", exc_info=True)   # Errors with stack trace
```

### Configuration Updates
When adding new config options:
1. Add to config.example.json with default value
2. Document in CLAUDE.md
3. Add UI control in Configuration tab
4. Handle missing keys with `config.get('key', default)`
5. Validate values before applying

### Testing Checklist
- [ ] Camera connects successfully
- [ ] Motion detection triggers capture
- [ ] ROI selection works correctly
- [ ] AI identification returns results
- [ ] Photos saved to correct folders
- [ ] Configuration saves and loads
- [ ] Graceful handling of camera disconnect
- [ ] GUI remains responsive during operations
- [ ] Logs show expected messages

## Common Pitfalls & Solutions

### 1. UI Controls Not Applying to Camera
**Symptom**: Moving sliders changes UI labels but doesn't affect camera behavior or captured images

**Root Cause**: UI control event handlers only update labels, don't call `camera_controller.update_camera_setting()`

**Solution**: Always connect UI controls to camera controller:
```python
def on_setting_changed(self, value):
    self.label.setText(str(value))  # Update UI
    # CRITICAL: Apply to camera
    main_window = self.window()
    if hasattr(main_window, 'camera_controller'):
        main_window.camera_controller.update_camera_setting('setting_name', value)
```

**Example**: ISO sliders were only updating labels (fixed in lines 1214-1216, 1225-1227)

### 2. Hardcoded Values in Camera Settings
**Symptom**: Changing UI settings has no effect; camera uses hardcoded defaults

**Root Cause**: Camera control commands use hardcoded values instead of reading from config

**Common Locations to Check**:
- `setManualExposure(exposure_us, iso)` - Check both parameters use config/UI values
- Initial camera setup in `_apply_initial_settings()`
- Auto-exposure disable handlers

**Solution**: Always use config values:
```python
# BAD: Hardcoded ISO
ctrl.setManualExposure(exposure_us, 800)

# GOOD: Use config
iso = self.config.get('iso_max', 800)
ctrl.setManualExposure(exposure_us, iso)
```

**Example**: ISO was hardcoded to 800 in 3 locations (fixed in camera_controller.py)

### 3. Cleanup Manager Deleting Important Files
**Symptom**: Files disappear unexpectedly, species gallery is empty

**Root Cause**: Cleanup manager walks ALL subdirectories without exclusions

**Solution**: Explicitly skip folders that should be preserved:
```python
for dirpath, dirnames, filenames in os.walk(self.save_dir):
    # Skip IdentifiedSpecies folder to preserve species gallery
    if 'IdentifiedSpecies' in dirpath:
        continue
    # ... cleanup logic
```

**Example**: IdentifiedSpecies folder was being cleaned (fixed in cleanup_manager.py)

### 4. Test Buttons Not Using Current UI Values
**Symptom**: Test buttons fail even with correct values in UI fields

**Root Cause**: Test functions use stale config or require save before testing

**Solution**: Create temporary handlers with current UI values:
```python
def test_connection(self):
    # Get current UI values (don't require save)
    current_value = self.input_field.text().strip()

    # Create temporary handler with current values
    temp_config = self.config.copy()
    temp_config['setting'] = current_value
    temp_handler = Handler(temp_config)

    # Test with current values
    result = temp_handler.test()
```

**Example**: Test email and API buttons now work without saving (fixed in main.py)

### 5. Configuration Values with Whitespace
**Symptom**: Authentication fails with "invalid credentials" despite correct values

**Root Cause**: Config values saved with trailing newlines or spaces from copy/paste

**Solution**: Always strip whitespace when saving text inputs:
```python
self.config['email']['password'] = self.password_field.text().strip()
self.config['openai']['api_key'] = self.api_key_field.text().strip()
```

**Example**: Email passwords were saved with `\n` causing SMTP failures (fixed in main.py)

### 6. Slider Value Conversions
**Symptom**: Slider shows wrong value when loading config, or saved value is incorrect

**Root Cause**: Mismatch between slider units and config units (e.g., slider in 0.1ms, config in ms)

**Solution**: Convert consistently in both directions:
```python
# Loading from config (ms to slider units)
exposure_ms = config.get('exposure_ms', 2.0)
self.slider.setValue(int(exposure_ms * 10))

# Saving to config (slider units to ms)
exposure_ms = self.slider.value() / 10.0
config['exposure_ms'] = exposure_ms

# Updating label (slider units to ms)
exposure_ms = value / 10.0
self.label.setText(f"{exposure_ms:.1f}ms")
```

**Example**: Exposure slider uses 0.1ms units but config stores ms (implemented in main.py)

### 7. GUI Freezes Without Errors
**Symptom**: GUI stops updating, no errors in logs, application appears frozen

**Common Causes**:
- QImage/QPixmap creation fails silently (null objects)
- Camera USB disconnect not detected (X_LINK errors)
- Long-running operations in main thread
- Qt signal exceptions swallowed

**Debugging Steps**:
1. Check freeze detection logs: `grep "FREEZE-CHECK\|FREEZE-WATCHDOG" logs/`
2. Enable DEBUG logging for detailed frame tracking
3. Check for X_LINK errors: `grep "X_LINK\|USB" logs/`
4. Verify camera thread is alive: `grep "HEARTBEAT" logs/`

**Prevention**: See "Freeze Detection Logging" section for comprehensive monitoring

### 8. Email Password in Config Not Working
**Symptom**: Email sends fail with authentication error despite correct app password in config.json

**Common Issues**:
- Password has trailing newline: `"password": "abc123\n"`
- Password not stripped when saving from UI
- Wrong email (not Gmail) or app password not enabled

**Solution**:
1. Check config.json for `\n` at end of password string
2. Manually edit config.json to remove newline
3. Ensure `.strip()` is called when saving (fixed in main.py:4985-4987)
4. Verify Gmail has 2FA enabled and app password generated

### 9. Species Gallery Empty Despite Identifications
**Symptom**: AI identifies birds but Species tab shows no photos

**Root Causes**:
- Photos deleted by cleanup manager (most common)
- Photos not copied to IdentifiedSpecies folder
- Folder naming mismatch (underscores vs spaces)

**Solution**:
1. Verify cleanup manager skips IdentifiedSpecies (cleanup_manager.py:49-51, 64-66, 181-183)
2. Check AI identifier copies photos correctly (ai_bird_identifier.py:218-304)
3. Verify folder exists: `ls ~/BirdPhotos/IdentifiedSpecies/`

### 10. Camera Settings Not Persisting After Reconnect
**Symptom**: Camera settings reset to defaults after USB disconnect/reconnect

**Root Cause**: Settings not reapplied in `_post_reconnect_setup()`

**Solution**: Reapply all runtime settings after reconnection:
```python
def _post_reconnect_setup(self):
    """Restore camera state after reconnection"""
    # Reapply auto exposure region if defined
    if self.ae_region_start and self.ae_region_end:
        self._apply_auto_exposure_region()

    # Reset motion detector background
    if self.motion_detector:
        self.motion_detector.reset()

    # Reapply ROI, focus, exposure, etc.
    # ... restore other settings
```

**Example**: Post-reconnect setup in camera_controller.py:634-648
