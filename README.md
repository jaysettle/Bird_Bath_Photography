# Bird Detection System

A comprehensive bird detection and monitoring system using OAK-D camera with PyQt6 GUI, automatic Google Drive uploads, and email notifications.

## Features

### 🎥 **Camera & Detection**
- **OAK-D Camera Integration** - 4K image capture with DepthAI
- **Motion Detection** - Configurable sensitivity and area thresholds
- **ROI Selection** - Drag-to-select region of interest on preview
- **Real-time Preview** - Live camera feed with motion detection overlay

### 🌙 **Modern UI**
- **Dark Theme** - Professional dark mode interface
- **Tabbed Interface** - Camera, Services, and Logs tabs
- **Interactive Controls** - Sliders for camera settings and motion detection
- **Real-time Status** - Live monitoring of all services

### 📤 **Cloud Integration**
- **Google Drive Upload** - Automatic image uploads to specified folder
- **Email Notifications** - Motion capture alerts with attachments
- **Hourly Reports** - Summary emails with captured images

### 🔧 **System Management**
- **Service Monitoring** - Real-time status of all system services
- **Storage Management** - Automatic cleanup and space monitoring
- **Configuration UI** - Easy toggle switches for all features
- **Watchdog Service** - Automatic restart on crashes

## Quick Start

### Prerequisites
- Raspberry Pi (tested on Pi 5)
- OAK-D camera
- Python 3.8+
- PyQt6
- Google Drive API credentials (optional)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/bird-detection-system.git
   cd bird-detection-system
   ```

2. **Install system dependencies:**
   ```bash
   sudo apt update
   sudo apt install python3-pyqt6 python3-systemd python3-watchdog
   ```

3. **Install Python dependencies:**
   ```bash
   pip3 install -r requirements.txt
   ```

4. **Configure the system:**
   - Edit `config.json` with your email settings
   - Add Google Drive service account credentials (optional)
   - Adjust camera and motion detection settings

5. **Run the application:**
   ```bash
   python3 main.py
   ```

### Watchdog Service (Optional)

For 24/7 operation with automatic restart:

```bash
# Install the watchdog service
./install_watchdog.sh

# Start the watchdog
sudo systemctl start bird-detection-watchdog.service
```

## Configuration

### Email Settings
Update `config.json` with your email configuration:
```json
{
  "email": {
    "sender": "your-email@gmail.com",
    "password": "your-app-password",
    "receivers": {
      "primary": "recipient@gmail.com"
    }
  }
}
```

### Google Drive Setup
1. Create a Google Cloud project
2. Enable Google Drive API
3. Create a service account
4. Download `service_account.json` to project root
5. Enable drive upload in `config.json`

### Camera Settings
- **Exposure**: Auto or manual control
- **ISO**: Min/max range settings
- **Focus**: Auto or manual focus
- **Resolution**: 4K capture mode

### Motion Detection
- **Sensitivity**: Threshold for motion detection
- **Min Area**: Minimum area for motion triggers
- **ROI**: Drag rectangle on preview to set region
- **Debounce**: Delay between captures

## Architecture

```
├── main.py                 # Main application with PyQt6 GUI
├── src/
│   ├── camera_controller.py    # OAK-D camera management
│   ├── drive_uploader_simple.py # Google Drive integration
│   ├── email_handler.py        # Email notifications
│   ├── cleanup_manager.py      # Storage cleanup
│   └── logger.py              # Logging utilities
├── services/               # Systemd service files
├── config.json            # Main configuration
└── bird_watchdog.py       # Watchdog service
```

## Usage

### Basic Operation
1. **Start the application** - `python3 main.py`
2. **Set ROI** - Drag on camera preview to select detection area
3. **Adjust settings** - Use sliders to fine-tune detection
4. **Monitor services** - Check Services tab for status
5. **View logs** - Real-time logs in Logs tab

### Service Management
- **Toggle uploads** - Enable/disable Google Drive in Services tab
- **Email settings** - Configure notifications and reports
- **Storage cleanup** - Automatic old file removal
- **System monitoring** - Service status and queue sizes

## Troubleshooting

### Common Issues

**Camera not detected:**
```bash
# Check camera connection
lsusb | grep -i luxonis
```

**Email not working:**
- Verify Gmail app password
- Check SMTP settings in config
- Review email logs

**Drive upload failing:**
- Check service account permissions
- Verify storage quota
- Review drive folder permissions

### Logs
- **Application logs**: `logs/bird_detection.log`
- **Watchdog logs**: `logs/watchdog.log`
- **System logs**: `sudo journalctl -u bird-detection-watchdog.service`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- **DepthAI** for OAK-D camera support
- **PyQt6** for the GUI framework
- **Google Drive API** for cloud storage
- **Raspberry Pi Foundation** for the hardware platform