#!/usr/bin/env python3
"""
Bird Detection System - Main Application with PyQt6 GUI
"""

import sys
import os
import json
import time
import threading
import subprocess
from datetime import datetime, date, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# PyQt6 imports
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, 
                           QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton,
                           QTextEdit, QGroupBox, QGridLayout, QCheckBox, QSpinBox,
                           QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
                           QComboBox,
                           QSizePolicy,
                           QSplitter, QFrame, QLineEdit, QTimeEdit, QFileDialog, 
                           QMessageBox, QScrollArea, QDialog)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot, QMutex, QPoint, QRect, QUrl, QTime
from PyQt6.QtGui import QPixmap, QImage, QFont, QPalette, QColor, QPainter, QPen, QMouseEvent, QDesktopServices
import cv2
import numpy as np

# Local imports
from src.config_manager import ConfigManager
from src.ui.themes import apply_dark_theme
from src.ui.preview_widgets import InteractivePreviewLabel
from src.ui.logs_tab import LogsTab
from src.ui.dialogs import ImageViewerDialog
from src.ui.services_tab import ServicesTab
from src.ui.config_tab import ConfigTab
from src.ui.gallery_tab import GalleryTab
from src.ui.camera_tab import CameraTab
from src.threads import CameraThread, ServiceMonitor, DriveStatsMonitor, GalleryLoader
from src.logger import setup_logging, setup_gui_logging, get_logger, log_buffer
from src.camera_controller import CameraController
from src.email_handler import EmailHandler
from src.drive_uploader_simple import CombinedUploader
from src.ai_bird_identifier import AIBirdIdentifier
from src.weather_service import WeatherService
from src.species_tab import SpeciesTab
from src.cleanup_manager import CleanupManager
# Removed bird_prefilter import

# Set up logging with configuration
config_path = os.path.join(os.path.dirname(__file__), 'config.json')
setup_logging(config_path)
setup_gui_logging()
logger = get_logger(__name__)
logger.info("Bird Bath Photography application started")


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        current_dir = Path(__file__).parent.name
        self.base_title = f"Bird Detection System - {current_dir}"

        # Set window size to 1211x1013
        self.resize(1211, 1013)

        # Set initial title with dimensions
        current_time = datetime.now().strftime("%H:%M:%S")
        self.setWindowTitle(f"{self.base_title} - {current_time} - 1211x1013")
        # Remove fixed size constraint to allow manual fullscreen/maximize
        self.setMinimumSize(1000, 750)  # Set minimum instead of fixed
        
        # Clock timer
        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(10000)  # Update every 10 seconds to reduce CPU load
        
        # Cleanup timer - check every minute if it's time to clean
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self.check_cleanup_time)
        self.cleanup_timer.start(60000)  # Check every minute
        self.last_cleanup_date = None

        # Weather check timer - check every minute (actual API call respects check_interval)
        self.weather_timer = QTimer()
        self.weather_timer.timeout.connect(self.check_weather)
        self.weather_timer.start(60000)  # Check every minute

        # GUI Freeze Detection Watchdog
        self.gui_watchdog_timer = QTimer()
        self.gui_watchdog_timer.timeout.connect(self.gui_watchdog_check)
        self.gui_watchdog_timer.start(15000)  # Check every 15 seconds
        self.last_gui_check = time.time()
        logger.info("[FREEZE-WATCHDOG] GUI watchdog timer initialized")
        
        # Load configuration
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        
        # Initialize services
        self.init_services()
        
        # Setup UI
        self.setup_ui()
        
        # Setup timers
        self.setup_timers()
        
        # Start services
        self.start_services()
        
        logger.info("Main window initialized")
    
    
    def init_services(self):
        """Initialize all services"""
        # Camera controller
        self.camera_controller = CameraController(self.config)
        
        # Email handler
        self.email_handler = EmailHandler(self.config)
        
        # Upload service
        self.uploader = CombinedUploader(self.config)
        
        # AI Bird Identifier (Day 1 Feature)
        self.bird_identifier = AIBirdIdentifier(self.config)
        
        # Cleanup manager for automatic storage cleanup
        self.cleanup_manager = CleanupManager(self.config)

        # Weather service for rain detection
        weather_config = self.config.get('weather', {})
        self.weather_service = WeatherService(weather_config)

        # Bird Pre-filter Service
        # Removed bird prefilter initialization

        # Service monitor
        self.service_monitor = ServiceMonitor()
        
        # Camera thread
        self.camera_thread = None
        
        # Mobile web server
        self.web_server_process = None
    
    def setup_ui(self):
        """Setup the main UI"""
        # Create central widget and tab widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        
        # Create tabs
        self.tab_widget = QTabWidget()
        
        # Camera tab
        self.camera_tab = CameraTab(self.camera_controller, self.config)
        self.tab_widget.addTab(self.camera_tab, "Camera")
        
        # Gallery tab (position #2)
        self.gallery_tab = GalleryTab(self.config)
        self.gallery_tab.email_handler = self.email_handler
        self.tab_widget.addTab(self.gallery_tab, "Gallery")
        
        # Services tab
        self.services_tab = ServicesTab(self.email_handler, self.uploader, self.config, self.bird_identifier)
        self.tab_widget.addTab(self.services_tab, "Services")
        
        # Species tab
        self.species_tab = SpeciesTab(self.bird_identifier)
        self.tab_widget.addTab(self.species_tab, "Species")
        
        # Configuration tab
        self.config_tab = ConfigTab(self.config_manager)
        self.tab_widget.addTab(self.config_tab, "Configuration")
        
        # Logs tab
        self.logs_tab = LogsTab()
        self.tab_widget.addTab(self.logs_tab, "Logs")
        
        # Connect tab change handler for lazy loading
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        
        layout.addWidget(self.tab_widget)
        
        # Status bar
        self.statusBar().showMessage("Initializing...")
    
    def on_tab_changed(self, index):
        """Handle tab change - lazy load gallery when first accessed"""
        # Check if this is the gallery tab (index 1)
        if index == 1 and hasattr(self, 'gallery_tab') and not self.gallery_tab.gallery_loaded:
            logger.info("Loading gallery for first time")
            self.gallery_tab.load_today_photos()
            self.gallery_tab.gallery_loaded = True
        
        # Check if this is the species tab (index 3) - refresh data when shown
        elif index == 3 and hasattr(self, 'species_tab'):
            self.species_tab.needs_refresh = True
            # Trigger showEvent manually since PyQt may not always call it
            self.species_tab.load_species()
    
    def setup_timers(self):
        """Setup update timers"""
        # Status update timer for frequently changing items
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(5000)  # Update every 5 seconds
        
        # Slow update timer for storage and watchdog (less frequent)
        self.slow_timer = QTimer()
        self.slow_timer.timeout.connect(self.update_slow_status)
        self.slow_timer.start(30000)  # Update every 30 seconds
        
        # Memory cleanup timer (every 5 minutes)
        self.memory_cleanup_timer = QTimer()
        self.memory_cleanup_timer.timeout.connect(self.periodic_memory_cleanup)
        self.memory_cleanup_timer.start(300000)  # Every 5 minutes
        
        # Store all timers for cleanup
        self.active_timers = [self.status_timer, self.slow_timer, self.memory_cleanup_timer]
    
    def periodic_memory_cleanup(self):
        """Periodic memory cleanup to prevent leaks"""
        try:
            import gc
            import psutil
            import os
            
            # Get current memory usage
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            # Check gallery image count
            gallery_images = 0
            if hasattr(self, 'images_by_date'):
                gallery_images = sum(len(images) for images in self.images_by_date.values())
            
            # Force garbage collection
            collected = gc.collect()
            
            # Log memory status
            if memory_mb > 300:  # Warning if over 300MB
                logger.warning(f"High memory usage: {memory_mb:.1f}MB, gallery has {gallery_images} images, collected {collected} objects")
                
                # If memory is very high, suggest clearing old gallery data
                if memory_mb > 500 and gallery_images > 200:
                    logger.critical(f"CRITICAL: Memory usage {memory_mb:.1f}MB with {gallery_images} gallery images!")
                    # Could auto-clear oldest date here if needed
                    
            elif memory_mb > 200:
                logger.info(f"Memory usage: {memory_mb:.1f}MB, gallery has {gallery_images} images")
            else:
                logger.debug(f"Memory usage OK: {memory_mb:.1f}MB, collected {collected} objects")
                
        except Exception as e:
            logger.error(f"Error during periodic memory cleanup: {e}")
    
    def cleanup_timers(self):
        """Stop and cleanup all timers"""
        timers_to_stop = []
        
        # Collect all timer attributes
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if isinstance(attr, QTimer):
                timers_to_stop.append((attr_name, attr))
        
        # Stop all timers
        for name, timer in timers_to_stop:
            try:
                if timer.isActive():
                    timer.stop()
                    logger.info(f"Stopped timer: {name}")
            except Exception as e:
                logger.error(f"Error stopping timer {name}: {e}")
        
        # Also check services tab if it exists
        if hasattr(self, 'services_tab'):
            if hasattr(self.services_tab, 'cleanup'):
                self.services_tab.cleanup()
    
    def start_services(self):
        """Start all services"""
        try:
            # Start camera
            if self.camera_controller.connect():
                self.camera_thread = CameraThread(self.camera_controller)
                self.camera_thread.frame_ready.connect(self.camera_tab.update_frame)
                self.camera_thread.image_captured.connect(self.on_image_captured)
                # Connect USB disconnect/reconnect signals
                self.camera_thread.connection_lost.connect(self.camera_tab.on_camera_disconnected)
                self.camera_thread.connection_restored.connect(self.camera_tab.on_camera_reconnected)
                self.camera_thread.start()
                logger.info("Camera service started with USB disconnect handling")
            else:
                logger.error("Failed to start camera service")
            
            # Start email service
            self.email_handler.start()
            
            # Start upload service (non-critical, don't crash if it fails)
            try:
                self.uploader.start()
            except Exception as e:
                logger.error(f"Drive uploader failed to start (non-fatal): {e}")
                # Continue running without drive uploads
            
            # Start service monitor
            self.service_monitor.service_status_updated.connect(
                self.services_tab.update_service_status
            )
            self.service_monitor.start()
            
            self.statusBar().showMessage("All services started")
            logger.info("All services started successfully")
            
            # Start mobile web server
            self.start_web_server()
            
            # Initial slow status update
            self.update_slow_status()
            
        except Exception as e:
            logger.error(f"Failed to start services: {e}")
            self.statusBar().showMessage(f"Error starting services: {e}")
    
    def start_web_server(self):
        """Start the mobile web server"""
        try:
            # Kill any existing web server processes first
            try:
                import psutil
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        if proc.info['name'] == 'python3' and proc.info['cmdline']:
                            # Check if it's running our web server
                            cmdline = ' '.join(proc.info['cmdline'])
                            if 'web_interface/server.py' in cmdline:
                                logger.info(f"Killing existing web server process {proc.info['pid']}")
                                proc.terminate()
                                proc.wait(timeout=3)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                        pass
            except ImportError:
                # psutil not available, try alternative method
                try:
                    subprocess.run(['pkill', '-f', 'web_interface/server.py'], check=False)
                except:
                    pass
            
            # Wait a moment for processes to die
            time.sleep(1)
            
            # Start web server in background
            web_server_path = Path(__file__).parent / "web_interface" / "server.py"
            
            # Check if server.py exists
            if not web_server_path.exists():
                logger.error(f"Web server script not found: {web_server_path}")
                return
            
            logger.info(f"Starting web server: {web_server_path}")
            self.web_server_process = subprocess.Popen(
                [sys.executable, str(web_server_path)],
                cwd=str(web_server_path.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Read output to get the actual port
            server_port = 8080  # default
            start_time = time.time()
            while time.time() - start_time < 5:  # Wait up to 5 seconds
                if self.web_server_process.poll() is not None:
                    # Process exited
                    stdout, stderr = self.web_server_process.communicate()
                    error_msg = stderr.strip()
                    logger.error(f"Web server failed to start: {error_msg}")
                    
                    # Set failure message in Services tab
                    if hasattr(self, 'services_tab'):
                        self.services_tab.set_mobile_url(None)
                    
                    self.mobile_url = None
                    return
                
                # Try to read stdout for port info
                try:
                    import select
                    if select.select([self.web_server_process.stdout], [], [], 0.1)[0]:
                        line = self.web_server_process.stdout.readline()
                        if line and "Starting server on port" in line:
                            # Extract port number
                            import re
                            match = re.search(r'port (\d+)', line)
                            if match:
                                server_port = int(match.group(1))
                                logger.info(f"Web server using port {server_port}")
                                break
                except:
                    pass
                
                time.sleep(0.1)
            
            # Check if process is still running
            if self.web_server_process.poll() is not None:
                stdout, stderr = self.web_server_process.communicate()
                logger.error(f"Web server failed: {stderr}")
                if hasattr(self, 'services_tab'):
                    self.services_tab.set_mobile_url(None)
                self.mobile_url = None
                return
            
            # Get IP address
            import socket
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            
            # Try to get actual IP (not localhost)
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
            except:
                pass
            
            self.mobile_url = f"http://{local_ip}:{server_port}"
            logger.info(f"Mobile web server started at {self.mobile_url}")
            
            # Update Services tab with URL
            if hasattr(self, 'services_tab'):
                self.services_tab.set_mobile_url(self.mobile_url)
                
        except Exception as e:
            logger.error(f"Failed to start web server: {e}")
            self.mobile_url = None
    
    def update_status(self):
        """Update frequently changing status information"""
        self.services_tab.update_upload_status()
        self.services_tab.update_email_status()
    
    def update_slow_status(self):
        """Update slow/blocking status information"""
        self.services_tab.update_storage_status()
        self.services_tab.update_watchdog_status()
    
    def update_clock(self):
        """Update window title with current time and dimensions"""
        current_time = datetime.now().strftime("%H:%M:%S")
        width = self.width()
        height = self.height()
        self.setWindowTitle(f"{self.base_title} - {current_time} - {width}x{height}")

    def gui_watchdog_check(self):
        """Check if GUI event loop is responsive - detects freezes"""
        current_time = time.time()
        time_since_last = current_time - self.last_gui_check

        # If this method is called, it means Qt's event loop is still running
        logger.info(f"[FREEZE-WATCHDOG] GUI event loop responsive - interval: {time_since_last:.1f}s")

        # Write heartbeat file for external watchdog monitoring
        try:
            heartbeat_file = Path(__file__).parent / 'logs' / 'heartbeat.txt'
            with open(heartbeat_file, 'w') as f:
                f.write(f"{current_time}\n")
        except Exception as e:
            logger.error(f"[FREEZE-WATCHDOG] Failed to write heartbeat file: {e}")

        # Check if camera thread is sending frames
        if hasattr(self, 'camera_tab') and hasattr(self.camera_tab, 'last_frame_update_time'):
            time_since_frame = current_time - self.camera_tab.last_frame_update_time
            if time_since_frame > 30:
                logger.warning(f"[FREEZE-WATCHDOG] No frame updates for {time_since_frame:.1f}s - possible GUI display freeze!")
                # Force camera reconnect to try to unstick the system
                if hasattr(self, 'camera_controller') and self.camera_controller.is_connected():
                    logger.error(f"[FREEZE-WATCHDOG] Forcing camera reconnect to recover from display freeze")
                    try:
                        self.camera_controller.disconnect()
                    except Exception as e:
                        logger.error(f"[FREEZE-WATCHDOG] Failed to disconnect camera: {e}")
            elif time_since_frame > 10:
                logger.info(f"[FREEZE-WATCHDOG] Slow frame updates: {time_since_frame:.1f}s since last frame")

        # Check camera thread status
        if hasattr(self, 'camera_thread') and self.camera_thread:
            if self.camera_thread.isRunning():
                logger.debug(f"[FREEZE-WATCHDOG] Camera thread running")
            else:
                logger.error(f"[FREEZE-WATCHDOG] Camera thread NOT running!")

        self.last_gui_check = current_time

    def resizeEvent(self, event):
        """Handle window resize events to update dimensions in title"""
        super().resizeEvent(event)
        # Update title with new dimensions immediately
        current_time = datetime.now().strftime("%H:%M:%S")
        width = self.width()
        height = self.height()
        self.setWindowTitle(f"{self.base_title} - {current_time} - {width}x{height}")
    
    def check_cleanup_time(self):
        """Check if it's time to run storage cleanup"""
        
        # Check if cleanup is enabled
        cleanup_enabled = self.config.get('storage', {}).get('cleanup_enabled', False)
        if not cleanup_enabled:
            return
        
        # Get configured cleanup time
        cleanup_time_str = self.config.get('storage', {}).get('cleanup_time', '23:30')
        hour, minute = map(int, cleanup_time_str.split(':'))
        
        now = datetime.now()
        today = date.today()
        
        # Log check (only log once per minute to avoid spam)
        if not hasattr(self, '_last_cleanup_log_minute') or self._last_cleanup_log_minute != now.minute:
            self._last_cleanup_log_minute = now.minute
            logger.debug(f"Checking cleanup time: current={now.strftime('%H:%M')}, scheduled={cleanup_time_str}, last_run={self.last_cleanup_date}")
        
        # Check if we haven't cleaned up today and it's past the cleanup time
        if self.last_cleanup_date != today and now.hour == hour and now.minute >= minute:
            logger.info(f"Running scheduled cleanup at {cleanup_time_str}")
            self.last_cleanup_date = today
            
            # Run cleanup in background
            try:
                result = self.cleanup_manager.cleanup_old_files()
                if result['cleaned']:
                    logger.info(f"Cleanup completed: deleted {result['files_deleted']} files, freed {result['space_freed']/(1024*1024):.1f}MB")
                    # Show notification in status bar
                    if hasattr(self, 'statusBar'):
                        self.statusBar().showMessage(f"Storage cleanup: {result['files_deleted']} files deleted", 5000)
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")
    
    def check_weather(self):
        """Check weather and pause motion detection if raining"""
        if not self.weather_service.enabled:
            return

        # Only check if enough time has passed (respects check_interval)
        if self.weather_service.should_check_weather():
            is_raining = self.weather_service.check_weather()

            # Get pause_on_rain setting from config
            weather_config = self.config.get('weather', {})
            pause_on_rain = weather_config.get('pause_on_rain', True)

            # Check if override is active in camera tab
            override_active = False
            if hasattr(self, 'camera_tab') and hasattr(self.camera_tab, 'weather_override_cb'):
                override_active = self.camera_tab.weather_override_cb.isChecked()

            # Update camera controller pause state (only if override not active)
            if pause_on_rain and is_raining and not override_active:
                if not self.camera_controller.motion_paused:
                    self.camera_controller.motion_paused = True
                    self.camera_controller.pause_reason = f"Rain: {self.weather_service.weather_description}"
                    logger.info(f"[WEATHER] Motion detection PAUSED - {self.weather_service.weather_description}")
                    self.statusBar().showMessage(f"Motion paused: {self.weather_service.weather_description}")
            else:
                if self.camera_controller.motion_paused and "Rain" in self.camera_controller.pause_reason:
                    self.camera_controller.motion_paused = False
                    self.camera_controller.pause_reason = ""
                    logger.info("[WEATHER] Motion detection RESUMED - weather cleared")
                    self.statusBar().showMessage("Motion detection resumed - weather cleared")

            # Update camera tab UI if it has weather display
            if hasattr(self, 'camera_tab') and hasattr(self.camera_tab, 'update_weather_status'):
                self.camera_tab.update_weather_status(self.weather_service.get_status())

    def run_cleanup_now(self):
        """Run storage cleanup manually"""
        try:
            logger.info("Running manual storage cleanup...")
            result = self.cleanup_manager.cleanup_old_files()
            
            if result['cleaned']:
                msg = f"Cleanup completed!\n\nDeleted {result['files_deleted']} files\nFreed {result['space_freed']/(1024*1024):.1f}MB\nCurrent size: {result['current_size']:.2f}GB"
                QMessageBox.information(self, "Cleanup Complete", msg)
            else:
                msg = f"No cleanup needed.\n\nCurrent size: {result['current_size']:.2f}GB\nLimit: {self.config['storage']['max_size_gb']}GB"
                QMessageBox.information(self, "Storage OK", msg)
                
        except Exception as e:
            logger.error(f"Manual cleanup failed: {e}")
            QMessageBox.critical(self, "Cleanup Failed", f"Storage cleanup failed:\n{str(e)}")
    
    def on_image_captured(self, image_path):
        """Handle image capture"""
        logger.info(f"Image captured: {image_path}")
        
        # Update camera tab stats
        if hasattr(self, 'camera_tab'):
            self.camera_tab.on_photo_captured()
            self.camera_tab.on_motion_detected()  # Photo capture means motion was detected
        
        # Add to gallery immediately
        if hasattr(self, 'gallery_tab') and self.gallery_tab:
            self.gallery_tab.add_new_image_immediately(image_path)
        
        # Queue for upload
        self.uploader.queue_file(image_path)
        
        # AI Bird Identification (Day 1 Feature)
        if self.bird_identifier.enabled:
            # Run identification in a separate thread to avoid blocking
            def identify_bird():
                
                result = self.bird_identifier.identify_bird(image_path)
                if result:
                    if result.get('rate_limited'):
                        # Rate limited - keep the image for later
                        wait_time = result.get('wait_time', 0)
                        logger.info(f"Rate limited: Keeping image for later. Next call in {wait_time:.0f}s")
                        self.statusBar().showMessage(
                            f"Rate limit: Next bird ID in {wait_time:.0f}s - Image saved"
                        )
                    elif result.get('identified'):
                        species = result.get('species_common', 'Unknown')
                        confidence = result.get('confidence', 0)
                        is_rare = self.bird_identifier.check_rare_species(
                            result.get('species_scientific', '')
                        )
                        
                        status_msg = f"Identified: {species} (confidence: {confidence:.0%})"
                        if is_rare:
                            status_msg += " - RARE SPECIES!"
                        
                        logger.info(status_msg)
                        self.statusBar().showMessage(status_msg)
                        
                        # Refresh species tab
                        if hasattr(self, 'species_tab'):
                            self.species_tab.load_species()
                    else:
                        # No bird detected by OpenAI - delete the image to save space
                        try:
                            os.remove(image_path)
                            logger.info(f"Deleted non-bird image: {os.path.basename(image_path)}")
                            self.statusBar().showMessage("No bird detected - image deleted")
                            
                            # Also remove from upload queue if present
                            if hasattr(self.uploader, 'drive_uploader') and self.uploader.drive_uploader:
                                # The image might already be queued for upload
                                pass  # Upload queue will handle missing files gracefully
                        except Exception as e:
                            logger.error(f"Error deleting non-bird image: {e}")
            
            threading.Thread(target=identify_bird, daemon=True).start()
        
        # Email notifications are sent via hourly reports only
        # Individual motion capture emails are disabled
        
        self.statusBar().showMessage(f"Image captured: {os.path.basename(image_path)}")
    
    def closeEvent(self, event):
        """Handle application close"""
        logger.info("Shutting down application...")
        
        try:
            # Comprehensive cleanup
            self.cleanup_application()
            
            # Make sure Qt application closes
            QApplication.processEvents()
            
            # Accept the event first
            event.accept()
            
            # Add a small delay to ensure cleanup completes
            QApplication.processEvents()
            
            # Force quit the application
            QApplication.quit()
            
            # Give Qt a moment to process
            import time
            time.sleep(0.1)
            
            logger.info("Application cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during application close: {e}")
        finally:
            # If still not closed, force exit
            import os
            import sys
            logger.info("Force terminating application")
            
            # Kill any remaining Python processes for this application
            try:
                import psutil
                current_process = psutil.Process()
                logger.info(f"Terminating process {current_process.pid}")
                current_process.terminate()
            except ImportError:
                pass
            
            # Final force exit
            os._exit(0)
    
    def resizeEvent(self, event):
        """Handle window resize events"""
        super().resizeEvent(event)

        # Preview is now fixed size - no scaling on window resize
        logger.debug(f"Window resized to {event.size().width()}x{event.size().height()}")
    
    def cleanup_application(self):
        """Comprehensive cleanup of all resources"""
        try:
            logger.info("Starting application cleanup...")
            
            # Stop camera thread
            if hasattr(self, 'camera_thread') and self.camera_thread:
                logger.info("Stopping camera thread...")
                self.camera_thread.stop()
                if not self.camera_thread.wait(2000):  # Wait up to 2 seconds
                    logger.warning("Camera thread did not stop gracefully")
            
            # Stop all timers
            logger.info("Stopping all timers...")
            self.cleanup_timers()
            
            # Stop camera controller
            if hasattr(self, 'camera_controller') and self.camera_controller:
                logger.info("Disconnecting camera controller...")
                self.camera_controller.disconnect()
            
            # Stop email handler
            if hasattr(self, 'email_handler') and self.email_handler:
                logger.info("Stopping email handler...")
                self.email_handler.stop()
            
            # Stop uploader
            if hasattr(self, 'uploader') and self.uploader:
                logger.info("Stopping uploader...")
                self.uploader.stop()
            
            # Stop service monitor
            if hasattr(self, 'service_monitor') and self.service_monitor:
                logger.info("Stopping service monitor...")
                self.service_monitor.stop()
            
            # Stop web server process if running
            if hasattr(self, 'web_server_process') and self.web_server_process:
                logger.info("Terminating web server...")
                self.web_server_process.terminate()
                self.web_server_process.wait()
            
            # Close all child windows/dialogs
            for widget in QApplication.topLevelWidgets():
                if widget != self:
                    widget.close()
            
            # Force garbage collection
            import gc
            gc.collect()
            
            logger.info("Application cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        
        # Clean up services tab background threads
        if hasattr(self, 'services_tab'):
            self.services_tab.cleanup()
        
        # Clean up camera tab
        if hasattr(self, 'camera_tab'):
            self.camera_tab.cleanup()
        
        # Stop web server
        if hasattr(self, 'web_server_process') and self.web_server_process:
            logger.info("Stopping mobile web server...")
            self.web_server_process.terminate()
            try:
                self.web_server_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.web_server_process.kill()
        
        event.accept()
        logger.info("Application closed")

def main():
    """Main function"""
    # Set environment variables
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    os.environ["DISPLAY"] = ":0"
    
    # Fix Qt runtime directory permissions if needed
    try:
        import stat
        runtime_dir = "/run/user/1000"
        if os.path.exists(runtime_dir):
            current_perms = oct(stat.S_IMODE(os.stat(runtime_dir).st_mode))
            if current_perms != '0o700':
                os.chmod(runtime_dir, 0o700)
    except Exception:
        pass  # Ignore permission errors
    
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Apply dark theme
    apply_dark_theme(app)
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Run application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
