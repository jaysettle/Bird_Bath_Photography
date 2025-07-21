# Bird Detection Watchdog Service

The watchdog service monitors the Bird Detection System and automatically restarts it if it crashes or stops running.

## Features

- **Automatic Monitoring**: Checks every 30 seconds if main.py is running
- **Automatic Restart**: Restarts the application if it stops or crashes
- **Rate Limiting**: Prevents too many restarts (max 10 per hour)
- **Logging**: Detailed logs of all watchdog activities
- **Graceful Shutdown**: Properly stops the application when needed
- **Process Management**: Uses proper signal handling for clean restarts

## Installation

### Option 1: Dynamic Installer (Recommended)
```bash
cd /path/to/your/bird-detection-project
./install_watchdog_dynamic.sh
```

### Option 2: Using Configuration Tab (GUI)
1. Open the Bird Detection application
2. Go to the **Configuration** tab
3. Scroll to **System Management** section
4. Click **Install Watchdog Service**
5. Follow the prompts in the terminal window

### Option 3: Manual Installation (Advanced)
```bash
cd /path/to/your/bird-detection-project
./install_watchdog.sh  # Legacy script (not recommended)
```

2. **Start the watchdog service:**
   ```bash
   sudo systemctl start bird-detection-watchdog.service
   ```

## Usage

### Basic Commands

```bash
# Start the watchdog service
sudo systemctl start bird-detection-watchdog.service

# Stop the watchdog service
sudo systemctl stop bird-detection-watchdog.service

# Check service status
sudo systemctl status bird-detection-watchdog.service

# Enable auto-start on boot
sudo systemctl enable bird-detection-watchdog.service

# Disable auto-start
sudo systemctl disable bird-detection-watchdog.service
```

### Monitoring

```bash
# View live logs
sudo journalctl -u bird-detection-watchdog.service -f

# View recent logs
sudo journalctl -u bird-detection-watchdog.service -n 50

# View watchdog-specific logs
tail -f logs/watchdog.log
```

## How It Works

1. **Monitoring**: The watchdog checks every 30 seconds if the main.py process is running
2. **Detection**: If the process is not running or has crashed, it's detected immediately
3. **Restart**: The application is restarted with proper environment variables
4. **Rate Limiting**: If too many restarts occur (>10 per hour), the watchdog stops to prevent infinite loops
5. **Logging**: All activities are logged to both systemd journal and local log files

## Configuration

The watchdog behavior can be modified in `bird_watchdog.py`:

```python
self.check_interval = 30  # Check every 30 seconds
self.restart_delay = 5    # Wait 5 seconds before restart
self.max_restarts = 10    # Maximum restarts per hour
```

## Troubleshooting

### Service Won't Start
```bash
# Check service status
sudo systemctl status bird-detection-watchdog.service

# Check logs for errors
sudo journalctl -u bird-detection-watchdog.service -n 50
```

### Application Keeps Restarting
```bash
# Check application logs
tail -f logs/bird_detection.log

# Check watchdog logs
tail -f logs/watchdog.log
```

### Stop Manual Instance First
If you're running main.py manually, stop it before starting the watchdog:
```bash
# Find and kill manual instances
ps aux | grep "python3 main.py"
kill [PID]

# Then start watchdog
sudo systemctl start bird-detection-watchdog.service
```

## Important Notes

- **Only run ONE instance**: Either run main.py manually OR use the watchdog service, not both
- **Environment Variables**: The watchdog sets proper environment variables for GUI display
- **Permissions**: The service runs as user 'jaysettle' with proper permissions
- **Logs**: Both systemd journal and local log files are used for monitoring

## Files Created

- `services/bird-detection-watchdog.service` - Systemd service file
- `bird_watchdog.py` - Main watchdog script
- `install_watchdog.sh` - Installation script
- `logs/watchdog.log` - Watchdog log file (created when service runs)