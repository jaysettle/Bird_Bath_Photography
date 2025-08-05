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
python3 main.py              # Start main GUI application
cd web_interface && python3 server.py  # Start mobile web interface
```

### Services & Background Processes
```bash
./install_watchdog.sh        # Install system service for automatic startup
systemctl start bird-detection-watchdog
systemctl status bird-detection-watchdog
```

### Web Interface
- Main app runs Flask server on port 5000
- Mobile interface in `web_interface/` directory
- Access via http://hostname:5000 or http://hostname:8080

## Architecture Overview

This is an AI-powered bird photography and identification system designed for Raspberry Pi with OAK-D cameras.

### Core Components

- **main.py**: PyQt6 GUI application with tabbed interface (Camera, Gallery, Species, Services, Configuration, Logs)
- **src/camera_controller.py**: OAK-D camera interface using DepthAI, motion detection, photo capture
- **src/ai_bird_identifier.py**: OpenAI Vision API integration for species identification
- **src/drive_uploader_simple.py**: Google Drive backup functionality
- **src/email_handler.py**: Daily summary email reports
- **src/cleanup_manager.py**: Automated cleanup of non-bird photos
- **web_interface/server.py**: Mobile-optimized Flask web interface

### Data Flow
1. OAK-D camera detects motion → captures photo
2. AI identifies species using OpenAI Vision API
3. Photos organized by date/species in ~/BirdPhotos/
4. Optional: Upload to Google Drive, send email reports
5. Web interface provides mobile access to galleries

### Configuration
- **config.json**: Main configuration (created from config.example.json)
- **species_database.json**: Species identification cache
- All API keys and credentials stored in config.json

### Dependencies
- PyQt6 for desktop GUI
- DepthAI for OAK camera control
- OpenCV for image processing
- Flask for web interface
- Google API clients for Drive integration
- OpenAI API for bird identification

### Hardware Requirements
- Raspberry Pi 5 (4GB+ RAM recommended)
- OAK-1 or OAK-D camera (Luxonis/DepthAI compatible)
- Internet connection for AI identification

### Photo Storage Structure
```
~/BirdPhotos/
├── YYYY-MM-DD/           # Daily folders
│   ├── species_name/     # Species subfolders
│   └── unidentified/     # Failed identifications
└── species/              # Species gallery copies
```

### Background Services
- Watchdog service monitors main process
- Cleanup timer service removes old non-bird photos
- systemd integration for automatic startup