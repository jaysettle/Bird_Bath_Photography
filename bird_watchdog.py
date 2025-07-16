#!/usr/bin/env python3
"""
Watchdog service for Bird Detection System
Monitors and restarts main.py if it stops running
"""

import os
import sys
import time
import signal
import subprocess
import logging
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/home/jaysettle/JayModel/MotionRevamp/logs/watchdog.log')
    ]
)
logger = logging.getLogger(__name__)

class BirdDetectionWatchdog:
    """Watchdog service for Bird Detection System"""
    
    def __init__(self):
        self.process = None
        self.running = True
        self.check_interval = 30  # 30 seconds
        self.restart_delay = 5    # 5 seconds
        self.max_restarts = 10    # Maximum restarts per hour
        self.restart_count = 0
        self.last_restart_time = 0
        self.working_dir = "/home/jaysettle/JayModel/MotionRevamp"
        self.script_path = os.path.join(self.working_dir, "main.py")
        
        # Ensure logs directory exists
        os.makedirs(os.path.join(self.working_dir, "logs"), exist_ok=True)
        
        logger.info("Bird Detection Watchdog initialized")
    
    def is_process_running(self):
        """Check if the main.py process is running"""
        if self.process is None:
            return False
        
        # Check if process is still running
        poll_result = self.process.poll()
        return poll_result is None
    
    def start_application(self):
        """Start the Bird Detection application"""
        try:
            if self.process and self.is_process_running():
                logger.info("Application is already running")
                return True
            
            # Check restart rate limiting
            current_time = time.time()
            if current_time - self.last_restart_time < 3600:  # Within 1 hour
                if self.restart_count >= self.max_restarts:
                    logger.error(f"Too many restarts ({self.restart_count}) in the last hour. Stopping watchdog.")
                    return False
            else:
                # Reset counter after 1 hour
                self.restart_count = 0
            
            logger.info("Starting Bird Detection application...")
            
            # Set environment variables
            env = os.environ.copy()
            env.update({
                'PYTHONPATH': self.working_dir,
                'QT_QPA_PLATFORM': 'xcb',
                'DISPLAY': ':0'
            })
            
            # Start the application
            self.process = subprocess.Popen(
                [sys.executable, self.script_path],
                cwd=self.working_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid  # Create new process group
            )
            
            self.restart_count += 1
            self.last_restart_time = current_time
            
            logger.info(f"Application started with PID: {self.process.pid}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start application: {e}")
            return False
    
    def stop_application(self):
        """Stop the Bird Detection application"""
        if self.process and self.is_process_running():
            try:
                logger.info("Stopping Bird Detection application...")
                
                # Send SIGTERM to process group
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                
                # Wait for graceful shutdown
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning("Application didn't stop gracefully, sending SIGKILL")
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    self.process.wait()
                
                logger.info("Application stopped")
                
            except Exception as e:
                logger.error(f"Error stopping application: {e}")
            
            finally:
                self.process = None
    
    def check_application_health(self):
        """Check if the application is healthy"""
        if not self.is_process_running():
            return False
        
        # Additional health checks can be added here
        # For example, check if GUI is responsive, check log files, etc.
        
        return True
    
    def restart_application(self):
        """Restart the Bird Detection application"""
        logger.info("Restarting Bird Detection application...")
        
        self.stop_application()
        time.sleep(self.restart_delay)
        
        return self.start_application()
    
    def run(self):
        """Main watchdog loop"""
        logger.info("Starting watchdog monitoring...")
        
        # Initial start
        if not self.start_application():
            logger.error("Failed to start application initially")
            return
        
        while self.running:
            try:
                time.sleep(self.check_interval)
                
                if not self.check_application_health():
                    logger.warning("Application is not healthy, restarting...")
                    
                    if not self.restart_application():
                        logger.error("Failed to restart application")
                        # Wait longer before next attempt
                        time.sleep(60)
                    else:
                        logger.info("Application restarted successfully")
                else:
                    logger.debug("Application is running normally")
                    
            except KeyboardInterrupt:
                logger.info("Watchdog interrupted by user")
                break
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
                time.sleep(self.check_interval)
        
        # Cleanup
        self.stop_application()
        logger.info("Watchdog stopped")
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

def main():
    """Main function"""
    watchdog = BirdDetectionWatchdog()
    
    # Setup signal handlers
    signal.signal(signal.SIGTERM, watchdog.signal_handler)
    signal.signal(signal.SIGINT, watchdog.signal_handler)
    
    try:
        watchdog.run()
    except Exception as e:
        logger.error(f"Watchdog crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()