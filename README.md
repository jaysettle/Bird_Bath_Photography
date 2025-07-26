AI Bird Photography System
Automatically photograph and identify birds(or other things) at your bird bath or feeder using AI and computer vision.
What It Does
�	AI identifies bird species using OpenAI Vision API
�	Automatic photography with motion detection
�	Photo gallery with day grouping and multi-select
�	Species galleries with photo collections
�	Mobile web interface for remote monitoring
�	Google Drive backup (optional)
�	Email reports with daily summaries(optional)
�	Smart cleanup - deletes non-bird photos
Quick Start
git clone https://github.com/jaysettle/Bird_Bath_Photography.git
cd Bird_Bath_Photography
./install.sh
python3 main.py
The app automatically creates config.json from the template on first run.
Setup
1.	Connect your OAK-D camera
2.	Run the app - it opens a GUI window
3.	Go to Configuration tab to set up:(Optional)
o	OpenAI API key (for bird identification)
o	Email settings (for reports)
o	Google Drive (for cloud backup)
4.	Position camera 3 - 6  feet from your bird bath
5.	View species on mobile at http://your-pi-ip:5000

Requirements
�	Raspberry Pi 4/5 (4GB+ RAM recommended)
�	OAK-1 Camera (DepthAI compatible)
OAK-1
https://shop.luxonis.com/products/oak-1?variant=42664380334303

Key Features:
�	For 12 MP central RGB camera auto-focus and fixed-focus variants are available; there is also global shutter based option with 1 MP OV9782 sensor
�	4 TOPS of processing power (1.4 TOPS for AI)
�	Dimensions: 36x54.5x27.8 mm; Weight: 53.1g
�	USB2 / USB3 for power delivery and communication

�	Internet connection
�	OpenAI API key - optional (for bird identification)


Mobile Interface
Access your bird monitoring system from your network:
�	Detection statistics
�	System status
�	Species gallery