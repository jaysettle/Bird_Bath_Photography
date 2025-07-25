# AI Bird Photography System

Automatically photograph and identify birds at your bird bath using AI and computer vision.

## What It Does

- AI identifies bird species using OpenAI Vision API
- Local pre-filtering to reduce API calls by ~90%
- Automatic photography with motion detection  
- Photo gallery with day grouping and multi-select
- Species galleries with photo collections
- Mobile web interface for remote monitoring
- Google Drive backup (optional)
- Email reports with daily summaries
- Smart cleanup - deletes non-bird photos
- Experimental batch processing tools

## Quick Start

```bash
git clone https://github.com/jaysettle/Bird_Bath_Photography.git
cd Bird_Bath_Photography
./install.sh
python3 main.py
```

The app automatically creates `config.json` from the template on first run.

## Setup

1. Connect your OAK-D camera
2. Run the app - it opens a GUI window
3. Go to Configuration tab to set up:
   - OpenAI API key (for bird identification)
   - Email settings (for reports)  
   - Google Drive (for cloud backup)
4. Position camera 6-8 feet from your bird bath
5. View species on mobile at http://your-pi-ip:5000

No JSON editing required - everything is configured through the GUI.

## Requirements

- Raspberry Pi 4/5 (4GB+ RAM recommended)
- OAK-D Camera (DepthAI compatible)
- Internet connection
- OpenAI API key (for bird identification)

## Key Features

| Feature | Description |
|---------|-------------|
| Motion Detection | Automatic bird photography with ROI selection |
| AI Identification | Species recognition with confidence scores |
| Photo Gallery | Browse all photos with thumbnails and day grouping |
| Statistics | Track species diversity and counts |
| Auto-Restart | Watchdog service keeps system running |
| Performance | Logging toggle for optimal speed |
| Resilient | Continues working even if services fail |
| Batch Tools | Experimental app for filtering non-bird photos |

## Mobile Interface

Access your bird monitoring system from your network:  
- Detection statistics
- System status

## Contributing

This is an open-source bird conservation project. Contributions welcome!

## License

Open source - use responsibly for bird conservation and education.

---

Need help? Check INSTALLATION.md for detailed setup instructions.
