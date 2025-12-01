# Installation

## Requirements
- Raspberry Pi 4/5 (4GB+ RAM)
- OAK-1 Camera
- Internet connection

## Quick Install

```bash
git clone https://github.com/jaysettle/Bird_Bath_Photography.git
cd Bird_Bath_Photography
./install.sh
python3 main.py
```

## Setup

1. **Connect OAK-1 camera**
2. **Run the app** - opens GUI window
3. **Configure (optional)**:
   - OpenAI API key (Configuration tab)
   - Email settings (Configuration tab) 
   - Google Drive (Configuration tab)

## Access

- **Desktop**: Run `python3 main.py`
- **Mobile**: Open `http://your-pi-ip:8080` in browser

## Troubleshooting

- **Camera not working**: Check `lsusb | grep -i movidius`
- **Slow performance**: Disable logging in Configuration tab
- **Storage full**: Clean up photos in Gallery tab
