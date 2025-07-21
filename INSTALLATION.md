# 🐦 Bird Detection System - Installation Guide

A comprehensive AI-powered bird photography system with automatic species identification, mobile web interface, and cloud storage integration.

## 📋 System Requirements

### Hardware
- **Raspberry Pi 5** (recommended) or Pi 4 with 4GB+ RAM
- **OAK-D Camera** (DepthAI compatible)
- **32GB+ MicroSD Card** (Class 10 or better)
- **Stable internet connection**

### Operating System
- **Raspberry Pi OS** (64-bit, Bullseye or newer)
- **Ubuntu 22.04+** (alternative)

## 🚀 Quick Installation

### 1. Clone the Repository
```bash
git clone https://github.com/jaysettle/Bird_Bath_Photography.git
cd Bird_Bath_Photography
```

### 2. Run the Setup Script
```bash
chmod +x install.sh
./install.sh
```

### 3. Configure the System
```bash
# Copy example configuration
cp config.example.json config.json

# Edit configuration with your settings
nano config.json
```

### 4. Start the Application
```bash
python3 main.py
```

## 📦 Manual Installation

### Install System Dependencies
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and system packages
sudo apt install -y python3 python3-pip python3-venv git
sudo apt install -y libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev
sudo apt install -y libfontconfig1 libice6 libxrandr2 libxss1 libxtst6

# Install Qt6 dependencies
sudo apt install -y python3-pyqt6 python3-pyqt6.qtmultimedia
```

### Install Python Dependencies
```bash
# Create virtual environment (optional but recommended)
python3 -m venv bird_env
source bird_env/bin/activate

# Install requirements
pip3 install -r requirements.txt
```

### Configure OAK Camera
```bash
# Install DepthAI
pip3 install depthai

# Test camera connection
python3 -c "import depthai as dai; print('DepthAI installed successfully')"
```

## ⚙️ Configuration

### 1. Basic Configuration
Edit `config.json` with your settings:

```json
{
  "storage": {
    "save_dir": "/home/username/BirdPhotos",
    "max_size_gb": 2
  },
  "email": {
    "sender": "your-email@gmail.com",
    "password": "your-app-password"
  },
  "openai": {
    "api_key": "your-openai-key",
    "enabled": true
  }
}
```

### 2. Google Drive Setup (Optional)
```bash
# Run OAuth setup
python3 setup_google_drive.py
```

### 3. Email Configuration
- Use Gmail App Password (not your regular password)
- Get App Password: https://myaccount.google.com/apppasswords

## 🔧 Advanced Setup

### Install as System Service
```bash
# Install watchdog service
sudo ./install_watchdog_dynamic.sh

# Start service
sudo systemctl start bird-detection-watchdog
sudo systemctl enable bird-detection-watchdog
```

### Performance Optimization
- **Disable logging** in Configuration tab for better performance
- **Adjust timer frequencies** in code if needed
- **Limit concurrent processes** for low-memory systems

## 🌐 Access Methods

### Desktop Application
```bash
python3 main.py
```

### Mobile Web Interface
- Access at: `http://your-pi-ip:5000`
- View camera feed, species gallery, and stats
- Responsive design for mobile devices

### Remote Access
```bash
# Enable SSH
sudo systemctl enable ssh

# Access remotely
ssh username@your-pi-ip
```

## 🐛 Troubleshooting

### Camera Issues
```bash
# Check camera connection
lsusb | grep -i movidius

# Reset camera
sudo systemctl restart bird-detection-watchdog
```

### Performance Issues
- Disable logging in Configuration tab
- Reduce image storage limit
- Check available disk space
- Monitor CPU usage with `htop`

### Network Issues
```bash
# Check network connectivity
ping google.com

# Restart networking
sudo systemctl restart networking
```

## 📱 Mobile App Alternative

While there's no native mobile app, the web interface is fully responsive:
- **Camera preview**: Real-time bird bath monitoring
- **Species gallery**: View all identified birds
- **Statistics**: Track detection counts and storage

## 🔒 Security Notes

- **Change default passwords**
- **Use app passwords** for email (not your main password)
- **Keep API keys secure** (never commit to public repos)
- **Enable firewall** if exposing to internet

## 🆔 Features Overview

- 🤖 **AI Bird Identification** using OpenAI Vision API
- 📸 **Automatic Photography** with motion detection
- 🖼️ **Species Galleries** with thumbnail grids
- ☁️ **Google Drive Backup** with automatic uploads
- 📧 **Email Notifications** with hourly reports
- 📱 **Mobile Web Interface** for remote monitoring
- 🗑️ **Smart Storage Management** auto-deletes non-bird images
- ⚡ **Performance Controls** with logging toggle
- 📊 **Statistics Dashboard** with detection metrics
- 🔄 **Automatic Restart** with watchdog service

## 💡 Tips for Best Results

1. **Position camera** 6-8 feet from bird bath
2. **Ensure good lighting** (avoid backlighting)
3. **Keep lens clean** for better AI recognition
4. **Monitor storage space** regularly
5. **Use logging toggle** to optimize performance
6. **Check hourly email reports** for activity summary

## 🤝 Contributing

Contributions welcome! Please read the code and submit pull requests for improvements.

## 📄 License

Open source project - use responsibly and ethically for bird conservation and education.