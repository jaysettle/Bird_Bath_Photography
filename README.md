# 🐦 AI Bird Photography System

Automatically photograph and identify birds at your bird bath using AI and computer vision.

![Features](https://img.shields.io/badge/Features-AI%20Identification-blue) ![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi-red) ![Mobile](https://img.shields.io/badge/Mobile-Web%20Interface-green)

## ✨ What It Does

- 🤖 **AI identifies bird species** using OpenAI Vision API
- 📸 **Automatic photography** with motion detection  
- 🖼️ **Species galleries** with photo collections
- 📱 **Mobile web interface** for remote monitoring
- ☁️ **Google Drive backup** (optional)
- 📧 **Email reports** with daily summaries
- 🗑️ **Smart cleanup** - deletes non-bird photos

## 🚀 Quick Start

```bash
git clone https://github.com/jaysettle/Bird_Bath_Photography.git
cd Bird_Bath_Photography
./install.sh
python3 main.py
```

That's it! The app creates all config files automatically.

## 🎛️ Setup

1. **Connect your OAK-D camera**
2. **Run the app** - it opens a GUI window
3. **Go to Configuration tab** to set up:
   - OpenAI API key (for bird identification)
   - Email settings (for reports)  
   - Google Drive (for cloud backup)
4. **Position camera** 6-8 feet from your bird bath
5. **View species** on mobile at `http://your-pi-ip:5000`

No JSON editing required - everything is configured through the GUI!

## 📋 Requirements

- **Raspberry Pi 4/5** (4GB+ RAM recommended)
- **OAK-D Camera** (DepthAI compatible)
- **Internet connection**
- **OpenAI API key** (for bird identification)

## 🎯 Key Features

| Feature | Description |
|---------|-------------|
| 🔍 **Motion Detection** | Automatic bird photography with ROI selection |
| 🤖 **AI Identification** | Species recognition with confidence scores |
| 📊 **Statistics** | Track species diversity and counts |
| 🔄 **Auto-Restart** | Watchdog service keeps system running |
| ⚡ **Performance** | Logging toggle for optimal speed |
| 🛡️ **Resilient** | Continues working even if services fail |

## 📱 Mobile Interface

Access your bird monitoring system from anywhere:
- Real-time camera preview
- Species photo galleries  
- Detection statistics
- System status

## 🤝 Contributing

This is an open-source bird conservation project. Contributions welcome!

## 📄 License

Open source - use responsibly for bird conservation and education.

---

**🔧 Need help?** Check `INSTALLATION.md` for detailed setup instructions.