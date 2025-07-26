# AI Bird Photography System

Automatically photograph and identify birds (or other things) at your bird bath or feeder using AI and computer vision.

<img width="1001" height="777" alt="image" src="https://github.com/user-attachments/assets/81bba8fe-3f49-4206-a75c-f98152286f6a" />

## What It Does

- AI identifies bird species using OpenAI Vision API
- Automatic photography with motion detection
- Photo gallery with day grouping and multi-select
- Species galleries with photo collections
- Mobile web interface for remote monitoring
- Google Drive backup (optional)
- Email reports with daily summaries (optional)
- Smart cleanup - deletes non-bird photos

## Quick Start

```bash
git clone https://github.com/jaysettle/Bird_Bath_Photography.git
cd Bird_Bath_Photography
./install.sh
python3 main.py
```
camera take a minute to initialize be patient after running python3 main.py

The app automatically creates config.json from the template on first run.

## Setup

1. Connect your OAK-1 camera
2. Run the app - it opens a GUI window
3. Go to Configuration tab to set up (Optional):
   - OpenAI API key (for bird identification)
   - Email settings (for reports)
   - Google Drive (for cloud backup)
4. Position camera 3-6 feet from your bird bath
5. View species on mobile at http://your-pi-ip:8080

## Requirements

- Raspberry Pi 4/5 (4GB+ RAM recommended)
- OAK-1 Camera (DepthAI compatible)
- Internet connection
- OpenAI API key - optional (for bird identification)

## OAK-1 Camera

https://shop.luxonis.com/products/oak-1?variant=42664380334303

## Bird Bath
<img width="287" height="392" alt="image" src="https://github.com/user-attachments/assets/6356d345-94ea-4c81-ba3b-df9c1dde2ca8" />

https://www.amazon.com/dp/B07K1WY1M4?ref_=ppx_hzsearch_conn_dt_b_fed_asin_title_2

**Key Features:**
- 12 MP central RGB camera with auto-focus and fixed-focus variants
- Global shutter option with 1 MP OV9782 sensor
- 4 TOPS of processing power (1.4 TOPS for AI)
- Dimensions: 36x54.5x27.8 mm
- Weight: 53.1g
- USB2/USB3 for power delivery and communication

## Mobile Interface

Access your bird monitoring system from your network:
- Detection statistics
- System status
- Species gallery

## Contributing

This is an open-source bird conservation project. Contributions welcome!

## License

Open source - use responsibly for bird conservation and education.

<img width="996" height="779" alt="image" src="https://github.com/user-attachments/assets/ea5ffd6c-bbd2-4da8-9cbd-1835632996ac" />
<img width="1000" height="778" alt="image" src="https://github.com/user-attachments/assets/c8121107-fb95-4e66-a152-ab1b145e9e04" />
<img width="999" height="779" alt="image" src="https://github.com/user-attachments/assets/12560abe-4195-4d65-b80c-6f8d6a688dc4" />
<img width="998" height="778" alt="image" src="https://github.com/user-attachments/assets/350f1a96-21e5-4210-8f9d-9a69c3f45eb4" />
<img width="997" height="776" alt="image" src="https://github.com/user-attachments/assets/f71e489f-d4d0-474f-932b-366e7632b5e1" />
<img width="471" height="1028" alt="image" src="https://github.com/user-attachments/assets/052da8aa-1515-4f5c-a728-31b18bddcf2b" />
<img width="486" height="1041" alt="image" src="https://github.com/user-attachments/assets/94e0b0f6-770c-4a46-9205-caa9b1a2024f" />


<img width="1684" height="950" alt="image" src="https://github.com/user-attachments/assets/9b65256a-1bbc-410a-bd42-454ae776ec02" />
<img width="1693" height="954" alt="image" src="https://github.com/user-attachments/assets/e119c462-2baf-4034-93f5-50d8ab05824b" />
<img width="1094" height="1493" alt="image" src="https://github.com/user-attachments/assets/9fbf5d48-e470-441a-8c26-23ef84ebeaf9" />

