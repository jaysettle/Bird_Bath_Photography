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

class ConfigManager:
    """Manages configuration loading and saving"""
    
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        self.config_path = config_path
        self.config = {}
        self.load_config()
    
    def load_config(self):
        """Load configuration from file"""
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            # Convert any ~ paths to absolute paths
            self._expand_paths()
        except FileNotFoundError:
            # config.json doesn't exist - create it from config.example.json or defaults
            print("INFO: config.json not found, creating from template...")
            
            # Try to load from config.example.json as template
            example_path = self.config_path.replace('config.json', 'config.example.json')
            try:
                with open(example_path, 'r') as f:
                    self.config = json.load(f)
                    print("INFO: Loaded configuration template from config.example.json")
                    
                    # Clear sensitive fields for new users
                    if 'email' in self.config:
                        self.config['email']['sender'] = ''
                        self.config['email']['password'] = ''
                    if 'openai' in self.config:
                        self.config['openai']['api_key'] = ''
                        
            except FileNotFoundError:
                # No example file either - use hardcoded defaults
                print("INFO: No config.example.json found, using hardcoded defaults")
                self.config = self._get_default_config()
                
            # Expand paths for the loaded config
            self._expand_paths()
            
            # Automatically save as config.json for future use
            try:
                with open(self.config_path, 'w') as f:
                    json.dump(self.config, f, indent=4)
                print("INFO: Created config.json with default configuration")
                print("INFO: Please configure your API keys in the Configuration tab")
            except Exception as e:
                print(f"ERROR: Failed to create config.json: {e}")
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = self._get_default_config()
            self._expand_paths()
    
    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            raise Exception(f"Failed to save config: {e}")
    
    def _expand_paths(self):
        """Expand ~ and environment variables in paths"""
        if 'storage' in self.config and 'save_dir' in self.config['storage']:
            # Handle ~ for home directory
            path = self.config['storage']['save_dir']
            if path.startswith('~'):
                self.config['storage']['save_dir'] = str(Path(path).expanduser())
            # Handle relative paths by making them absolute
            elif not os.path.isabs(path):
                self.config['storage']['save_dir'] = str(Path(path).absolute())
    
    def _get_default_config(self):
        """Get default configuration"""
        return {
            "camera": {
                "resolution": "4k",
                "socket": "rgb",
                "preview_width": 600,
                "preview_height": 400,
                "orientation": "rotate_180",
                "focus": 132,
                "exposure_ms": 20,
                "iso_min": 100,
                "iso_max": 800,
                "white_balance": 6208,
                "threshold": 37,
                "min_area": 500
            },
            "motion_detection": {
                "threshold": 50,
                "min_area": 500,
                "debounce_time": 5.0,
                "default_roi": {
                    "enabled": True,
                    "x": 43,
                    "y": 177,
                    "width": 699,
                    "height": 287
                }
            },
            "storage": {
                "save_dir": "~/BirdPhotos",
                "max_size_gb": 2,
                "cleanup_time": "23:30"
            },
            "email": {
                "sender": "",
                "password": "",
                "receivers": {"primary": ""},
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 465,
                "hourly_report": True,
                "daily_email_time": "16:30",
                "quiet_hours": {"start": 23, "end": 5}
            },
            "services": {
                "drive_upload": {
                    "enabled": False,
                    "folder_name": "Bird Photos",
                    "upload_delay": 3
                },
                "cleanup": {
                    "enabled": True,
                    "schedule": "daily"
                }
            },
            "logging": {
                "level": "INFO",
                "max_log_size": "10MB",
                "backup_count": 5,
                "journal_integration": True
            },
            "ui": {
                "window_title": "Bird Detection System",
                "tabs": ["Camera", "Services", "Configuration", "Logs"],
                "refresh_rate": 30
            },
            "openai": {
                "api_key": "",
                "enabled": False,
                "max_images_per_hour": 10
            }
        }

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
from src.logger import setup_logging, setup_gui_logging, get_logger, log_buffer
from src.camera_controller import CameraController
from src.email_handler import EmailHandler
from src.drive_uploader_simple import CombinedUploader
from src.ai_bird_identifier import AIBirdIdentifier
from src.species_tab import SpeciesTab
from src.cleanup_manager import CleanupManager
# Removed bird_prefilter import

# Set up logging with configuration
config_path = os.path.join(os.path.dirname(__file__), 'config.json')
setup_logging(config_path)
setup_gui_logging()
logger = get_logger(__name__)
logger.info("Bird Bath Photography application started")

class InteractivePreviewLabel(QLabel):
    """Custom QLabel that handles mouse events for ROI selection and focus control"""
    roi_selected = pyqtSignal(QPoint, QPoint)
    focus_point_clicked = pyqtSignal(QPoint)  # Signal for right-click focus
    
    def __init__(self):
        super().__init__()
        # Default camera preview dimensions
        self.base_width = 600
        self.base_height = 400
        self.aspect_ratio = self.base_width / self.base_height
        
        # Zoom functionality
        self.zoom_factor = 1.0
        self.min_zoom = 0.5
        self.max_zoom = 3.0
        self.zoom_step = 0.1
        self.current_width = self.base_width
        self.current_height = self.base_height
        
        self.setFixedSize(self.base_width, self.base_height)
        self.setStyleSheet("border: 2px solid #555555; background-color: #252525; border-radius: 6px;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("Camera Preview")
        self.setScaledContents(False)  # No scaling - show at natural size
        
        # ROI selection state
        self.drawing = False
        self.has_dragged = False
        self.potential_roi_start = QPoint()
        self.roi_start = QPoint()
        self.roi_end = QPoint()
        self.roi_rect = QRect()
        self.current_pixmap = None
        
        # Focus indicator
        self.focus_click_point = None
        self.focus_indicator_timer = QTimer()
        self.focus_indicator_timer.timeout.connect(self.clear_focus_indicator)
        self.focus_indicator_timer.setSingleShot(True)
        
        # Right-click drag prevention
        self.right_button_pressed = False
        self.right_click_start = None
        self.drag_threshold = 5  # pixels
    
    def scale_for_fullscreen(self, is_fullscreen=False):
        """Scale the preview size based on window state"""
        if is_fullscreen:
            # Scale up to 1.5x size in fullscreen
            self.base_width = 900
            self.base_height = 600
        else:
            # Use base size for windowed mode
            self.base_width = 600
            self.base_height = 400
        
        # Apply current zoom to new base size
        self.update_size()
        logger.debug(f"Preview base scaled to {self.base_width}x{self.base_height} (fullscreen: {is_fullscreen})")
    
    def wheelEvent(self, event):
        """Handle mouse wheel for zooming"""
        # Get wheel delta
        delta = event.angleDelta().y()
        
        if delta > 0:
            # Zoom in
            new_zoom = min(self.zoom_factor + self.zoom_step, self.max_zoom)
        else:
            # Zoom out
            new_zoom = max(self.zoom_factor - self.zoom_step, self.min_zoom)
        
        if new_zoom != self.zoom_factor:
            self.zoom_factor = new_zoom
            self.update_size()
            logger.debug(f"Zoom changed to {self.zoom_factor:.1f}x")
    
    def update_size(self):
        """Update the widget size based on current zoom factor"""
        old_width = getattr(self, 'current_width', self.base_width)
        old_height = getattr(self, 'current_height', self.base_height)
        
        self.current_width = int(self.base_width * self.zoom_factor)
        self.current_height = int(self.base_height * self.zoom_factor)
        self.setFixedSize(self.current_width, self.current_height)
        
        # Scale ROI if it exists and size changed
        if not self.roi_rect.isEmpty() and (old_width != self.current_width or old_height != self.current_height):
            self.scale_roi(old_width, old_height, self.current_width, self.current_height)
    
    def reset_zoom(self):
        """Reset zoom to 1.0x"""
        self.zoom_factor = 1.0
        self.update_size()
        logger.info("Preview zoom reset to 1.0x")

    def set_preview_resolution(self, resolution):
        """Update preview widget size based on camera resolution"""
        # Map resolution to appropriate display size
        resolution_display_map = {
            'THE_1211x1013': (605, 506),   # Scale down by ~2x for display
            'THE_1250x1036': (625, 518),   # Scale down by 2x for display
            'THE_1080_P': (640, 360),       # Scale 1920x1080 to fit
            'THE_720_P': (640, 360),        # Scale 1280x720
            'THE_480_P': (640, 480),        # Keep 640x480
            'THE_400_P': (640, 400),        # Keep 640x400
            'THE_300_P': (640, 300)         # Keep 640x300
        }

        # Get display dimensions for this resolution
        display_width, display_height = resolution_display_map.get(resolution, (605, 506))

        # Update base dimensions
        self.base_width = display_width
        self.base_height = display_height
        self.aspect_ratio = self.base_width / self.base_height

        # Apply zoom and update size
        self.update_size()

        logger.info(f"Preview widget size updated to {display_width}x{display_height} for resolution {resolution}")
    
    def scale_roi(self, old_width, old_height, new_width, new_height):
        """Scale ROI coordinates when preview size changes"""
        if not self.roi_rect.isEmpty():
            # Calculate scaling factors
            scale_x = new_width / old_width
            scale_y = new_height / old_height
            
            # Scale ROI rectangle
            scaled_x = int(self.roi_rect.x() * scale_x)
            scaled_y = int(self.roi_rect.y() * scale_y)
            scaled_width = int(self.roi_rect.width() * scale_x)
            scaled_height = int(self.roi_rect.height() * scale_y)
            
            # Update ROI rectangle
            old_rect = self.roi_rect
            self.roi_rect = QRect(scaled_x, scaled_y, scaled_width, scaled_height)
            
            # Trigger repaint to show updated ROI
            self.update()
            
            # Emit signal to update camera controller with new coordinates
            self.roi_selected.emit(QPoint(scaled_x, scaled_y), QPoint(scaled_x + scaled_width, scaled_y + scaled_height))
            
            logger.debug(f"ROI scaled from {old_rect} to {self.roi_rect} (preview: {old_width}x{old_height} -> {new_width}x{new_height})")
        
    def heightForWidth(self, width):
        """Maintain 16:9 aspect ratio (locked)"""
        return int(width * 9 / 16)
        
    def mousePressEvent(self, event):
        """Handle mouse press for ROI selection or focus control"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Store the start position but don't start drawing yet
            # Only draw if there's a significant drag
            self.potential_roi_start = event.pos()
            self.has_dragged = False
        elif event.button() == Qt.MouseButton.RightButton:
            # Right-click for focus control - track for drag detection
            self.right_button_pressed = True
            self.right_click_start = event.pos()
            # Don't emit focus signal yet - wait for release to distinguish from drag
            
    def mouseMoveEvent(self, event):
        """Handle mouse move for ROI selection"""
        if event.buttons() & Qt.MouseButton.LeftButton and hasattr(self, 'potential_roi_start'):
            # Check if we've dragged far enough to start ROI drawing
            if not self.drawing:
                distance = ((event.pos().x() - self.potential_roi_start.x()) ** 2 + 
                           (event.pos().y() - self.potential_roi_start.y()) ** 2) ** 0.5
                if distance > 10:  # Require at least 10 pixel drag to start drawing
                    self.drawing = True
                    self.has_dragged = True
                    self.roi_start = self.potential_roi_start
                    self.roi_end = event.pos()
                    self.update()
            else:
                # Already drawing, update endpoint
                self.roi_end = event.pos()
                self.update()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release events"""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.drawing:
                # We were drawing an ROI
                self.drawing = False
                self.roi_end = event.pos()
                self.update()
                
                # Only emit ROI if the drawn area is significant
                width = abs(self.roi_end.x() - self.roi_start.x())
                height = abs(self.roi_end.y() - self.roi_start.y())
                if width > 20 and height > 20:  # Minimum 20x20 pixel ROI
                    # Emit ROI selected signal
                    self.roi_selected.emit(self.roi_start, self.roi_end)
                else:
                    # Too small, don't change ROI
                    self.update()
            # Reset drag tracking
            self.has_dragged = False
            
        elif event.button() == Qt.MouseButton.RightButton and self.right_button_pressed:
            self.right_button_pressed = False
            
            # Check if this was a click (not a drag)
            if self.right_click_start:
                distance = ((event.pos().x() - self.right_click_start.x()) ** 2 + 
                           (event.pos().y() - self.right_click_start.y()) ** 2) ** 0.5
                
                if distance <= self.drag_threshold:
                    # This was a click, not a drag - emit focus signal
                    self.focus_click_point = self.right_click_start
                    self.focus_indicator_timer.start(2000)  # Show indicator for 2 seconds
                    self.update()
                    self.focus_point_clicked.emit(self.right_click_start)
                    logger.info(f"Focus point clicked at: {self.right_click_start.x()}, {self.right_click_start.y()}")
                
            self.right_click_start = None
    def paintEvent(self, event):
        """Custom paint event to draw ROI rectangle and focus indicator"""
        super().paintEvent(event)
        
        if self.current_pixmap:
            painter = QPainter(self)
            
            # Draw the current ROI rectangle
            if not self.roi_rect.isEmpty():
                painter.setPen(QPen(QColor(0, 255, 100), 3))  # Bright green rectangle
                painter.drawRect(self.roi_rect)
                
                # Draw ROI label with background for better visibility
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.setBrush(QColor(0, 255, 100, 180))
                label_rect = QRect(self.roi_rect.topLeft() + QPoint(5, -20), QPoint(self.roi_rect.topLeft().x() + 85, self.roi_rect.topLeft().y() - 5))
                painter.drawRect(label_rect)
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.drawText(self.roi_rect.topLeft() + QPoint(8, -8), "MOTION ROI")
            
            # Draw temporary rectangle while drawing
            if self.drawing:
                painter.setPen(QPen(QColor(255, 255, 0), 2))  # Yellow while drawing
                temp_rect = QRect(self.roi_start, self.roi_end)
                painter.drawRect(temp_rect.normalized())
            
            # Focus click indicator removed per user request
                
            painter.end()
    
    def setPixmap(self, pixmap):
        """Override setPixmap to store current pixmap"""
        self.current_pixmap = pixmap
        super().setPixmap(pixmap)
    
    def clear_focus_indicator(self):
        """Clear the focus click indicator"""
        self.focus_click_point = None
        self.update()
    
        
    def clear_roi(self):
        """Clear the ROI rectangle"""
        self.roi_rect = QRect()
        self.drawing = False  # Reset drawing state
        self.has_dragged = False
        self.potential_roi_start = QPoint()
        self.roi_start = QPoint()
        self.roi_end = QPoint()
        self.update()
    
    def set_roi_rect(self, x, y, width, height):
        """Set the ROI rectangle programmatically"""
        self.roi_rect = QRect(x, y, width, height)
        self.update()

class CameraThread(QThread):
    """Thread for camera operations"""
    frame_ready = pyqtSignal(np.ndarray)
    motion_detected = pyqtSignal(list)
    image_captured = pyqtSignal(str)
    connection_lost = pyqtSignal()  # Signal when connection is lost
    connection_restored = pyqtSignal()  # Signal when connection is restored

    def __init__(self, camera_controller):
        super().__init__()
        self.camera_controller = camera_controller
        self.running = False
        self.mutex = QMutex()
        self.connection_error_count = 0
        self.last_reconnect_attempt = 0
        self.reconnect_interval = 5  # Seconds between reconnection attempts
        
    def run(self):
        """Main camera loop with USB disconnect handling"""
        self.running = True
        was_connected = True
        last_heartbeat = time.time()
        heartbeat_interval = 30  # Log heartbeat every 30 seconds
        last_successful_frame = time.time()
        frame_timeout = 15  # Force reconnect if no frames processed for 15 seconds
        consecutive_frame_failures = 0
        max_frame_failures = 5  # Trigger reconnect after 5 consecutive frame failures

        while self.running:
            try:
                # Heartbeat logging to detect thread freeze
                current_time = time.time()
                if current_time - last_heartbeat >= heartbeat_interval:
                    logger.info(f"[HEARTBEAT] Camera thread alive - connected: {self.camera_controller.is_connected()}, errors: {self.connection_error_count}, frames_ok: {time.time() - last_successful_frame:.1f}s ago")
                    last_heartbeat = current_time

                # Detect stalled frame processing - GUI may have frozen
                time_since_frame = current_time - last_successful_frame
                if time_since_frame > frame_timeout and self.camera_controller.is_connected():
                    logger.error(f"[FREEZE-DETECT] No frames processed for {time_since_frame:.1f}s - forcing camera reconnect to recover")
                    # Force reconnection to unstick the system
                    self.camera_controller.disconnect()
                    was_connected = False
                    consecutive_frame_failures = 0
                    continue

                # Check if camera is connected
                if not self.camera_controller.is_connected():
                    if was_connected:
                        logger.warning("Camera disconnected - attempting reconnection")
                        self.connection_lost.emit()
                        was_connected = False

                    # Attempt reconnection if enough time has passed
                    current_time = time.time()
                    if current_time - self.last_reconnect_attempt >= self.reconnect_interval:
                        self.last_reconnect_attempt = current_time

                        if self.camera_controller.reconnect():
                            logger.info("Camera reconnected successfully")
                            self.connection_restored.emit()
                            was_connected = True
                            self.connection_error_count = 0
                            last_successful_frame = time.time()  # Reset frame timer
                            consecutive_frame_failures = 0
                        else:
                            logger.warning(f"Reconnection failed, will retry in {self.reconnect_interval} seconds")

                    self.msleep(1000)  # Wait 1 second before next iteration
                    continue

                # Get frame
                frame = self.camera_controller.get_frame()
                if frame is not None:
                    logger.debug(f"[FRAME] Got frame, shape: {frame.shape}, emitting to GUI")
                    self.frame_ready.emit(frame.copy())
                    logger.debug(f"[FRAME] Frame emitted successfully")
                    self.connection_error_count = 0  # Reset error count on successful frame
                    last_successful_frame = time.time()  # Update last successful frame time
                    consecutive_frame_failures = 0  # Reset failure counter

                    # Process motion detection
                    if self.camera_controller.process_motion(frame):
                        # Motion was detected and capture triggered
                        pass

                    # Normal frame rate when frames are available
                    self.msleep(33)  # ~30 FPS
                else:
                    # No frame available - could indicate problem
                    consecutive_frame_failures += 1
                    if consecutive_frame_failures >= max_frame_failures:
                        logger.warning(f"[FREEZE-DETECT] {consecutive_frame_failures} consecutive frame failures - possible camera stall")
                        # Don't force disconnect yet, just warn

                    # Longer delay when no frames available
                    self.msleep(200)  # 5 FPS polling rate

                # Check for captured images
                captured_image = self.camera_controller.get_captured_image()
                if captured_image:
                    self.image_captured.emit(captured_image)

            except ConnectionError as e:
                # Handle X_LINK/USB disconnect errors
                logger.error(f"Camera connection error: {e}")
                self.connection_error_count += 1

                if self.connection_error_count == 1:
                    logger.warning("Camera USB disconnected - will attempt automatic reconnection")
                    self.connection_lost.emit()
                    was_connected = False

                self.msleep(1000)  # Wait before retry

            except Exception as e:
                logger.error(f"Error in camera thread: {e}")
                self.msleep(100)
    
    def stop(self):
        """Stop the camera thread"""
        self.running = False
        self.wait()

class ServiceMonitor(QThread):
    """Thread for monitoring system services"""
    service_status_updated = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.running = False
        self.services = [
            'cleanup.service',
            'bird-detection-watchdog.service'
        ]
    
    def run(self):
        """Monitor services"""
        self.running = True
        
        while self.running:
            try:
                status = {}
                for service in self.services:
                    try:
                        result = subprocess.run(
                            ['systemctl', 'is-active', service],
                            capture_output=True, text=True, timeout=5
                        )
                        status[service] = result.stdout.strip()
                    except Exception as e:
                        status[service] = 'unknown'
                        logger.debug(f"Error checking {service}: {e}")
                
                self.service_status_updated.emit(status)
                
                # Check every 5 seconds
                if self.running:
                    self.msleep(5000)
                    
            except Exception as e:
                logger.error(f"Error in service monitor: {e}")
                self.msleep(1000)
    
    def stop(self):
        """Stop the service monitor"""
        self.running = False
        self.wait()

class DriveStatsMonitor(QThread):
    """Monitor Google Drive folder statistics in background"""
    drive_stats_updated = pyqtSignal(dict)
    
    def __init__(self, uploader):
        super().__init__()
        self.uploader = uploader
        self.running = False
        
    def run(self):
        """Monitor Drive stats"""
        self.running = True
        while self.running:
            try:
                if (hasattr(self.uploader, 'drive_uploader') and 
                    self.uploader.drive_uploader and 
                    self.uploader.drive_uploader.enabled):
                    
                    logger.debug("DriveStatsMonitor: Fetching stats...")
                    try:
                        stats = self.uploader.drive_uploader.get_drive_folder_stats()
                        logger.debug(f"DriveStatsMonitor: Got stats: {stats}")
                        self.drive_stats_updated.emit(stats)
                    except Exception as e:
                        logger.debug(f"DriveStatsMonitor: Failed to get stats: {e}")
                        # Emit empty stats on error
                        self.drive_stats_updated.emit({
                            'file_count': 0,
                            'total_size': 0,
                            'latest_file': None,
                            'latest_upload_time': None
                        })
                else:
                    # Emit empty stats if Drive not enabled
                    self.drive_stats_updated.emit({
                        'file_count': 0,
                        'total_size': 0,
                        'latest_file': None,
                        'latest_upload_time': None
                    })
                
                # Check every 30 seconds to reduce CPU load
                if self.running:
                    self.msleep(30000)
                    
            except Exception as e:
                logger.error(f"Error in Drive stats monitor: {e}")
                self.msleep(5000)  # Wait 5 seconds on error
    
    def stop(self):
        """Stop the Drive stats monitor"""
        self.running = False
        self.wait()

class CameraTab(QWidget):
    """Camera control and preview tab"""
    
    def __init__(self, camera_controller, config):
        super().__init__()
        self.camera_controller = camera_controller
        self.config = config
        self.current_frame = None
        self.roi_drawing = False
        self.roi_start = None
        self.roi_end = None
        
        # Stats tracking
        self.session_capture_count = 0
        self.last_capture_time = None
        self.motion_event_count = 0
        self.daily_motion_events = 0
        
        self.setup_ui()
        self.load_default_roi()
        self.load_camera_settings()
        
    def setup_ui(self):
        """Setup the camera tab UI"""
        main_layout = QVBoxLayout()

        # Connection status indicator
        self.connection_status_label = QLabel("🟢 Camera Connected")
        self.connection_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_status_label.setStyleSheet("""
            QLabel {
                background-color: #2E7D32;
                color: white;
                padding: 5px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 11px;
            }
        """)
        self.connection_status_label.hide()  # Initially hidden
        main_layout.addWidget(self.connection_status_label)

        # Top section - Preview sized to actual image
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        # Camera preview label - centered
        preview_center_layout = QHBoxLayout()
        preview_center_layout.addStretch()

        self.preview_label = InteractivePreviewLabel()
        # Set initial preview size based on camera resolution
        camera_res = getattr(self.camera_controller, 'preview_resolution', 'THE_1211x1013')
        self.preview_label.set_preview_resolution(camera_res)
        self.preview_label.roi_selected.connect(self.on_roi_selected)
        self.preview_label.focus_point_clicked.connect(self.on_focus_point_clicked)
        preview_center_layout.addWidget(self.preview_label)
        
        preview_center_layout.addStretch()
        preview_layout.addLayout(preview_center_layout)
        
        # Bottom section - Controls adapt to preview width
        bottom_panel = QWidget()
        bottom_panel.setMaximumHeight(350)
        bottom_layout = QHBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(5, 5, 5, 5)
        bottom_layout.setSpacing(5)
        
        # Left column for camera and motion controls
        left_column = QWidget()
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)
        
        # Right column for motion settings and actions
        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)
        
        # Camera controls - compact version
        camera_group = QGroupBox("Camera")
        camera_layout = QGridLayout()
        camera_layout.setSpacing(2)
        camera_layout.setContentsMargins(5, 5, 5, 5)
        
        # Focus slider
        camera_layout.addWidget(QLabel("Focus:"), 0, 0)
        self.focus_slider = QSlider(Qt.Orientation.Horizontal)
        self.focus_slider.setRange(0, 255)
        self.focus_slider.setValue(128)
        self.focus_slider.valueChanged.connect(self.on_focus_changed)
        camera_layout.addWidget(self.focus_slider, 0, 1)
        self.focus_value = QLabel("128")
        camera_layout.addWidget(self.focus_value, 0, 2)
        
        # Exposure slider
        camera_layout.addWidget(QLabel("Exposure:"), 1, 0)
        self.exposure_slider = QSlider(Qt.Orientation.Horizontal)
        # Range: 5-100 (represents 0.5ms to 10ms in 0.1ms increments)
        self.exposure_slider.setRange(5, 100)
        self.exposure_slider.setValue(20)
        self.exposure_slider.valueChanged.connect(self.on_exposure_changed)
        camera_layout.addWidget(self.exposure_slider, 1, 1)
        self.exposure_value = QLabel("2.0ms")
        camera_layout.addWidget(self.exposure_value, 1, 2)
        
        # Auto exposure checkbox
        self.auto_exposure_cb = QCheckBox("Auto Exposure")
        self.auto_exposure_cb.setChecked(True)
        self.auto_exposure_cb.stateChanged.connect(self.on_auto_exposure_changed)
        camera_layout.addWidget(self.auto_exposure_cb, 2, 0, 1, 3)
        
        # White balance slider
        camera_layout.addWidget(QLabel("White Balance:"), 3, 0)
        self.wb_slider = QSlider(Qt.Orientation.Horizontal)
        self.wb_slider.setRange(2000, 7500)
        self.wb_slider.setValue(6637)
        self.wb_slider.valueChanged.connect(self.on_wb_changed)
        camera_layout.addWidget(self.wb_slider, 3, 1)
        self.wb_value = QLabel("6637K")
        camera_layout.addWidget(self.wb_value, 3, 2)
        
        # Brightness slider
        camera_layout.addWidget(QLabel("Brightness:"), 4, 0)
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(-10, 10)
        self.brightness_slider.setValue(0)
        self.brightness_slider.valueChanged.connect(self.on_brightness_changed)
        camera_layout.addWidget(self.brightness_slider, 4, 1)
        self.brightness_value = QLabel("0")
        camera_layout.addWidget(self.brightness_value, 4, 2)

        # ISO Min
        camera_layout.addWidget(QLabel("ISO Min:"), 5, 0)
        self.iso_min_slider = QSlider(Qt.Orientation.Horizontal)
        self.iso_min_slider.setRange(100, 3200)
        self.iso_min_slider.setValue(100)
        self.iso_min_slider.valueChanged.connect(self.on_iso_min_changed)
        camera_layout.addWidget(self.iso_min_slider, 5, 1)
        self.iso_min_value = QLabel("100")
        camera_layout.addWidget(self.iso_min_value, 5, 2)

        # ISO Max
        camera_layout.addWidget(QLabel("ISO Max:"), 6, 0)
        self.iso_max_slider = QSlider(Qt.Orientation.Horizontal)
        self.iso_max_slider.setRange(100, 3200)
        self.iso_max_slider.setValue(800)
        self.iso_max_slider.valueChanged.connect(self.on_iso_max_changed)
        camera_layout.addWidget(self.iso_max_slider, 6, 1)
        self.iso_max_value = QLabel("800")
        camera_layout.addWidget(self.iso_max_value, 6, 2)

        # Capture Resolution dropdown
        camera_layout.addWidget(QLabel("Capture:"), 7, 0)
        self.resolution_combo = QComboBox()
        # Add only verified DepthAI supported resolutions
        resolutions = [
            ("THE_4_K", "4K (4056×3040)"),
            ("THE_12_MP", "12MP (4056×3040)"),
            ("THE_13_MP", "13MP (4208×3120)"),
            ("THE_1080_P", "1080p (1920×1080)"),
            ("THE_720_P", "720p (1280×720)"),
            ("THE_5_MP", "5MP (2592×1944)")
        ]
        for res_key, res_name in resolutions:
            self.resolution_combo.addItem(res_name, res_key)

        # Set current resolution from config
        current_res = self.config.get('camera', {}).get('resolution', '4k')
        res_map = {
            '4k': 'THE_4_K',
            '12mp': 'THE_12_MP',
            '13mp': 'THE_13_MP',
            '1080p': 'THE_1080_P',
            '720p': 'THE_720_P',
            '5mp': 'THE_5_MP'
        }
        current_index = 0
        for i in range(self.resolution_combo.count()):
            if self.resolution_combo.itemData(i) == res_map.get(current_res, 'THE_4_K'):
                current_index = i
                break
        self.resolution_combo.setCurrentIndex(current_index)
        self.resolution_combo.currentIndexChanged.connect(self.on_resolution_changed)
        camera_layout.addWidget(self.resolution_combo, 7, 1, 1, 2)

        # Preview Resolution dropdown
        camera_layout.addWidget(QLabel("Preview:"), 8, 0)
        self.preview_resolution_combo = QComboBox()
        preview_resolutions = [
            ("THE_1211x1013", "1211x1013"),
            ("THE_1250x1036", "1250x1036"),
            ("THE_1080_P", "1080p"),
            ("THE_720_P", "720p"),
            ("THE_480_P", "480p"),
            ("THE_400_P", "400p"),
            ("THE_300_P", "300p")
        ]
        for res_key, res_name in preview_resolutions:
            self.preview_resolution_combo.addItem(res_name, res_key)

        # Set default preview resolution (1211x1013)
        self.preview_resolution_combo.setCurrentIndex(0)
        # No immediate change handler - will apply on Save
        camera_layout.addWidget(self.preview_resolution_combo, 8, 1, 1, 2)
        
        camera_group.setLayout(camera_layout)
        left_layout.addWidget(camera_group)
        
        # Motion detection controls - compact
        motion_group = QGroupBox("Motion Detection")
        motion_layout = QGridLayout()
        motion_layout.setSpacing(2)
        motion_layout.setContentsMargins(5, 5, 5, 5)
        
        # Sensitivity slider with clarification
        sensitivity_label = QLabel("Sensitivity:")
        sensitivity_label.setToolTip("Higher values = MORE sensitive (detects smaller movements)\nLower values = LESS sensitive (ignores small movements)")
        motion_layout.addWidget(sensitivity_label, 0, 0)
        
        self.sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.sensitivity_slider.setRange(10, 100)
        self.sensitivity_slider.setValue(50)
        self.sensitivity_slider.valueChanged.connect(self.on_sensitivity_changed)
        motion_layout.addWidget(self.sensitivity_slider, 0, 1)
        
        self.sensitivity_value = QLabel("60")  # Display inverted initial value
        motion_layout.addWidget(self.sensitivity_value, 0, 2)
        
        # Add clarification text
        sensitivity_hint = QLabel("← Less Sensitive | More Sensitive →")
        sensitivity_hint.setStyleSheet("font-size: 9px; color: #888;")
        sensitivity_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        motion_layout.addWidget(sensitivity_hint, 1, 1)
        

        motion_group.setLayout(motion_layout)
        left_layout.addWidget(motion_group)
        
        # Motion detection settings
        motion_settings_group = QGroupBox("Motion Settings")
        motion_settings_layout = QGridLayout()
        
        # Debounce time
        motion_settings_layout.addWidget(QLabel("Debounce Time:"), 0, 0)
        self.debounce_slider = QSlider(Qt.Orientation.Horizontal)
        self.debounce_slider.setRange(1, 10)
        self.debounce_slider.setValue(5)
        self.debounce_slider.valueChanged.connect(self.on_debounce_changed)
        motion_settings_layout.addWidget(self.debounce_slider, 0, 1)
        self.debounce_value = QLabel("5.0s")
        motion_settings_layout.addWidget(self.debounce_value, 0, 2)
        
        motion_settings_group.setLayout(motion_settings_layout)
        right_layout.addWidget(motion_settings_group)
        
        # Action buttons - compact
        action_group = QGroupBox("Actions")
        action_layout = QVBoxLayout()
        action_layout.setSpacing(2)
        action_layout.setContentsMargins(5, 5, 5, 5)
        
        self.capture_btn = QPushButton("Capture")
        self.capture_btn.setMaximumHeight(30)
        self.capture_btn.clicked.connect(self.on_manual_capture)
        action_layout.addWidget(self.capture_btn)
        
        self.save_settings_btn = QPushButton("Save")
        self.save_settings_btn.setMaximumHeight(30)
        self.save_settings_btn.clicked.connect(self.on_save_settings)
        action_layout.addWidget(self.save_settings_btn)

        # Test button to verify dialogs work
        self.test_dialog_btn = QPushButton("Test Dialog")
        self.test_dialog_btn.setMaximumHeight(30)
        self.test_dialog_btn.clicked.connect(self.test_dialog)
        action_layout.addWidget(self.test_dialog_btn)
        
        action_group.setLayout(action_layout)
        right_layout.addWidget(action_group)
        
        # Add camera stats to the right column
        self.create_camera_stats_panel(right_layout)
        
        # Add columns to bottom layout
        bottom_layout.addWidget(left_column)
        bottom_layout.addWidget(right_column)
        
        # Add preview on top and controls on bottom
        main_layout.addWidget(preview_container, 3)  # Preview takes 3/4 of vertical space
        main_layout.addWidget(bottom_panel, 1)  # Controls take 1/4
        
        self.setLayout(main_layout)
    
    
    def create_camera_stats_panel(self, layout):
        """Create camera statistics panel for bottom panel"""
        stats_group = QGroupBox("Statistics")
        stats_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                padding-top: 10px;
                margin-top: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
        """)
        
        # Use grid layout for more compact horizontal display
        stats_layout = QGridLayout()
        stats_layout.setSpacing(2)
        stats_layout.setContentsMargins(5, 5, 5, 5)
        
        # Organize stats in a 2-column grid
        # Column 1
        self.camera_model_label = QLabel("Model: Unknown")
        self.camera_model_label.setStyleSheet("font-size: 11px;")
        stats_layout.addWidget(self.camera_model_label, 0, 0)
        
        self.connection_type_label = QLabel("Connection: Disconnected")
        self.connection_type_label.setStyleSheet("font-size: 11px;")
        stats_layout.addWidget(self.connection_type_label, 1, 0)
        
        self.sensor_fps_label = QLabel("Sensor: Unknown | FPS: 0")
        self.sensor_fps_label.setStyleSheet("font-size: 11px;")
        stats_layout.addWidget(self.sensor_fps_label, 2, 0)
        
        self.resolution_mode_label = QLabel("Resolution: 4K")
        self.resolution_mode_label.setStyleSheet("font-size: 11px;")
        stats_layout.addWidget(self.resolution_mode_label, 3, 0)
        
        # Column 2
        self.photos_motion_label = QLabel("Photos: 0 | Events: 0")
        self.photos_motion_label.setStyleSheet("font-size: 11px;")
        stats_layout.addWidget(self.photos_motion_label, 0, 1)
        
        self.last_capture_label = QLabel("Last: None")
        self.last_capture_label.setStyleSheet("font-size: 11px;")
        stats_layout.addWidget(self.last_capture_label, 1, 1)
        
        # Empty slots for alignment
        stats_layout.addWidget(QLabel(""), 2, 1)
        stats_layout.addWidget(QLabel(""), 3, 1)
        
        
        # Create label references for updates (hidden labels for compatibility)
        self.sensor_resolution_label = QLabel()
        self.fps_label = QLabel()
        self.session_photos_label = QLabel()
        self.motion_events_label = QLabel()
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # Set up timer to update stats periodically
        self.stats_timer = QTimer()
        self.stats_timer.timeout.connect(self.update_camera_stats)
        self.stats_timer.start(5000)  # Update every 5 seconds to reduce CPU load
        
        # Initial update
        self.update_camera_stats()
    
    def update_frame(self, frame):
        """Update the camera preview with new frame"""
        try:
            # Freeze detection: Track when update_frame is called
            if not hasattr(self, 'last_frame_update_time'):
                self.last_frame_update_time = time.time()
                self.frame_update_count = 0
                logger.info("[FREEZE-CHECK] First frame update - initializing tracking")

            current_time = time.time()
            time_since_last = current_time - self.last_frame_update_time

            # Log if there's a suspicious gap (> 5 seconds between frames)
            if time_since_last > 5.0:
                logger.warning(f"[FREEZE-CHECK] Long gap detected: {time_since_last:.1f}s since last frame update")

            self.frame_update_count += 1

            # Log every 100 frames to confirm updates are happening
            if self.frame_update_count % 100 == 0:
                logger.debug(f"[FREEZE-CHECK] Frame update #{self.frame_update_count}, gap: {time_since_last:.3f}s")

            self.last_frame_update_time = current_time

            if frame is None or frame.size == 0:
                logger.warning("Received invalid frame in update_frame")
                return

            self.current_frame = frame.copy()

            # Convert to Qt format
            height, width, channel = frame.shape

            # Validate frame dimensions
            if height == 0 or width == 0 or channel != 3:
                logger.error(f"[FREEZE-CHECK] Invalid frame dimensions: {height}x{width}x{channel}")
                return

            bytes_per_line = 3 * width
            logger.debug(f"[FREEZE-CHECK] Creating QImage: {width}x{height}, bpl: {bytes_per_line}")
            q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).rgbSwapped()

            if q_image.isNull():
                logger.error("[FREEZE-CHECK] Failed to create QImage from frame data - THIS CAUSES GUI FREEZE")
                return

            logger.debug(f"[FREEZE-CHECK] QImage created successfully, converting to pixmap")
            # Scale to fit preview
            pixmap = QPixmap.fromImage(q_image)
            if pixmap.isNull():
                logger.error("[FREEZE-CHECK] Failed to create QPixmap from QImage - THIS CAUSES GUI FREEZE")
                return

            logger.debug(f"[FREEZE-CHECK] Pixmap created, scaling to preview size: {self.preview_label.size()}")
            scaled_pixmap = pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            logger.debug(f"[FREEZE-CHECK] Setting pixmap on label")
            self.preview_label.setPixmap(scaled_pixmap)
            logger.debug(f"[FREEZE-CHECK] Frame display update complete")

            # Update FPS in stats (approximate)
            if hasattr(self, 'sensor_fps_label'):
                sensor_res = getattr(self, 'sensor_resolution_label', QLabel()).text()
                if sensor_res == "Unknown":
                    sensor_res = "4056x3040"
                self.sensor_fps_label.setText(f"Sensor: {sensor_res} | FPS: ~30")

        except Exception as e:
            logger.error(f"Error updating frame display: {e}", exc_info=True)
    
    def update_camera_stats(self):
        """Update camera statistics display"""
        if not hasattr(self, 'camera_model_label'):
            return
            
        # Update camera info from camera controller
        if self.camera_controller:
            device_info = self.camera_controller.get_device_info()
            
            # Camera model
            model = device_info.get('name', 'OAK Camera')
            self.camera_model_label.setText(f"Model: {model}")
            
            # Connection type
            usb_speed = device_info.get('usb_speed', 'Unknown')
            if device_info.get('connected'):
                self.connection_type_label.setText(f"Connection: USB {usb_speed}")
            else:
                self.connection_type_label.setText(f"Connection: {usb_speed}")
            
            # Sensor resolution and FPS
            sensor_res = device_info.get('sensor_resolution', '4056x3040')
            fps = getattr(self, 'current_fps', 0)
            self.sensor_fps_label.setText(f"Sensor: {sensor_res} | FPS: {fps}")
            
            # Store values in hidden labels for compatibility
            self.sensor_resolution_label.setText(sensor_res)
            self.fps_label.setText(str(fps))
        else:
            self.camera_model_label.setText("Model: Disconnected")
            self.connection_type_label.setText("Connection: Not Connected")
            self.sensor_fps_label.setText("Sensor: Unknown | FPS: 0")
            self.sensor_resolution_label.setText("Unknown")
            self.fps_label.setText("0")
        
        # Update photos and motion events
        self.photos_motion_label.setText(f"Photos: {self.session_capture_count} | Events: {self.motion_event_count}")
        
        # Store in hidden labels for compatibility
        self.session_photos_label.setText(str(self.session_capture_count))
        self.motion_events_label.setText(str(self.motion_event_count))
        
        # Update last capture time
        if self.last_capture_time:
            time_str = self.last_capture_time.strftime("%H:%M:%S")
            self.last_capture_label.setText(f"Last Capture: {time_str}")
        else:
            self.last_capture_label.setText("Last Capture: None")
        
        # Update resolution mode
        self.resolution_mode_label.setText("Resolution: 4K")
    
    def on_motion_detected(self):
        """Called when motion is detected - updates stats"""
        self.motion_event_count += 1
        self.daily_motion_events += 1
        
    def on_photo_captured(self):
        """Called when a photo is captured - updates stats"""
        self.session_capture_count += 1
        self.last_capture_time = datetime.now()
    
    def cleanup(self):
        """Clean up timers and resources"""
        if hasattr(self, 'stats_timer'):
            self.stats_timer.stop()
    
    def on_focus_changed(self, value):
        """Handle focus slider change"""
        self.focus_value.setText(str(value))
        self.camera_controller.update_camera_setting('focus', value)
    
    def on_exposure_changed(self, value):
        """Handle exposure slider change"""
        # Slider value is in 0.1ms units (5-100 = 0.5-10ms)
        exposure_ms = value / 10.0
        self.exposure_value.setText(f"{exposure_ms:.1f}ms")
        if not self.auto_exposure_cb.isChecked():
            self.camera_controller.update_camera_setting('exposure', exposure_ms)
    
    def on_auto_exposure_changed(self, state):
        """Handle auto exposure checkbox change"""
        enabled = state == Qt.CheckState.Checked.value
        self.camera_controller.update_camera_setting('auto_exposure', enabled)
        self.exposure_slider.setEnabled(not enabled)
    
    def on_wb_changed(self, value):
        """Handle white balance slider change"""
        self.wb_value.setText(f"{value}K")
        self.camera_controller.update_camera_setting('white_balance', value)

    def on_brightness_changed(self, value):
        """Handle brightness slider change"""
        self.brightness_value.setText(str(value))
        self.camera_controller.update_camera_setting('brightness', value)

    def on_iso_min_changed(self, value):
        """Handle ISO min slider change"""
        self.iso_min_value.setText(str(value))
        # Ensure max >= min
        if value > self.iso_max_slider.value():
            self.iso_max_slider.setValue(value)
        # Apply ISO setting to camera
        main_window = self.window()
        if hasattr(main_window, 'camera_controller'):
            main_window.camera_controller.update_camera_setting('iso', value)

    def on_iso_max_changed(self, value):
        """Handle ISO max slider change"""
        self.iso_max_value.setText(str(value))
        # Ensure max >= min
        if value < self.iso_min_slider.value():
            self.iso_min_slider.setValue(value)
        # Apply ISO setting to camera
        main_window = self.window()
        if hasattr(main_window, 'camera_controller'):
            main_window.camera_controller.update_camera_setting('iso', value)

    # Preview resolution change is now handled in on_save_settings() instead

    def on_resolution_changed(self, index):
        """Handle resolution dropdown change"""
        logger.info(f"=== on_resolution_changed CALLED with index={index} ===")
        resolution_key = self.resolution_combo.itemData(index)
        resolution_name = self.resolution_combo.itemText(index)
        logger.info(f"Resolution key: {resolution_key}, name: {resolution_name}")

        # Map DepthAI resolution keys to config values - only supported resolutions
        key_to_config = {
            'THE_4_K': '4k',
            'THE_12_MP': '12mp',
            'THE_13_MP': '13mp',
            'THE_1080_P': '1080p',
            'THE_720_P': '720p',
            'THE_5_MP': '5mp'
        }

        config_value = key_to_config.get(resolution_key, '4k')
        logger.info(f"Config value: {config_value}, showing confirmation...")

        # Show in-UI confirmation (QMessageBox doesn't work properly)
        self.show_resolution_confirmation(resolution_name, config_value, resolution_key)

    def show_resolution_confirmation(self, resolution_name, config_value, resolution_key):
        """Show in-UI confirmation for resolution change"""
        # Store the pending change
        self.pending_resolution_change = {
            'name': resolution_name,
            'config_value': config_value,
            'resolution_key': resolution_key
        }

        # Create confirmation widget if it doesn't exist
        if not hasattr(self, 'confirmation_widget'):
            self.confirmation_widget = QWidget()
            conf_layout = QVBoxLayout(self.confirmation_widget)
            conf_layout.setContentsMargins(10, 10, 10, 10)

            self.confirmation_label = QLabel()
            self.confirmation_label.setWordWrap(True)
            self.confirmation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            conf_layout.addWidget(self.confirmation_label)

            button_layout = QHBoxLayout()
            button_layout.addStretch()

            yes_btn = QPushButton("Yes, Change Resolution")
            yes_btn.clicked.connect(self.on_resolution_confirmed)
            yes_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; padding: 8px; font-weight: bold; }")
            button_layout.addWidget(yes_btn)

            no_btn = QPushButton("Cancel")
            no_btn.clicked.connect(self.on_resolution_cancelled)
            no_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; padding: 8px; font-weight: bold; }")
            button_layout.addWidget(no_btn)

            button_layout.addStretch()
            conf_layout.addLayout(button_layout)

            self.confirmation_widget.setStyleSheet("""
                QWidget {
                    background-color: #FFF3CD;
                    border: 2px solid #FFC107;
                    border-radius: 5px;
                }
                QLabel {
                    font-size: 13px;
                    font-weight: bold;
                    color: #856404;
                }
            """)
            self.confirmation_widget.hide()

            # Insert at the top of the main layout
            main_layout = self.layout()
            if main_layout:
                main_layout.insertWidget(0, self.confirmation_widget)

        # Update message
        self.confirmation_label.setText(
            f"⚠️ Change capture resolution to {resolution_name}?\n\n"
            f"This will restart the camera and may take a few seconds."
        )
        self.confirmation_widget.show()
        logger.info(f"Showing resolution confirmation for {resolution_name}")

    def on_resolution_confirmed(self):
        """User confirmed resolution change"""
        self.confirmation_widget.hide()

        if not hasattr(self, 'pending_resolution_change'):
            return

        resolution_name = self.pending_resolution_change['name']
        config_value = self.pending_resolution_change['config_value']

        logger.info(f"Changing camera resolution to {resolution_name}")

        # Update config
        self.config['camera']['resolution'] = config_value

        # Save config to file
        try:
            import json
            config_path = os.path.join(os.path.dirname(__file__), 'config.json')
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info(f"Config updated with new resolution: {config_value}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

        # Get main window reference using window() method
        main_window = self.window()

        try:
            # Step 1: Stop and cleanup existing camera thread
            if hasattr(main_window, 'camera_thread') and main_window.camera_thread:
                logger.info("Stopping existing camera thread...")
                # Disconnect all signals first
                try:
                    main_window.camera_thread.frame_ready.disconnect()
                    main_window.camera_thread.image_captured.disconnect()
                except:
                    pass  # Signals may not be connected

                main_window.camera_thread.stop()
                if not main_window.camera_thread.wait(3000):  # Wait up to 3 seconds
                    logger.warning("Camera thread did not stop gracefully")
                main_window.camera_thread = None

            # Step 2: Disconnect camera controller
            if hasattr(self.camera_controller, 'device') and self.camera_controller.device:
                logger.info("Disconnecting camera controller...")
                self.camera_controller.disconnect()

            # Step 3: Update camera controller config
            self.camera_controller.config['resolution'] = config_value
            logger.info(f"Camera controller config updated to: {config_value}")

            # Step 4: Reconnect and setup new pipeline
            if self.camera_controller.connect() and self.camera_controller.setup_pipeline():
                logger.info("Camera reconnected with new resolution")

                # Step 5: Create and start new camera thread
                main_window.camera_thread = CameraThread(self.camera_controller)
                main_window.camera_thread.frame_ready.connect(self.update_frame)
                main_window.camera_thread.image_captured.connect(main_window.on_image_captured)
                main_window.camera_thread.start()

                logger.info(f"Camera successfully restarted with resolution: {resolution_name}")

                # Show success notification
                self.show_save_notification(
                    f"✅ Capture resolution changed to {resolution_name}\n\nCamera restarted successfully.",
                    1, False
                )
            else:
                raise Exception("Failed to setup camera pipeline with new resolution")

        except Exception as e:
            logger.error(f"Failed to restart camera with new resolution: {e}")
            self.show_save_notification(f"❌ Failed to change resolution: {str(e)}", 0, False)

            # Revert dropdown to previous selection
            current_res = self.config.get('camera', {}).get('resolution', '4k')
            res_map = {
                '4k': 'THE_4_K',
                '12mp': 'THE_12_MP',
                '13mp': 'THE_13_MP',
                '1080p': 'THE_1080_P',
                '720p': 'THE_720_P',
                '5mp': 'THE_5_MP'
            }
            for i in range(self.resolution_combo.count()):
                if self.resolution_combo.itemData(i) == res_map.get(current_res, 'THE_4_K'):
                    self.resolution_combo.setCurrentIndex(i)
                    break

    def on_resolution_cancelled(self):
        """User cancelled resolution change"""
        self.confirmation_widget.hide()
        logger.info("Resolution change cancelled")

        # Revert dropdown selection to current config value
        current_res = self.config.get('camera', {}).get('resolution', '4k')
        res_map = {
            '4k': 'THE_4_K',
            '12mp': 'THE_12_MP',
            '13mp': 'THE_13_MP',
            '1080p': 'THE_1080_P',
            '720p': 'THE_720_P',
            '5mp': 'THE_5_MP'
        }
        for i in range(self.resolution_combo.count()):
            if self.resolution_combo.itemData(i) == res_map.get(current_res, 'THE_4_K'):
                self.resolution_combo.blockSignals(True)
                self.resolution_combo.setCurrentIndex(i)
                self.resolution_combo.blockSignals(False)
                break
    
    def on_sensitivity_changed(self, value):
        """Handle sensitivity slider change"""
        # Display the inverted value (higher = more sensitive)
        display_value = 110 - value  # Convert range 10-100 to 100-10
        self.sensitivity_value.setText(str(display_value))
        # Use original value for motion detection (lower = more sensitive)
        self.camera_controller.motion_detector.update_settings(threshold=value)

    def on_debounce_changed(self, value):
        """Handle debounce time slider change"""
        self.debounce_value.setText(f"{value}.0s")
        self.camera_controller.debounce_time = value
        logger.info(f"Debounce time set to {value}s")
    
    
    def on_roi_selected(self, start_point, end_point):
        """Handle ROI selection from preview label"""
        if start_point.x() == -1:  # Clear ROI
            self.camera_controller.clear_roi()
            self.preview_label.clear_roi()
            logger.info("ROI cleared")
        else:
            # Get current camera preview resolution
            preview_res_map = {
                'THE_1211x1013': (1211, 1013),
                'THE_1250x1036': (1250, 1036),
                'THE_1080_P': (1920, 1080),
                'THE_720_P': (1280, 720),
                'THE_480_P': (640, 480),
                'THE_400_P': (640, 400),
                'THE_300_P': (640, 300)
            }

            # Get camera resolution
            camera_res = getattr(self.camera_controller, 'preview_resolution', 'THE_1211x1013')
            camera_width, camera_height = preview_res_map.get(camera_res, (1211, 1013))

            # Get display widget size
            display_width = self.preview_label.width()
            display_height = self.preview_label.height()

            logger.info(f"ROI Scaling: Display {display_width}x{display_height} -> Camera {camera_width}x{camera_height}")

            # Scale ROI coordinates from display to camera resolution
            scale_x = camera_width / display_width
            scale_y = camera_height / display_height

            camera_start_x = int(start_point.x() * scale_x)
            camera_start_y = int(start_point.y() * scale_y)
            camera_end_x = int(end_point.x() * scale_x)
            camera_end_y = int(end_point.y() * scale_y)

            logger.info(f"Display ROI: ({start_point.x()}, {start_point.y()}) to ({end_point.x()}, {end_point.y()})")
            logger.info(f"Camera ROI: ({camera_start_x}, {camera_start_y}) to ({camera_end_x}, {camera_end_y})")

            # Set ROI in camera controller with scaled coordinates
            self.camera_controller.set_roi(
                (camera_start_x, camera_start_y),
                (camera_end_x, camera_end_y)
            )

            # Update the visual ROI rectangle on the preview (keep display coordinates)
            roi_rect = QRect(start_point, end_point).normalized()
            self.preview_label.roi_rect = roi_rect
            self.preview_label.update()

            # Trigger autofocus on ROI if enabled
            if hasattr(self, 'roi_autofocus_cb') and self.roi_autofocus_cb.isChecked():
                self.camera_controller.autofocus_roi()
                logger.info("Autofocus triggered for new ROI")

            logger.info(f"ROI set: {start_point} to {end_point}")
    
    def on_focus_point_clicked(self, point):
        """Handle right-click focus adjustment based on position"""
        # Calculate focus value based on vertical position
        # Top of preview = far focus (higher values)
        # Bottom of preview = near focus (lower values)
        preview_height = self.preview_label.height()
        y_position = point.y()
        
        # Invert y so top = far, bottom = near
        normalized_y = 1.0 - (y_position / preview_height)
        
        # Map to focus range (0-255)
        # For bird bath, use range 100-220 for practical focusing
        min_focus = 100
        max_focus = 220
        new_focus = int(min_focus + (normalized_y * (max_focus - min_focus)))
        
        # Update focus slider
        self.focus_slider.setValue(new_focus)
        
        # Show visual feedback
        from PyQt6.QtWidgets import QToolTip
        QToolTip.showText(
            self.preview_label.mapToGlobal(point),
            f"Focus set to {new_focus}\n(Top=Far {max_focus}, Bottom=Near {min_focus})",
            self.preview_label,
            QRect(point.x() - 50, point.y() - 50, 100, 100),
            2000  # Show for 2 seconds
        )
        
        logger.info(f"Focus adjusted to {new_focus} based on click at y={y_position} (normalized={normalized_y:.2f})")
        
        # Add visual indicator on preview
        self.preview_label.update()
    
    def on_set_roi(self):
        """Set ROI for motion detection"""
        # This button now just provides instructions and visual feedback
        logger.info("Click and drag on the preview to set ROI")
        
        # Show message box with instructions
        QMessageBox.information(self, "Set ROI", 
                               "Click and drag on the camera preview to draw a rectangle for motion detection.\n\n"
                               "• Left-click and drag to select an area\n"
                               "• The area will be highlighted in green\n"
                               "• Use 'Clear ROI' to remove the current selection")
    
    def on_clear_roi(self):
        """Clear ROI"""
        self.camera_controller.clear_roi()
        self.preview_label.clear_roi()
        logger.info("ROI cleared")
    
    def on_reset_zoom(self):
        """Reset camera preview zoom to 1.0x"""
        self.preview_label.reset_zoom()
        logger.info("Camera preview zoom reset")
    
    
    def load_default_roi(self):
        """Load ROI from config and scale to current preview size"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'config.json')
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            motion_config = config.get('motion_detection', {})
            
            # First try to load current_roi (user-drawn ROI)
            roi_config = motion_config.get('current_roi', {})
            if roi_config:
                logger.info("Loading saved current ROI")
            else:
                # Fallback to default_roi if no current_roi exists
                roi_config = motion_config.get('default_roi', {})
                logger.info("Loading default ROI")
            # Check if ROI should be loaded (enabled for default_roi, or any current_roi)
            should_load = (roi_config.get('enabled', False) or 
                          ('current_roi' in motion_config and roi_config))
            
            if should_load and roi_config:
                # Original ROI coordinates from config
                orig_x = roi_config.get('x', 0)
                orig_y = roi_config.get('y', 0)
                orig_width = roi_config.get('width', 600)
                orig_height = roi_config.get('height', 400)
                
                # Get current preview dimensions
                preview_width = 600  # Current fixed preview width
                preview_height = 400  # Current fixed preview height
                
                # Scale ROI coordinates if they extend beyond current preview
                if orig_x + orig_width > preview_width or orig_y + orig_height > preview_height:
                    # Calculate scale factor based on the larger dimension that overflows
                    scale_x = preview_width / (orig_x + orig_width) if orig_x + orig_width > preview_width else 1.0
                    scale_y = preview_height / (orig_y + orig_height) if orig_y + orig_height > preview_height else 1.0
                    scale = min(scale_x, scale_y)
                    
                    x = int(orig_x * scale)
                    y = int(orig_y * scale)
                    width = int(orig_width * scale)
                    height = int(orig_height * scale)
                    
                    logger.info(f"Scaled ROI from ({orig_x}, {orig_y}, {orig_width}x{orig_height}) to ({x}, {y}, {width}x{height})")
                else:
                    # Use original coordinates if they fit
                    x, y, width, height = orig_x, orig_y, orig_width, orig_height
                
                # Ensure ROI stays within preview bounds
                x = max(0, min(x, preview_width - 1))
                y = max(0, min(y, preview_height - 1))
                width = min(width, preview_width - x)
                height = min(height, preview_height - y)
                
                # Set ROI in preview label
                self.preview_label.set_roi_rect(x, y, width, height)

                # Scale ROI coordinates from display to camera resolution
                preview_res_map = {
                    'THE_1211x1013': (1211, 1013),
                'THE_1250x1036': (1250, 1036),
                    'THE_1080_P': (1920, 1080),
                    'THE_720_P': (1280, 720),
                    'THE_480_P': (640, 480),
                    'THE_400_P': (640, 400),
                    'THE_300_P': (640, 300)
                }

                # Get camera resolution
                camera_res = getattr(self.camera_controller, 'preview_resolution', 'THE_1211x1013')
                camera_width, camera_height = preview_res_map.get(camera_res, (1211, 1013))

                # Get display widget size
                display_width = self.preview_label.width()
                display_height = self.preview_label.height()

                # Scale to camera coordinates
                scale_x = camera_width / display_width
                scale_y = camera_height / display_height

                camera_x1 = int(x * scale_x)
                camera_y1 = int(y * scale_y)
                camera_x2 = int((x + width) * scale_x)
                camera_y2 = int((y + height) * scale_y)

                # Set ROI in camera controller with scaled coordinates
                self.camera_controller.set_roi((camera_x1, camera_y1), (camera_x2, camera_y2))

                logger.info(f"Display ROI loaded: ({x}, {y}) to ({x + width}, {y + height})")
                logger.info(f"Camera ROI loaded: ({camera_x1}, {camera_y1}) to ({camera_x2}, {camera_y2})")
            else:
                logger.info("Default ROI is disabled in config")
                
        except Exception as e:
            logger.error(f"Failed to load default ROI: {e}")
    
    def on_manual_capture(self):
        """Manual capture button pressed"""
        self.camera_controller.capture_still()
        logger.info("Manual capture triggered")
    
    def on_debounce_changed(self, value):
        """Handle debounce time slider change"""
        self.debounce_value.setText(f"{value}.0s")
        self.camera_controller.debounce_time = value
        logger.info(f"Debounce time set to {value}s")
    
    
    def load_camera_settings(self):
        """Load camera settings from config"""
        try:
            # Load camera settings
            camera_config = self.config.get('camera', {})
            self.focus_slider.setValue(camera_config.get('focus', 128))
            # Convert exposure from ms to slider units (0.1ms increments)
            exposure_ms = camera_config.get('exposure_ms', 2.0)
            self.exposure_slider.setValue(int(exposure_ms * 10))
            self.wb_slider.setValue(camera_config.get('white_balance', 6637))
            self.brightness_slider.setValue(camera_config.get('brightness', 0))
            self.brightness_value.setText(str(self.brightness_slider.value()))
            self.iso_min_slider.setValue(camera_config.get('iso_min', 100))
            self.iso_max_slider.setValue(camera_config.get('iso_max', 800))

            # Load preview resolution from config
            saved_preview_res = camera_config.get('preview_resolution', 'THE_1211x1013')
            logger.info(f"Loading saved preview resolution: {saved_preview_res}")

            # Set the combo box to the saved value
            for i in range(self.preview_resolution_combo.count()):
                if self.preview_resolution_combo.itemData(i) == saved_preview_res:
                    self.preview_resolution_combo.setCurrentIndex(i)
                    logger.info(f"Set preview combo to index {i}: {self.preview_resolution_combo.itemText(i)}")
                    break

            # Also set it in the camera controller
            self.camera_controller.preview_resolution = saved_preview_res

            # Load motion detection settings
            motion_config = self.config.get('motion_detection', {})
            threshold_value = motion_config.get('threshold', 50)
            self.sensitivity_slider.setValue(threshold_value)
            # Update display with inverted value
            display_value = 110 - threshold_value
            self.sensitivity_value.setText(str(display_value))

            logger.info("Camera settings loaded from config")
        except Exception as e:
            logger.error(f"Failed to load camera settings: {e}")
    
    def test_dialog(self):
        """Test if dialogs work at all"""
        logger.info("Testing dialog display...")
        # Use main window as parent to ensure dialog appears on top
        main_window = self.window()

        # Force dialog to be visible with explicit flags
        msg = QMessageBox(main_window)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText("This is a test dialog.")
        msg.setInformativeText("If you can see this, dialogs are working!")
        msg.setWindowTitle("Test Dialog")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.setWindowModality(Qt.WindowModality.ApplicationModal)
        msg.raise_()
        msg.activateWindow()

        logger.info("About to exec test dialog...")
        result = msg.exec()
        logger.info(f"Test dialog closed with result: {result}")

    def on_save_settings(self):
        """Save current settings"""
        try:
            # Track what changed
            changes = []
            
            # Check camera settings changes
            old_focus = self.config['camera'].get('focus', 128)
            new_focus = self.focus_slider.value()
            if old_focus != new_focus:
                changes.append(f"• Focus: {old_focus} → {new_focus}")
            
            old_exposure = self.config['camera'].get('exposure_ms', 2.0)
            # Convert slider value (0.1ms units) to milliseconds
            new_exposure = self.exposure_slider.value() / 10.0
            if old_exposure != new_exposure:
                changes.append(f"• Exposure: {old_exposure:.1f}ms → {new_exposure:.1f}ms")
            
            old_wb = self.config['camera'].get('white_balance', 6637)
            new_wb = self.wb_slider.value()
            if old_wb != new_wb:
                changes.append(f"• White Balance: {old_wb}K → {new_wb}K")

            old_brightness = self.config['camera'].get('brightness', 0)
            new_brightness = self.brightness_slider.value()
            if old_brightness != new_brightness:
                changes.append(f"• Brightness: {old_brightness} → {new_brightness}")

            old_iso_min = self.config['camera'].get('iso_min', 100)
            new_iso_min = self.iso_min_slider.value()
            if old_iso_min != new_iso_min:
                changes.append(f"• ISO Min: {old_iso_min} → {new_iso_min}")
            
            old_iso_max = self.config['camera'].get('iso_max', 800)
            new_iso_max = self.iso_max_slider.value()
            if old_iso_max != new_iso_max:
                changes.append(f"• ISO Max: {old_iso_max} → {new_iso_max}")
            
            # Check motion detection changes
            old_threshold = self.config['motion_detection'].get('threshold', 50)
            new_threshold = self.sensitivity_slider.value()
            if old_threshold != new_threshold:
                changes.append(f"• Motion Threshold: {old_threshold} → {new_threshold}")

            # Check preview resolution changes
            new_preview_res = self.preview_resolution_combo.itemData(self.preview_resolution_combo.currentIndex())
            old_preview_res = getattr(self.camera_controller, 'preview_resolution', 'THE_1211x1013')
            preview_changed = False

            logger.info(f"Preview resolution check - Old: {old_preview_res}, New: {new_preview_res}")

            if old_preview_res != new_preview_res:
                old_name = {'THE_1211x1013': '1211x1013', 'THE_1250x1036': '1250x1036', 'THE_1080_P': '1080p', 'THE_720_P': '720p', 'THE_480_P': '480p', 'THE_400_P': '400p', 'THE_300_P': '300p'}.get(old_preview_res, '1211x1013')
                new_name = self.preview_resolution_combo.currentText()
                changes.append(f"• Preview Resolution: {old_name} → {new_name}")
                preview_changed = True
                logger.info(f"Preview resolution will change from {old_name} to {new_name}")

            # Update config with current values
            self.config['camera']['focus'] = new_focus
            self.config['camera']['exposure_ms'] = new_exposure
            self.config['camera']['white_balance'] = new_wb
            self.config['camera']['brightness'] = new_brightness
            self.config['camera']['iso_min'] = new_iso_min
            self.config['camera']['iso_max'] = new_iso_max
            self.config['camera']['preview_resolution'] = new_preview_res  # Save preview resolution to config
            self.config['motion_detection']['threshold'] = new_threshold
            
            # Save current ROI settings if defined
            roi_changed = False
            if self.camera_controller.roi_defined:
                roi_rect = self.preview_label.roi_rect
                if not roi_rect.isEmpty():
                    new_roi = {
                        'x': roi_rect.x(),
                        'y': roi_rect.y(),
                        'width': roi_rect.width(),
                        'height': roi_rect.height()
                    }
                    old_roi = self.config['motion_detection'].get('current_roi', {})
                    if old_roi != new_roi:
                        changes.append(f"• ROI: Updated to ({roi_rect.x()}, {roi_rect.y()}, {roi_rect.width()}x{roi_rect.height()})")
                        roi_changed = True
                    
                    self.config['motion_detection']['current_roi'] = new_roi
                    logger.info(f"Saving ROI: {roi_rect}")
            
            # Save to file
            config_path = os.path.join(
                os.path.dirname(__file__),
                'config.json'
            )
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            
            logger.info("Settings saved to config.json")

            # If preview resolution changed, restart camera with new settings
            if preview_changed:
                logger.info(f"=== Starting camera restart for preview resolution change ===")
                logger.info(f"New preview resolution: {new_preview_res}")

                # Get main window reference
                main_window = self.window()

                try:
                    # Stop camera thread
                    logger.info("Step 1: Stopping camera thread...")
                    if hasattr(main_window, 'camera_thread') and main_window.camera_thread:
                        # Disconnect signals
                        try:
                            main_window.camera_thread.frame_ready.disconnect()
                            main_window.camera_thread.image_captured.disconnect()
                            logger.info("Disconnected camera thread signals")
                        except Exception as e:
                            logger.info(f"Signal disconnect: {e}")

                        # Stop thread
                        main_window.camera_thread.stop()
                        main_window.camera_thread.wait(2000)
                        main_window.camera_thread = None
                        logger.info("Camera thread stopped")

                    # Disconnect and reconnect camera with new preview settings
                    logger.info("Step 2: Disconnecting camera device...")
                    if hasattr(self.camera_controller, 'device') and self.camera_controller.device:
                        self.camera_controller.disconnect()
                        logger.info("Camera device disconnected")

                    # Get old and new preview dimensions for ROI scaling
                    old_preview_res_map = {
                        'THE_1211x1013': (1211, 1013),
                'THE_1250x1036': (1250, 1036),
                        'THE_1080_P': (1920, 1080),
                        'THE_720_P': (1280, 720),
                        'THE_480_P': (640, 480),
                        'THE_400_P': (640, 400),
                        'THE_300_P': (640, 300)
                    }
                    old_width, old_height = old_preview_res_map.get(old_preview_res, (1211, 1013))
                    new_width, new_height = old_preview_res_map.get(new_preview_res, (1211, 1013))

                    logger.info(f"ROI scaling: {old_width}x{old_height} -> {new_width}x{new_height}")

                    # Update preview resolution in camera controller
                    logger.info(f"Step 3: Updating camera controller preview resolution to {new_preview_res}")
                    self.camera_controller.preview_resolution = new_preview_res

                    # Update preview widget size for new resolution
                    logger.info(f"Step 3a: Updating preview widget for resolution {new_preview_res}")
                    self.preview_label.set_preview_resolution(new_preview_res)

                    # Scale ROI if it exists
                    if hasattr(self, 'preview_label') and not self.preview_label.roi_rect.isEmpty():
                        old_roi = self.preview_label.roi_rect
                        logger.info(f"Scaling ROI from: {old_roi}")

                        # Get current display dimensions for scaling calculation
                        old_display_width = self.preview_label.width()
                        old_display_height = self.preview_label.height()

                        # Get new display dimensions from resolution map
                        resolution_display_map = {
                            'THE_1211x1013': (605, 506),
                        'THE_1250x1036': (625, 518),
                            'THE_1080_P': (600, 338),
                            'THE_720_P': (640, 360),
                            'THE_480_P': (640, 480),
                            'THE_400_P': (640, 400),
                            'THE_300_P': (640, 300)
                        }
                        display_width, display_height = resolution_display_map.get(new_preview_res, (625, 518))

                        # Calculate ROI scaling factors for the display
                        display_scale_x = display_width / old_display_width
                        display_scale_y = display_height / old_display_height

                        # Scale ROI coordinates for display
                        new_x = int(old_roi.x() * display_scale_x)
                        new_y = int(old_roi.y() * display_scale_y)
                        new_width_roi = int(old_roi.width() * display_scale_x)
                        new_height_roi = int(old_roi.height() * display_scale_y)

                        # Update the ROI rect for display
                        self.preview_label.roi_rect = QRect(new_x, new_y, new_width_roi, new_height_roi)
                        logger.info(f"Scaled ROI for display to: {self.preview_label.roi_rect}")

                        # Convert ROI coordinates to camera resolution for camera controller
                        # (ROI in camera coordinates should be proportional to camera resolution)
                        cam_roi_scale_x = new_width / old_width
                        cam_roi_scale_y = new_height / old_height

                        # Get original ROI in old camera coordinates
                        old_cam_scale_x = old_width / old_display_width
                        old_cam_scale_y = old_height / old_display_height

                        # Convert display ROI to camera coordinates
                        cam_x = int(old_roi.x() * old_cam_scale_x * cam_roi_scale_x)
                        cam_y = int(old_roi.y() * old_cam_scale_y * cam_roi_scale_y)
                        cam_width = int(old_roi.width() * old_cam_scale_x * cam_roi_scale_x)
                        cam_height = int(old_roi.height() * old_cam_scale_y * cam_roi_scale_y)

                        # Update camera controller ROI with camera coordinates
                        self.camera_controller.set_roi((cam_x, cam_y), (cam_x + cam_width, cam_y + cam_height))
                        logger.info(f"Camera ROI set to: ({cam_x}, {cam_y}) to ({cam_x + cam_width}, {cam_y + cam_height})")

                    # Reconnect
                    logger.info("Step 4: Reconnecting camera with new settings...")
                    if self.camera_controller.connect():
                        # Restart camera thread
                        logger.info("Step 5: Restarting camera thread...")
                        main_window.camera_thread = CameraThread(self.camera_controller)
                        main_window.camera_thread.frame_ready.connect(main_window.camera_tab.update_frame)
                        main_window.camera_thread.image_captured.connect(main_window.on_image_captured)
                        main_window.camera_thread.start()
                        logger.info(f"=== Camera successfully restarted with preview resolution: {new_preview_res} ===")

                        # Force ROI redraw after camera restart
                        if hasattr(self, 'preview_label') and not self.preview_label.roi_rect.isEmpty():
                            logger.info(f"Forcing ROI redraw after camera restart: {self.preview_label.roi_rect}")
                            self.preview_label.update()  # Force repaint

                    else:
                        logger.error("Failed to reconnect camera with new preview resolution")
                        QMessageBox.warning(self, "Camera Restart Failed", "Failed to restart camera with new preview resolution")

                except Exception as e:
                    logger.error(f"Error restarting camera: {e}")
                    QMessageBox.warning(self, "Camera Restart Error", f"Error restarting camera: {str(e)}")

            # Show success message with changes
            if changes:
                message = "Camera settings saved successfully!\n\nChanges made:\n" + "\n".join(changes)
                if preview_changed:
                    message += "\n\nCamera restarted with new preview resolution."
            else:
                message = "Camera settings saved successfully!\n\nNo changes detected - all settings remain the same."

            logger.info(f"Showing save confirmation dialog: {len(changes)} changes")
            logger.info(f"Changes detected: {changes}")
            logger.info(f"Dialog message: {message}")

            # Create a custom notification instead of dialog
            # Since dialogs aren't working, we'll use a label in the UI
            self.show_save_notification(message, len(changes), preview_changed)

            # Other settings are applied immediately via slider change events
            
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            QMessageBox.critical(self, "Save Failed", f"Failed to save settings:\n{str(e)}")

    def show_save_notification(self, message, changes_count, preview_changed):
        """Show a visual save confirmation notification in the UI"""
        try:
            logger.info(f"Creating save notification UI - Changes: {changes_count}, Preview changed: {preview_changed}")

            # Create or update notification label if it doesn't exist
            if not hasattr(self, 'notification_label'):
                # Create a notification area at the top of the camera tab
                self.notification_label = QLabel()
                self.notification_label.setWordWrap(True)
                self.notification_label.setStyleSheet("""
                    QLabel {
                        background-color: #4CAF50;
                        color: white;
                        padding: 10px;
                        border-radius: 5px;
                        font-weight: bold;
                        font-size: 12px;
                    }
                """)
                self.notification_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.notification_label.hide()  # Initially hidden

                # Insert at the top of the main layout
                main_layout = self.layout()
                if main_layout:
                    main_layout.insertWidget(0, self.notification_label)
                    logger.info("Added notification label to camera tab layout")

            # Set the message
            self.notification_label.setText(message)
            self.notification_label.show()
            logger.info("Showing save notification with message")

            # Use a timer to auto-hide the notification after 5 seconds
            if hasattr(self, 'notification_timer'):
                self.notification_timer.stop()
            else:
                self.notification_timer = QTimer()
                self.notification_timer.setSingleShot(True)
                self.notification_timer.timeout.connect(self.hide_save_notification)

            self.notification_timer.start(5000)  # Hide after 5 seconds
            logger.info("Save notification displayed successfully")

        except Exception as e:
            logger.error(f"Failed to show save notification: {e}")

    def hide_save_notification(self):
        """Hide the save notification"""
        try:
            if hasattr(self, 'notification_label'):
                self.notification_label.hide()
                logger.info("Save notification hidden")
        except Exception as e:
            logger.error(f"Failed to hide save notification: {e}")

    def on_camera_disconnected(self):
        """Handle camera disconnection"""
        try:
            logger.warning("Camera disconnected - updating UI")
            self.connection_status_label.setText("🔴 Camera Disconnected - Reconnecting...")
            self.connection_status_label.setStyleSheet("""
                QLabel {
                    background-color: #C62828;
                    color: white;
                    padding: 5px;
                    border-radius: 3px;
                    font-weight: bold;
                    font-size: 11px;
                }
            """)
            self.connection_status_label.show()

            # Disable camera controls
            self.focus_slider.setEnabled(False)
            self.exposure_slider.setEnabled(False)
            self.wb_slider.setEnabled(False)
            self.iso_min_slider.setEnabled(False)
            self.iso_max_slider.setEnabled(False)
            self.auto_exposure_cb.setEnabled(False)

            # Show disconnected message in preview
            self.preview_label.setText("Camera Disconnected\nAttempting to reconnect...")
            self.preview_label.setPixmap(QPixmap())  # Clear current image

        except Exception as e:
            logger.error(f"Error handling camera disconnection: {e}")

    def on_camera_reconnected(self):
        """Handle camera reconnection"""
        try:
            logger.info("Camera reconnected - updating UI")
            self.connection_status_label.setText("🟢 Camera Reconnected")
            self.connection_status_label.setStyleSheet("""
                QLabel {
                    background-color: #2E7D32;
                    color: white;
                    padding: 5px;
                    border-radius: 3px;
                    font-weight: bold;
                    font-size: 11px;
                }
            """)

            # Hide status after 3 seconds
            QTimer.singleShot(3000, self.connection_status_label.hide)

            # Re-enable camera controls
            self.focus_slider.setEnabled(True)
            self.exposure_slider.setEnabled(True)
            self.wb_slider.setEnabled(True)
            self.iso_min_slider.setEnabled(True)
            self.iso_max_slider.setEnabled(True)
            self.auto_exposure_cb.setEnabled(True)

            # Reset preview label text
            self.preview_label.setText("Camera Preview")

            # Reload camera settings to ensure they're applied
            self.load_camera_settings()

        except Exception as e:
            logger.error(f"Error handling camera reconnection: {e}")

class ImageViewerDialog(QDialog):
    """Full-size image viewer dialog with keyboard navigation"""
    
    def __init__(self, parent, current_image_path, all_image_paths):
        super().__init__(parent)
        self.current_image_path = str(current_image_path)
        self.all_image_paths = [str(p) for p in all_image_paths]
        self.current_index = self.all_image_paths.index(self.current_image_path)
        
        self.setWindowTitle(Path(current_image_path).name)
        self.setModal(True)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Image label - make it expand to fill available space
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(1200, 800)  # Doubled from 600x400
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.image_label, 1)  # Give it stretch factor of 1

        # Navigation info
        self.nav_label = QLabel()
        self.nav_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nav_label.setStyleSheet("color: #888; padding: 5px;")
        layout.addWidget(self.nav_label)

        # Button layout
        button_layout = QHBoxLayout()

        # Previous button
        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.clicked.connect(self.show_previous)
        button_layout.addWidget(self.prev_btn)

        # Close button
        close_btn = QPushButton("Close (Esc)")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        # Next button
        self.next_btn = QPushButton("Next →")
        self.next_btn.clicked.connect(self.show_next)
        button_layout.addWidget(self.next_btn)

        layout.addLayout(button_layout)

        # Load initial image
        self.load_current_image()

        # Set window size to be twice as large (1600x1200 instead of 800x600)
        self.resize(1600, 1200)
        self.setMinimumSize(1600, 1200)
        
        # Store original pixmap for resizing
        self.original_pixmap = None
        
    def keyPressEvent(self, event):
        """Handle keyboard navigation"""
        if event.key() == Qt.Key.Key_Left:
            self.show_previous()
        elif event.key() == Qt.Key.Key_Right:
            self.show_next()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
    
    def resizeEvent(self, event):
        """Handle window resize - rescale image to fit new size"""
        super().resizeEvent(event)
        if hasattr(self, 'original_pixmap') and self.original_pixmap:
            # Delay the rescaling slightly to avoid flickering during resize
            QTimer.singleShot(50, self.scale_and_display_image)
    
    def scale_and_display_image(self):
        """Scale and display the current image to fit available space"""
        if not self.original_pixmap:
            return

        try:
            # Get available space, accounting for margins and buttons
            available_size = self.image_label.size()

            # Account for margins - leave some padding
            max_width = max(available_size.width() - 40, 600)
            max_height = max(available_size.height() - 40, 400)

            # Scale image to fit available space while preserving aspect ratio
            if (self.original_pixmap.width() > max_width or
                self.original_pixmap.height() > max_height):
                scaled_pixmap = self.original_pixmap.scaled(
                    max_width, max_height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
            else:
                # Show at original size if it fits
                scaled_pixmap = self.original_pixmap

            self.image_label.setPixmap(scaled_pixmap)
            
        except Exception as e:
            logger.error(f"Error scaling image: {e}")
    
    def load_current_image(self):
        """Load and display the current image"""
        try:
            # Load the original pixmap
            self.original_pixmap = QPixmap(self.current_image_path)
            
            # Scale and display it
            self.scale_and_display_image()
            
            # Update window title and navigation info
            filename = Path(self.current_image_path).name
            self.setWindowTitle(filename)
            self.nav_label.setText(f"Image {self.current_index + 1} of {len(self.all_image_paths)} | Use arrow keys to navigate")
            
            # Update button states
            self.prev_btn.setEnabled(self.current_index > 0)
            self.next_btn.setEnabled(self.current_index < len(self.all_image_paths) - 1)
            
        except Exception as e:
            logger.error(f"Error loading image: {e}")
            self.image_label.setText("Error loading image")
    
    def show_previous(self):
        """Show previous image"""
        if self.current_index > 0:
            self.current_index -= 1
            self.current_image_path = self.all_image_paths[self.current_index]
            self.load_current_image()
    
    def show_next(self):
        """Show next image"""
        if self.current_index < len(self.all_image_paths) - 1:
            self.current_index += 1
            self.current_image_path = self.all_image_paths[self.current_index]
            self.load_current_image()

class GalleryLoader(QThread):
    """Background thread for loading gallery images"""
    progress = pyqtSignal(int, int, str)  # current, total, message
    image_loaded = pyqtSignal(object, str, float)  # widget_data, date_str, mtime
    finished_loading = pyqtSignal()
    
    def __init__(self, storage_dir):
        super().__init__()
        self.storage_dir = storage_dir
        self._is_running = True
        
    def stop(self):
        self._is_running = False
        
    def run(self):
        """Load images in background thread"""
        try:
            if not self.storage_dir.exists():
                self.finished_loading.emit()
                return
            
            # Get all image files
            self.progress.emit(0, 0, "Scanning for images...")
            image_files = []
            for ext in ['*.jpg', '*.jpeg', '*.png']:
                image_files.extend(self.storage_dir.glob(ext))
            
            if not image_files:
                self.finished_loading.emit()
                return
                
            image_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            total_images = len(image_files)
            
            # Load images
            for idx, image_path in enumerate(image_files):
                if not self._is_running:
                    break
                    
                self.progress.emit(idx + 1, total_images, f"Loading {image_path.name}...")
                
                # Get date for grouping
                mtime = image_path.stat().st_mtime
                date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                
                # Load thumbnail
                try:
                    pixmap = QPixmap(str(image_path))
                    if not pixmap.isNull() and self._is_running:
                        scaled_pixmap = pixmap.scaled(180, 135, Qt.AspectRatioMode.KeepAspectRatio, 
                                                     Qt.TransformationMode.FastTransformation)
                        
                        # Emit data for main thread to create widget
                        widget_data = {
                            'path': str(image_path),
                            'name': image_path.name,
                            'pixmap': scaled_pixmap,
                            'mtime': mtime
                        }
                        if self._is_running:  # Check again before emitting
                            self.image_loaded.emit(widget_data, date_str, mtime)
                except Exception as e:
                    logger.debug(f"Failed to load thumbnail for {image_path}: {e}")
                
                # Check if we should continue
                if not self._is_running:
                    break
                
                # Small delay to keep UI responsive
                if idx % 10 == 0:
                    self.msleep(10)
                    
            self.finished_loading.emit()
            
        except Exception as e:
            logger.error(f"Error in gallery loader: {e}")
            self.finished_loading.emit()

class GalleryTab(QWidget):
    """Photo gallery tab for viewing all captured images"""
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.selected_items = set()
        self.current_full_image = None
        self.email_handler = None  # Will be set from main window
        self.loader_thread = None
        self.images_by_date = {}
        self.date_widgets = {}
        self.gallery_items = []
        self.loaded_dates = set()  # Track which dates have been loaded
        self.today_date = datetime.now().strftime('%Y-%m-%d')
        self.current_focus_index = -1  # Track currently focused item for arrow navigation
        self.initial_batch_size = 30  # Images to load for the newest day
        self.scroll_batch_size = 60   # Images to load per scroll batch
        self.scroll_trigger_percent = 80  # Threshold percentage to trigger lazy load
        self.setup_ui()
        
        # Mark that gallery hasn't been loaded yet (lazy loading)
        self.gallery_loaded = False
        
        # Log configuration details
        storage_config = self.config.get('storage', {})
        save_dir = storage_config.get('save_dir', str(Path.home() / 'BirdPhotos'))
        logger.info(f"Gallery initialized - Storage config: {storage_config}")
        logger.info(f"Gallery will look for photos in: {save_dir}")
        logger.info(f"Today's date for gallery: {self.today_date}")
        
        # Setup timer to check for new images in today's folder only
        self.new_image_timer = QTimer()
        self.new_image_timer.timeout.connect(self.check_for_new_images)
        self.new_image_timer.start(10000)  # Check every 10 seconds
    
    def closeEvent(self, event):
        """Clean up when gallery tab is closed"""
        if self.loader_thread and self.loader_thread.isRunning():
            self.loader_thread.stop()
            self.loader_thread.wait(1000)  # Wait up to 1 second
        if hasattr(self, 'new_image_timer'):
            self.new_image_timer.stop()
        super().closeEvent(event)
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        # Refresh button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_gallery)
        toolbar_layout.addWidget(self.refresh_btn)
        
        # Selection info
        self.selection_label = QLabel("0 selected")
        toolbar_layout.addWidget(self.selection_label)
        
        # Email button
        self.email_btn = QPushButton("Email Selected")
        self.email_btn.clicked.connect(self.email_selected)
        self.email_btn.setEnabled(False)
        toolbar_layout.addWidget(self.email_btn)
        
        # Delete button
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.clicked.connect(self.delete_selected)
        self.delete_btn.setEnabled(False)
        toolbar_layout.addWidget(self.delete_btn)
        
        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)
        
        # Progress bar for loading
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        
        # Gallery scroll area
        self.scroll_area = QScrollArea()
        self.scroll_widget = QWidget()
        self.gallery_layout = QGridLayout(self.scroll_widget)
        self.gallery_layout.setSpacing(10)
        
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area)
        
        # Connect scroll event for lazy loading
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.on_scroll_changed)
        
        # Status label at bottom
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("QLabel { color: #666; padding: 5px; }")
        layout.addWidget(self.status_label)
        
        # Enable keyboard shortcuts
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def set_status_message(self, message, color=None):
        """Set status message with optional color"""
        self.status_label.setText(message)
        if color:
            self.status_label.setStyleSheet(f"QLabel {{ color: {color}; padding: 5px; }}")
        else:
            # Reset to default gray
            self.status_label.setStyleSheet("QLabel { color: #666; padding: 5px; }")
        
    def keyPressEvent(self, event):
        """Handle keyboard events"""
        if event.key() == Qt.Key.Key_Delete and self.selected_items:
            self.delete_selected()
        elif event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Select all
            self.select_all()
        elif event.key() == Qt.Key.Key_Escape:
            # Clear selection
            self.clear_selection()
        elif event.key() == Qt.Key.Key_Left:
            # Navigate to previous image
            self.navigate_image(-1)
        elif event.key() == Qt.Key.Key_Right:
            # Navigate to next image
            self.navigate_image(1)
        else:
            # Call parent implementation for other keys
            super().keyPressEvent(event)
    
    def navigate_image(self, direction):
        """Navigate through gallery images with arrow keys"""
        if not self.gallery_items:
            return
        
        # If no current focus, start with first item
        if self.current_focus_index == -1:
            self.current_focus_index = 0
        else:
            # Move focus in the specified direction
            new_index = self.current_focus_index + direction
            # Wrap around at boundaries
            if new_index < 0:
                new_index = len(self.gallery_items) - 1
            elif new_index >= len(self.gallery_items):
                new_index = 0
            self.current_focus_index = new_index
        
        # Update visual focus and scroll to item
        self.update_focus_highlight()
        self.scroll_to_focused_item()
        
        logger.debug(f"Navigated to image {self.current_focus_index + 1} of {len(self.gallery_items)}")
    
    def update_focus_highlight(self):
        """Update the visual highlight for the currently focused item"""
        # Remove highlight from all items
        for i, (path, widget) in enumerate(self.gallery_items):
            if i == self.current_focus_index:
                # Add highlight to focused item
                widget.setStyleSheet("""
                    QWidget {
                        border: 3px solid #4CAF50;
                        border-radius: 8px;
                        background-color: rgba(76, 175, 80, 0.1);
                    }
                """)
            else:
                # Remove highlight from non-focused items
                widget.setStyleSheet("""
                    QWidget {
                        border: 1px solid #444;
                        border-radius: 8px;
                        background-color: #2b2b2b;
                    }
                """)
    
    def scroll_to_focused_item(self):
        """Scroll the gallery to show the currently focused item"""
        if self.current_focus_index >= 0 and self.current_focus_index < len(self.gallery_items):
            path, widget = self.gallery_items[self.current_focus_index]
            # Ensure the widget is visible in the scroll area
            self.scroll_area.ensureWidgetVisible(widget)
    
    def on_image_clicked(self, image_path):
        """Handle image click - set focus and show full image"""
        # Find the index of the clicked image
        for i, (path, widget) in enumerate(self.gallery_items):
            if path == image_path:
                self.current_focus_index = i
                break
        
        # Update visual focus
        self.update_focus_highlight()
        
        # Set focus to the gallery tab for keyboard navigation
        self.setFocus()
        
        # Show full image
        self.show_full_image(image_path)
        
        logger.debug(f"Image clicked: {image_path}, focus set to index {self.current_focus_index}")
            
    
    def refresh_gallery(self):
        """Refresh the gallery - reload all loaded dates"""
        try:
            logger.info("Gallery refresh button clicked")
            self.set_status_message("Refreshing gallery...", "#ffcc00")
            
            # Show progress bar
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Refreshing gallery...")
            
            # Count images before refresh
            old_total_images = sum(len(images) for images in self.images_by_date.values())
            logger.info(f"Images before refresh: {old_total_images}")
            
            # If gallery was never loaded, just load today's photos
            if not self.gallery_loaded:
                logger.info("Gallery never loaded, loading today's photos")
                self.load_today_photos()
                self.gallery_loaded = True
                return
            
            # Save dates to reload before clearing
            loaded_dates_copy = self.loaded_dates.copy() if self.loaded_dates else {self.today_date}
            
            # Clear current display
            self.clear_gallery()
            self.images_by_date.clear()
            self.date_widgets.clear()
            self.gallery_items.clear()
            self.selected_items.clear()
            # Don't clear loaded_dates yet - we need it for reload
            self.current_focus_index = -1  # Reset focus
            # Clear loaded image tracking so images can be reloaded
            if hasattr(self, 'loaded_image_paths'):
                self.loaded_image_paths.clear()
            if hasattr(self, 'date_load_info'):
                self.date_load_info.clear()
            self.update_selection_label()
            logger.info(f"Reloading dates: {loaded_dates_copy}")
            
            storage_dir = Path(self.config.get('storage', {}).get('save_dir', 
                                               str(Path.home() / 'BirdPhotos')))
            
            # Clear loaded_dates now that we have the copy
            self.loaded_dates.clear()
            
            if storage_dir.exists():
                # Reload each date that was previously loaded
                for date_str in sorted(loaded_dates_copy, reverse=True):
                    date_folder = storage_dir / date_str
                    if date_folder.exists() and date_folder.is_dir():
                        logger.info(f"Reloading date: {date_str}")
                        self.load_date_folder(date_str, date_folder, limit=self.initial_batch_size)
                        self.loaded_dates.add(date_str)
                    else:
                        logger.warning(f"Date folder no longer exists: {date_folder}")
            
            # Check if we should auto-load yesterday (if today has < 16 photos)
            today_count = len(self.images_by_date.get(self.today_date, []))
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
            logger.info(f"Refresh auto-load check: today_count={today_count}, yesterday='{yesterday}', loaded_dates={self.loaded_dates}")
            
            if today_count > 0 and today_count < 16 and yesterday not in self.loaded_dates:
                yesterday_folder = storage_dir / yesterday
                logger.info(f"Checking yesterday folder: {yesterday_folder}, exists={yesterday_folder.exists()}")
                if yesterday_folder.exists() and yesterday_folder.is_dir():
                    logger.info(f"Auto-loading yesterday's photos (today has only {today_count})...")
                    self.set_status_message(f"Loading more photos (today has only {today_count})...", "#ffcc00")
                    self.progress_bar.setFormat("Loading yesterday's photos...")
                    QApplication.processEvents()  # Force UI update
                    
                    # Load yesterday's photos
                    self.load_date_folder(yesterday, yesterday_folder, limit=self.initial_batch_size)
                    self.loaded_dates.add(yesterday)
                    logger.info(f"Yesterday photos loaded via refresh, loaded_dates now: {self.loaded_dates}")
            
            # Count images after potential yesterday load
            new_total_images = sum(len(images) for images in self.images_by_date.values())
            logger.info(f"Images after refresh: {new_total_images}")
            
            # Update status
            if new_total_images == 0:
                # No images found at all
                self.status_label.setText("No images found in gallery")
                self.set_status_message("No images found - gallery may be empty", "#ff9800")
                # Show empty message in gallery
                empty_label = QLabel("No bird photos found.\nPhotos will appear here after motion detection captures.")
                empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty_label.setStyleSheet("color: #999; font-size: 14px; padding: 50px;")
                self.gallery_layout.addWidget(empty_label)
            elif new_total_images == old_total_images and old_total_images > 0 and today_count >= 16:
                # No new images found, show "up to date" message temporarily
                self.status_label.setText("Gallery is up to date")
                QTimer.singleShot(2000, lambda: self.status_label.setText(f"{new_total_images} images from {len(self.images_by_date)} days"))
            else:
                self.status_label.setText(f"{new_total_images} images from {len(self.images_by_date)} days")
            
            # Hide progress bar
            self.progress_bar.setVisible(False)
            
        except Exception as e:
            logger.error(f"Error refreshing gallery: {e}")
            self.set_status_message("Error refreshing gallery", "#ff6464")
    
    def load_today_photos(self):
        """Load only today's photos on startup"""
        try:
            # Show loading status immediately
            self.set_status_message("Loading gallery...", "#ffcc00")
            QApplication.processEvents()  # Force UI update
            
            # Show progress bar
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Scanning for photos...")
            
            storage_dir = Path(self.config.get('storage', {}).get('save_dir', 
                                               str(Path.home() / 'BirdPhotos')))
            
            logger.info(f"Gallery looking for photos in: {storage_dir}")
            
            if not storage_dir.exists():
                logger.warning(f"Photos directory does not exist: {storage_dir}")
                self.status_label.setText("No photos directory found")
                # Hide progress bar
                self.progress_bar.setVisible(False)
                return
            
            # Load only today's folder
            today_folder = storage_dir / self.today_date
            logger.info(f"Looking for today's folder: {today_folder}")
            
            if today_folder.exists() and today_folder.is_dir():
                logger.info(f"Loading photos from: {today_folder}")
                self.set_status_message("Loading today's photos...", "#ffcc00")
                QApplication.processEvents()  # Force UI update
                
                self.load_date_folder(self.today_date, today_folder, limit=self.initial_batch_size)
                self.loaded_dates.add(self.today_date)
                
                # Check if we should load yesterday too (if today has < 16 photos)
                today_count = len(self.images_by_date.get(self.today_date, []))
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                
                logger.info(f"Auto-load check: today_count={today_count}, yesterday='{yesterday}', loaded_dates={self.loaded_dates}")
                
                if today_count < 16 and yesterday not in self.loaded_dates:
                    yesterday_folder = storage_dir / yesterday
                    logger.info(f"Checking yesterday folder: {yesterday_folder}, exists={yesterday_folder.exists()}")
                    if yesterday_folder.exists() and yesterday_folder.is_dir():
                        logger.info(f"Today only has {today_count} photos, loading yesterday's photos too...")
                        self.set_status_message(f"Loading more photos (today has only {today_count})...", "#ffcc00")
                        self.progress_bar.setFormat("Loading yesterday's photos...")
                        QApplication.processEvents()  # Force UI update
                        
                        # Load yesterday's photos (first batch)
                        has_more = self.load_date_folder(
                            yesterday,
                            yesterday_folder,
                            limit=self.initial_batch_size,
                            offset=0
                        )
                        self.loaded_dates.add(yesterday)
                        logger.info(
                            f"Yesterday photos loaded ({self.initial_batch_size} images), has_more={has_more}"
                        )
                else:
                    logger.info(f"Not loading yesterday: count check={today_count < 16}, not in loaded={yesterday not in self.loaded_dates}")
                
                # Update status with final count
                total_images = sum(len(images) for images in self.images_by_date.values())
                self.status_label.setText(f"Loaded {total_images} images from {len(self.images_by_date)} days")
                # Hide progress bar
                self.progress_bar.setVisible(False)
            else:
                logger.info(f"No photos folder for today: {today_folder}")
                
                # Try to load yesterday's photos instead
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                yesterday_folder = storage_dir / yesterday
                
                if yesterday_folder.exists() and yesterday_folder.is_dir():
                    logger.info(f"Loading yesterday's photos from: {yesterday_folder}")
                    self.set_status_message("No photos today - loading yesterday's photos...", "#ffcc00")
                    self.progress_bar.setFormat("Loading yesterday's photos...")
                    
                    # Create and start loader thread for yesterday
                    self.loader_thread = GalleryLoaderThread(yesterday_folder)
                    self.loader_thread.image_loaded.connect(self.on_image_loaded)
                    self.loader_thread.progress.connect(self.on_loader_progress)
                    self.loader_thread.finished_loading.connect(self.on_loading_finished)
                    self.loader_thread.start()
                else:
                    self.status_label.setText("No photos for today or yesterday")
                    # Hide progress bar
                    self.progress_bar.setVisible(False)
                
        except Exception as e:
            logger.error(f"Error loading today's photos: {e}")
            self.set_status_message("Error loading photos", "#ff6464")
    
    def load_date_folder(self, date_str, folder_path, limit=None, offset=0):
        """Load photos from a specific date folder with pagination
        
        Args:
            date_str: Date string (YYYY-MM-DD)
            folder_path: Path to the folder
            limit: Maximum number of images to load (defaults to scroll batch size)
            offset: Starting offset for loading (default 0)
        """
        try:
            if limit is None:
                limit = self.scroll_batch_size

            logger.info(f"Loading date folder: {date_str} from path: {folder_path} (limit={limit}, offset={offset})")
            
            # Create date section if it doesn't exist
            if date_str not in self.date_widgets:
                logger.info(f"Creating new date section for: {date_str}")
                self.create_date_section(date_str)
                self.images_by_date[date_str] = []
            
            # Track loaded image paths per date
            if not hasattr(self, 'loaded_image_paths'):
                self.loaded_image_paths = {}
            if date_str not in self.loaded_image_paths:
                self.loaded_image_paths[date_str] = set()
            
            # Get existing images for this date
            existing_paths = self.loaded_image_paths[date_str]
            logger.info(f"Already loaded images for {date_str}: {len(existing_paths)}")
            
            # Search for image files with multiple extensions
            image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp']
            all_images = []
            
            for ext in image_extensions:
                found_images = list(folder_path.glob(f'**/{ext}'))
                all_images.extend(found_images)
                logger.info(f"Found {len(found_images)} {ext} files in {folder_path}")
            
            logger.info(f"Total image files found in {folder_path}: {len(all_images)}")
            
            # Sort images by modification time (newest first)
            sorted_images = sorted(all_images, key=lambda p: p.stat().st_mtime, reverse=True)
            
            # Get the batch to load based on offset and limit
            batch_images = sorted_images[offset:offset + limit]
            logger.info(f"Loading batch: {len(batch_images)} images from offset {offset}")
            
            # Load new images with memory management
            new_images = 0
            
            for image_path in batch_images:
                    
                logger.debug(f"Processing image: {image_path}")
                if str(image_path) not in existing_paths:
                    try:
                        # Load and add image with explicit memory management
                        pixmap = QPixmap(str(image_path))
                        if not pixmap.isNull():
                            # Create smaller thumbnail to save memory
                            scaled_pixmap = pixmap.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, 
                                                        Qt.TransformationMode.FastTransformation)
                            
                            # Explicitly delete the original large pixmap
                            del pixmap
                            
                            self.add_image_to_gallery(date_str, image_path, scaled_pixmap)
                            self.loaded_image_paths[date_str].add(str(image_path))
                            new_images += 1
                            logger.debug(f"Added image to gallery: {image_path}")
                            
                            # Periodic garbage collection every 12 images
                            if new_images % 12 == 0:
                                import gc
                                gc.collect()
                                QApplication.processEvents()  # Keep UI responsive
                        else:
                            logger.warning(f"Failed to load pixmap for: {image_path}")
                    except Exception as e:
                        logger.error(f"Error loading image {image_path}: {e}")
                else:
                    logger.debug(f"Image already loaded: {image_path}")
            
            logger.info(f"Added {new_images} new images for date {date_str}")
            
            # Update status
            total_images = sum(len(images) for images in self.images_by_date.values())
            self.status_label.setText(f"{total_images} images from {len(self.images_by_date)} days")
            logger.info(f"Gallery now has {total_images} total images from {len(self.images_by_date)} days")
            
            # Store info about remaining images for this date
            if not hasattr(self, 'date_load_info'):
                self.date_load_info = {}
            self.date_load_info[date_str] = {
                'total': len(sorted_images),
                'loaded': len(self.loaded_image_paths[date_str]),
                'has_more': (offset + limit) < len(sorted_images)
            }
            
            # Return whether there are more images to load
            has_more = (offset + limit) < len(sorted_images)
            logger.info(f"Date {date_str}: loaded {len(self.loaded_image_paths[date_str])}/{len(sorted_images)} images, has_more={has_more}")
            return has_more
            
        except Exception as e:
            logger.error(f"Error loading date folder {date_str}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def add_image_to_gallery(self, date_str, image_path, scaled_pixmap):
        """Add a single image to the gallery"""
        logger.debug(f"Adding image to gallery UI: {image_path} for date {date_str}")
        
        # Get the date section info
        if date_str not in self.date_widgets:
            logger.error(f"Date section {date_str} not found in date_widgets")
            return
            
        date_info = self.date_widgets[date_str]
        if not isinstance(date_info, dict) or 'widget' not in date_info:
            logger.error(f"Invalid date_info structure for {date_str}: {type(date_info)} - {date_info}")
            return
            
        grid_widget = date_info['widget']
        if not hasattr(grid_widget, 'layout'):
            logger.error(f"Grid widget for {date_str} has no layout method: {type(grid_widget)}")
            return
            
        grid_layout = grid_widget.layout()
        
        # Get current number of images for this date
        images_in_date = len(self.images_by_date[date_str])
        
        # Calculate position in the grid (4 columns)
        col = images_in_date % 4
        row = images_in_date // 4
        
        logger.debug(f"Adding image to date {date_str} grid at row {row}, col {col}")
        
        # Create gallery item
        item_widget = self.create_gallery_item(str(image_path), scaled_pixmap)
        grid_layout.addWidget(item_widget, row, col)
        
        # Update tracking
        self.images_by_date[date_str].append(str(image_path))
        self.gallery_items.append((str(image_path), item_widget))
        
        logger.debug(f"Gallery now has {len(self.gallery_items)} total items")
    
    def check_for_new_images(self):
        """Check for new images in today's folder only"""
        try:
            # Skip auto-refresh until initial gallery load has occurred
            if not getattr(self, 'gallery_loaded', False):
                return

            storage_dir = Path(self.config.get('storage', {}).get('save_dir', 
                                               str(Path.home() / 'BirdPhotos')))
            
            if not storage_dir.exists():
                return
            
            # Update today's date in case we crossed midnight
            self.today_date = datetime.now().strftime('%Y-%m-%d')
            
            # Check today's folder
            today_folder = storage_dir / self.today_date
            if today_folder.exists() and today_folder.is_dir():
                # Count current images on disk (match supported extensions)
                image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp']
                images_on_disk = 0
                for ext in image_extensions:
                    images_on_disk += len(list(today_folder.glob(f'**/{ext}')))

                current_loaded = len(self.images_by_date.get(self.today_date, []))
                date_info = getattr(self, 'date_load_info', {}).get(self.today_date, {})
                known_total = date_info.get('total', current_loaded)

                # Only load when new captures increase total files beyond what we've already catalogued
                if images_on_disk > known_total:
                    new_images = images_on_disk - known_total
                    logger.info(f"Detected {new_images} new files for today")
                    load_limit = min(self.scroll_batch_size, new_images)
                    self.load_date_folder(
                        self.today_date,
                        today_folder,
                        limit=load_limit,
                        offset=0
                    )

        except Exception as e:
            logger.error(f"Error checking for new images: {e}")
    
    def add_new_image_immediately(self, image_path):
        """Add a new image immediately when captured"""
        try:
            path = Path(image_path)
            if not path.exists():
                return
            
            # Get the date from the image path
            date_str = path.parent.name
            # Check if this looks like a date folder (YYYY-MM-DD format)
            if not date_str or len(date_str) != 10 or date_str.count('-') != 2:
                date_str = self.today_date
            
            logger.debug(f"Adding new image {path.name} to date section: {date_str}")
            
            # Load image
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio, 
                                            Qt.TransformationMode.SmoothTransformation)
                
                # Create date section if needed
                if date_str not in self.date_widgets:
                    self.create_date_section(date_str)
                    self.images_by_date[date_str] = []
                    self.loaded_dates.add(date_str)
                
                # Add to gallery
                self.add_image_to_gallery(date_str, path, scaled_pixmap)
                logger.info(f"Added new image to gallery: {path.name}")
                
        except Exception as e:
            logger.error(f"Error adding new image immediately: {e}")
    
    def on_scroll_changed(self, value):
        """Handle scroll changes for lazy loading"""
        try:
            # Check if we're near the bottom
            scrollbar = self.scroll_area.verticalScrollBar()
            if scrollbar.maximum() > 0:
                scroll_percentage = (value / scrollbar.maximum()) * 100

                # If scrolled past threshold, try to load more dates
                if scroll_percentage > self.scroll_trigger_percent:
                    self.load_previous_dates()
                    
        except Exception as e:
            logger.error(f"Error in scroll handler: {e}")
    
    def load_previous_dates(self):
        """Load more photos (20 at a time) when scrolling down"""
        try:
            # Prevent concurrent loading
            if hasattr(self, 'is_loading_more') and self.is_loading_more:
                return
            self.is_loading_more = True
            
            # Show loading status
            old_status = self.status_label.text()
            self.set_status_message("Loading more photos...", "#ffcc00")
            QApplication.processEvents()  # Force UI update
            
            storage_dir = Path(self.config.get('storage', {}).get('save_dir', 
                                               str(Path.home() / 'BirdPhotos')))
            
            if not storage_dir.exists():
                self.set_status_message("No storage directory found", "#ff6464")
                self.is_loading_more = False
                return
            
            # First check if current dates have more images to load
            if hasattr(self, 'date_load_info'):
                for date_str in sorted(self.date_load_info.keys(), reverse=True):
                    info = self.date_load_info[date_str]
                    if info.get('has_more', False):
                        # Load next batch from this date
                        date_folder = storage_dir / date_str
                        offset = info['loaded']
                        logger.info(f"Loading more from {date_str}, offset={offset}")
                        
                        has_more = self.load_date_folder(
                            date_str,
                            date_folder,
                            limit=self.scroll_batch_size,
                            offset=offset
                        )

                        # Update status to show completion
                        total_images = sum(len(images) for images in self.images_by_date.values())
                        self.set_status_message(f"Loaded {total_images} images from {len(self.images_by_date)} days")

                        # Reset loading flag AFTER status update
                        self.is_loading_more = False
                        return
            
            # If no existing dates have more, load from a new date
            all_dates = []
            for folder in storage_dir.iterdir():
                if folder.is_dir() and folder.name.count('-') == 2:  # Basic date format check
                    try:
                        # Validate it's a proper date
                        datetime.strptime(folder.name, '%Y-%m-%d')
                        all_dates.append(folder.name)
                    except ValueError:
                        continue
            
            all_dates.sort(reverse=True)
            
            # Find the next date to load
            for date_str in all_dates:
                if date_str not in self.loaded_dates:
                    # Load first batch from this new date
                    date_folder = storage_dir / date_str
                    logger.info(f"Loading new date: {date_str}")
                    self.set_status_message(f"Loading photos from {date_str}...", "#ffcc00")
                    QApplication.processEvents()  # Force UI update
                    
                    # Load first batch (24 images) from new date
                    has_more = self.load_date_folder(
                        date_str,
                        date_folder,
                        limit=self.initial_batch_size,
                        offset=0
                    )
                    self.loaded_dates.add(date_str)

                    # Update status to show completion
                    total_images = sum(len(images) for images in self.images_by_date.values())
                    self.set_status_message(f"Loaded {total_images} images from {len(self.images_by_date)} days")

                    # Reset loading flag AFTER status update
                    self.is_loading_more = False
                    return
            
            # No more dates to load
            total_images = sum(len(images) for images in self.images_by_date.values())
            self.set_status_message(f"Loaded {total_images} images from {len(self.images_by_date)} days")
            self.is_loading_more = False
                    
        except Exception as e:
            logger.error(f"Error loading previous dates: {e}")
            self.set_status_message("Error loading photos", "#ff6464")
            self.is_loading_more = False
    
    def check_scroll_position(self):
        """Check if we need to load more images based on scroll position"""
        try:
            # Don't check if already loading
            if hasattr(self, 'is_loading_more') and self.is_loading_more:
                return

            scrollbar = self.scroll_area.verticalScrollBar()
            if scrollbar.maximum() > 0:
                scroll_percentage = (scrollbar.value() / scrollbar.maximum()) * 100
                if scroll_percentage > self.scroll_trigger_percent:
                    # Still near bottom, load more
                    self.load_previous_dates()
        except Exception as e:
            logger.debug(f"Error checking scroll position: {e}")
    
    def create_date_section(self, date_str, prepend=False):
        """Create a date section in the gallery"""
        # Date header - format the date nicely
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%A, %B %d, %Y')  # e.g., "Sunday, August 04, 2024"
        except:
            formatted_date = date_str
            
        date_label = QLabel(formatted_date)
        date_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #ffffff;
                background-color: #404040;
                padding: 10px 15px;
                border-radius: 5px;
                margin: 10px 0px;
            }
        """)
        
        # Grid for this date's images
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(10)
        
        # Add to main gallery layout
        if prepend and self.gallery_layout.count() > 0:
            # Insert at the top
            self.gallery_layout.insertWidget(0, date_label)
            self.gallery_layout.insertWidget(1, grid_widget)
        else:
            # Add at the end
            row = self.gallery_layout.rowCount()
            self.gallery_layout.addWidget(date_label, row, 0, 1, 4)
            self.gallery_layout.addWidget(grid_widget, row + 1, 0, 1, 4)
        
        # Store both widget and row information for compatibility
        row = self.gallery_layout.rowCount() - 1  # Row where the grid was added
        self.date_widgets[date_str] = {
            'widget': grid_widget,
            'label': date_label,
            'row': row
        }
    
    def load_photos(self):
        """Load all photos from the storage directory - non-blocking"""
        # Stop any existing loader
        if self.loader_thread and self.loader_thread.isRunning():
            self.loader_thread.stop()
            self.loader_thread.wait()
        
        # Clear existing items
        self.clear_gallery()
        
        # Reset data structures
        self.images_by_date.clear()
        self.date_widgets.clear()
        self.gallery_items.clear()
        self.selected_items.clear()
        self.loaded_dates.clear()
        self.current_focus_index = -1  # Reset focus
        # Clear loaded image tracking
        if hasattr(self, 'loaded_image_paths'):
            self.loaded_image_paths.clear()
        if hasattr(self, 'date_load_info'):
            self.date_load_info.clear()
        self.update_selection_label()
        
        # Get storage directory
        storage_dir = Path(self.config.get('storage', {}).get('save_dir', 
                                           str(Path.home() / 'BirdPhotos')))
        
        if not storage_dir.exists():
            self.status_label.setText("No photos directory found")
            return
        
        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.refresh_btn.setEnabled(False)
        self.set_status_message("Loading photos...", "#ffcc00")
        
        # Start background loader
        self.loader_thread = GalleryLoader(storage_dir)
        self.loader_thread.progress.connect(self.on_load_progress)
        self.loader_thread.image_loaded.connect(self.on_image_loaded)
        self.loader_thread.finished_loading.connect(self.on_loading_finished)
        self.loader_thread.start()
    
    def clear_gallery(self):
        """Clear all gallery widgets with aggressive memory cleanup"""
        logger.info("Clearing gallery with memory cleanup...")
        
        # Clear layout and explicitly delete widgets
        while self.gallery_layout.count():
            item = self.gallery_layout.takeAt(0)
            if item.widget():
                widget = item.widget()
                
                # Find and delete any pixmaps in child widgets
                for child in widget.findChildren(QLabel):
                    if child.pixmap():
                        child.clear()
                
                widget.deleteLater()
        
        # Clear tracking collections
        if hasattr(self, 'gallery_items'):
            self.gallery_items.clear()
        if hasattr(self, 'selected_items'):
            self.selected_items.clear()
        if hasattr(self, 'images_by_date'):
            self.images_by_date.clear()
        if hasattr(self, 'date_widgets'):
            self.date_widgets.clear()
        # Note: loaded_dates is NOT cleared here - managed by refresh logic
        if hasattr(self, 'current_focus_index'):
            self.current_focus_index = -1
        
        # Force garbage collection
        import gc
        gc.collect()
        
        logger.info("Gallery cleared and memory cleaned up")
    
    @pyqtSlot(int, int, str)
    def on_load_progress(self, current, total, message):
        """Update progress bar"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"{current}/{total} - {message}")
    
    @pyqtSlot(object, str, float)
    def on_image_loaded(self, widget_data, date_str, mtime):
        """Add loaded image to gallery"""
        
        # Group by date
        if date_str not in self.images_by_date:
            self.images_by_date[date_str] = []
            
            # Create date header
            date_label = QLabel(datetime.fromtimestamp(mtime).strftime('%A, %B %d, %Y'))
            date_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
            
            row = len(self.date_widgets) * 100  # Space for images
            self.gallery_layout.addWidget(date_label, row, 0, 1, 4)
            self.date_widgets[date_str] = {'label': date_label, 'row': row + 1}
        
        # Add image to date group
        date_info = self.date_widgets[date_str]
        images_in_date = len(self.images_by_date[date_str])
        col = images_in_date % 4
        row = date_info['row'] + (images_in_date // 4)
        
        # Create thumbnail widget
        item_widget = self.create_gallery_item(widget_data['path'], widget_data['pixmap'])
        self.gallery_layout.addWidget(item_widget, row, col)
        
        self.images_by_date[date_str].append(widget_data['path'])
        self.gallery_items.append((widget_data['path'], item_widget))
    
    @pyqtSlot()
    def on_loading_finished(self):
        """Handle loading completion"""
        self.progress_bar.setVisible(False)
        self.refresh_btn.setEnabled(True)
        
        # Check if we loaded today's photos and if count is less than 16
        today_count = len(self.images_by_date.get(self.today_date, []))
        total_images = sum(len(images) for images in self.images_by_date.values())
        
        # If today has less than 16 photos and we haven't loaded yesterday yet, load it
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        if today_count > 0 and today_count < 16 and yesterday not in self.images_by_date:
            storage_dir = Path(self.config.get('storage', {}).get('save_dir', 
                                               str(Path.home() / 'BirdPhotos')))
            yesterday_folder = storage_dir / yesterday
            
            if yesterday_folder.exists() and yesterday_folder.is_dir():
                logger.info(f"Today only has {today_count} photos, loading yesterday's photos too...")
                self.set_status_message(f"Loading more photos (today has only {today_count})...", "#ffcc00")
                
                # Show progress bar again
                self.progress_bar.setVisible(True)
                self.progress_bar.setFormat("Loading yesterday's photos...")
                
                # Load yesterday's photos
                self.loader_thread = GalleryLoaderThread(yesterday_folder)
                self.loader_thread.image_loaded.connect(self.on_image_loaded)
                self.loader_thread.progress.connect(self.on_loader_progress)
                self.loader_thread.finished_loading.connect(self.on_loading_finished)
                self.loader_thread.start()
                return
        
        # Normal completion - reset to normal color
        self.set_status_message(f"Loaded {total_images} images from {len(self.images_by_date)} days")
    
    
    def create_gallery_item(self, image_path, scaled_pixmap):
        """Create a gallery item widget"""
        container = QWidget()
        container.setFixedSize(200, 200)
        container.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border: 2px solid transparent;
                border-radius: 5px;
            }
            QWidget:hover {
                border-color: #555;
            }
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Checkbox for selection
        checkbox = QCheckBox()
        checkbox.stateChanged.connect(lambda state: self.on_item_selected(image_path, state))
        layout.addWidget(checkbox, alignment=Qt.AlignmentFlag.AlignRight)
        
        # Thumbnail
        thumb_label = QLabel()
        thumb_label.setPixmap(scaled_pixmap)
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setStyleSheet("QLabel { background-color: #000; }")
        thumb_label.mousePressEvent = lambda e: self.on_image_clicked(image_path) if e.button() == Qt.MouseButton.LeftButton else None
        thumb_label.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(thumb_label)
        
        # Filename
        name_label = QLabel(Path(image_path).name)
        name_label.setStyleSheet("color: #ccc; font-size: 10px;")
        name_label.setWordWrap(True)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)
        
        # Time ago label
        time_ago = self.get_time_ago_text(image_path)
        time_label = QLabel(time_ago)
        time_label.setStyleSheet("color: #999; font-size: 9px; font-style: italic;")
        time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(time_label)
        
        return container
    
    def get_time_ago_text(self, image_path):
        """Extract timestamp from filename and return human-readable time ago text"""
        try:
            import re
            
            # Extract timestamp from filename (motion_1754413128.jpeg -> 1754413128)
            filename = Path(image_path).name
            match = re.search(r'motion_(\d+)\.jpeg', filename)
            
            if match:
                timestamp = int(match.group(1))
                # Convert timestamp to datetime
                image_time = datetime.fromtimestamp(timestamp)
                now = datetime.now()
                
                # Calculate time difference
                diff = now - image_time
                
                # Format as human-readable text
                if diff.days > 0:
                    if diff.days == 1:
                        return "1 day ago"
                    else:
                        return f"{diff.days} days ago"
                elif diff.seconds > 3600:  # More than 1 hour
                    hours = diff.seconds // 3600
                    if hours == 1:
                        return "1 hour ago"
                    else:
                        return f"{hours} hours ago"
                elif diff.seconds > 60:  # More than 1 minute
                    minutes = diff.seconds // 60
                    if minutes == 1:
                        return "1 minute ago"
                    else:
                        return f"{minutes} minutes ago"
                else:
                    return "Just now"
            else:
                # Fallback: use file modification time
                stat = Path(image_path).stat()
                image_time = datetime.fromtimestamp(stat.st_mtime)
                now = datetime.now()
                diff = now - image_time
                
                if diff.days > 0:
                    return f"{diff.days} days ago"
                elif diff.seconds > 3600:
                    hours = diff.seconds // 3600
                    return f"{hours} hours ago"
                elif diff.seconds > 60:
                    minutes = diff.seconds // 60
                    return f"{minutes} minutes ago"
                else:
                    return "Just now"
                    
        except Exception as e:
            logger.debug(f"Error getting time ago for {image_path}: {e}")
            return ""
    
    def on_item_selected(self, path, state):
        """Handle item selection"""
        if state == 2:  # Checked
            self.selected_items.add(path)
        else:
            self.selected_items.discard(path)
        self.update_selection_label()
    
    def update_selection_label(self):
        """Update selection count and button states"""
        count = len(self.selected_items)
        self.selection_label.setText(f"{count} selected")
        self.email_btn.setEnabled(count > 0)
        self.delete_btn.setEnabled(count > 0)
    
    def select_all(self):
        """Select all images"""
        for path, widget in self.gallery_items:
            checkbox = widget.findChild(QCheckBox)
            if checkbox:
                checkbox.setChecked(True)
    
    def clear_selection(self):
        """Clear all selections"""
        for path, widget in self.gallery_items:
            checkbox = widget.findChild(QCheckBox)
            if checkbox:
                checkbox.setChecked(False)
    
    def get_all_image_paths(self):
        """Get all image paths in the current gallery view"""
        all_paths = []
        # Collect paths in date order
        for date_str in sorted(self.images_by_date.keys(), reverse=True):
            all_paths.extend(self.images_by_date[date_str])
        return all_paths
                
    def show_full_image(self, image_path):
        """Show full-size image in a dialog with keyboard navigation"""
        # Convert to Path object if it's a string
        if isinstance(image_path, str):
            image_path = Path(image_path)
        
        # Create custom dialog for keyboard handling
        self.current_full_image = str(image_path)
        dialog = ImageViewerDialog(self, image_path, self.get_all_image_paths())
        dialog.exec()
        
    def delete_selected(self):
        """Delete selected images"""
        if not self.selected_items:
            return
            
        # Confirm deletion
        reply = QMessageBox.question(
            self, 
            "Confirm Deletion",
            f"Delete {len(self.selected_items)} selected image(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            for image_path in self.selected_items.copy():  # Copy to avoid modification during iteration
                try:
                    # Ensure image_path is a Path object
                    if isinstance(image_path, str):
                        image_path = Path(image_path)
                    
                    if image_path.exists():
                        image_path.unlink()
                        deleted_count += 1
                        logger.info(f"Deleted {image_path}")
                    else:
                        logger.warning(f"File not found: {image_path}")
                        
                except Exception as e:
                    logger.error(f"Failed to delete {image_path}: {e}")
                    QMessageBox.warning(self, "Delete Error", f"Failed to delete {image_path.name}: {str(e)}")
            
            # Clear selection
            self.selected_items.clear()
            self.update_selection_label()
            
            # Reload gallery
            if deleted_count > 0:
                self.load_photos()
                QMessageBox.information(self, "Delete Complete", f"Successfully deleted {deleted_count} image(s).")
            
    def email_selected(self):
        """Email selected images"""
        if not self.selected_items or not self.email_handler:
            return
            
        try:
            # Get email config
            email_config = self.config.get('email', {})
            recipient = email_config.get('recipient', email_config.get('sender', ''))
            
            if not recipient:
                QMessageBox.warning(self, "No Email", 
                                  "No email recipient configured")
                return
                
            # Send email with attachments
            subject = f"Bird Photos - {len(self.selected_items)} images"
            body = f"Attached are {len(self.selected_items)} bird photos from your collection."
            
            success = self.email_handler.send_email_with_attachments(
                recipient, 
                subject, 
                body,
                list(self.selected_items)
            )
            
            if success:
                QMessageBox.information(self, "Email Sent", 
                                      f"Successfully sent {len(self.selected_items)} images")
                
                # Clear selection after successful email
                self.clear_selection()
            else:
                QMessageBox.warning(self, "Email Failed", 
                                  "Failed to send email")
                
        except Exception as e:
            logger.error(f"Email error: {e}")
            QMessageBox.critical(self, "Error", f"Email error: {str(e)}")

class ServicesTab(QWidget):
    """Services monitoring and control tab"""
    
    def __init__(self, email_handler, uploader, config=None, bird_identifier=None):
        super().__init__()
        self.email_handler = email_handler
        self.uploader = uploader
        self.config = config or {}
        self.bird_identifier = bird_identifier
        
        # Initialize Drive stats monitor
        self.drive_stats_monitor = DriveStatsMonitor(uploader)
        self.drive_stats_monitor.drive_stats_updated.connect(self.update_drive_stats)
        
        self.setup_ui()
        
        # Start background monitoring
        self.drive_stats_monitor.start()
        
        # Update OpenAI count immediately and every 5 seconds
        self.update_openai_count()
        self.openai_timer = QTimer()
        self.openai_timer.timeout.connect(self.update_openai_count)
        self.openai_timer.start(5000)
        
        # Track app start time for uptime
        self.app_start_time = datetime.now()
        
        # Update uptime every second
        self.uptime_timer = QTimer()
        self.uptime_timer.timeout.connect(self.update_uptime)
        self.uptime_timer.start(5000)  # Update every 5 seconds to reduce CPU load
        self.update_uptime()
        
        # Update service statuses
        self.update_service_statuses()
        
    def set_config(self, config):
        """Update config reference and refresh statuses"""
        self.config = config
        self.update_service_statuses()
        
    
    def cleanup(self):
        """Clean up background threads"""
        if hasattr(self, 'drive_stats_monitor'):
            self.drive_stats_monitor.stop()
        if hasattr(self, 'openai_timer'):
            self.openai_timer.stop()
        if hasattr(self, 'uptime_timer'):
            self.uptime_timer.stop()
    
    def set_mobile_url(self, url):
        """Set the mobile web interface URL"""
        if url:
            self.mobile_url_label.setText(
                f'<p style="text-align: center;">Mobile interface available at:<br>'
                f'<a href="{url}" style="font-size: 16px; color: #4CAF50;">{url}</a><br>'
                f'<span style="font-size: 12px;">Access from your phone browser</span></p>'
            )
        else:
            self.mobile_url_label.setText(
                '<p style="text-align: center; color: #ff6b6b;">Mobile interface failed to start<br>'
                '<span style="font-size: 12px;">Check logs for details</span></p>'
            )
        
    def setup_ui(self):
        """Setup the services tab UI"""
        main_layout = QVBoxLayout()
        
        # Mobile Web Interface (at the top)
        mobile_group = QGroupBox("Mobile Web Interface")
        mobile_layout = QVBoxLayout()
        
        self.mobile_url_label = QLabel("Starting web server...")
        self.mobile_url_label.setOpenExternalLinks(True)
        self.mobile_url_label.setStyleSheet("font-size: 14px; padding: 10px;")
        mobile_layout.addWidget(self.mobile_url_label)
        
        mobile_group.setLayout(mobile_layout)
        main_layout.addWidget(mobile_group)
        
        # Create horizontal splitter for 50/50 layout
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side widget
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # Move Google Drive services to right side - placeholder for now
        pass
        
        # Email service status
        email_group = QGroupBox("Email Service")
        email_layout = QGridLayout()
        
        email_layout.addWidget(QLabel("Status:"), 0, 0)
        self.email_status = QLabel("Running")
        email_layout.addWidget(self.email_status, 0, 1)
        
        email_layout.addWidget(QLabel("Queue:"), 1, 0)
        self.email_queue = QLabel("0")
        email_layout.addWidget(self.email_queue, 1, 1)
        
        # Email test button
        self.test_email_btn = QPushButton("Send Test Email")
        self.test_email_btn.clicked.connect(self.on_test_email)
        email_layout.addWidget(self.test_email_btn, 2, 0, 1, 2)
        
        email_group.setLayout(email_layout)
        left_layout.addWidget(email_group)
        
        # Storage status
        storage_group = QGroupBox("Storage")
        storage_layout = QGridLayout()
        
        storage_layout.addWidget(QLabel("Save Directory:"), 0, 0)
        self.storage_path = QLabel(self.config.get('storage', {}).get('save_dir', str(Path.home() / 'BirdPhotos')))
        storage_layout.addWidget(self.storage_path, 0, 1)
        
        storage_layout.addWidget(QLabel("Used Space:"), 1, 0)
        self.storage_used = QLabel("0.0 GB")
        storage_layout.addWidget(self.storage_used, 1, 1)
        
        storage_layout.addWidget(QLabel("File Count:"), 2, 0)
        self.file_count = QLabel("0")
        storage_layout.addWidget(self.file_count, 2, 1)
        
        storage_group.setLayout(storage_layout)
        left_layout.addWidget(storage_group)
        
        # Application Status
        app_status_group = QGroupBox("Application Status")
        app_status_layout = QGridLayout()
        
        # App uptime
        app_status_layout.addWidget(QLabel("Uptime:"), 0, 0)
        self.uptime_label = QLabel("0h 0m 0s")
        self.uptime_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
        app_status_layout.addWidget(self.uptime_label, 0, 1)
        
        # Watchdog status
        app_status_layout.addWidget(QLabel("Watchdog Service:"), 1, 0)
        self.watchdog_status = QLabel("Unknown")
        app_status_layout.addWidget(self.watchdog_status, 1, 1)
        
        app_status_group.setLayout(app_status_layout)
        left_layout.addWidget(app_status_group)
        
        # Service Status Overview
        status_group = QGroupBox("Service Status")
        status_layout = QGridLayout()
        
        # Google Drive Upload status
        status_layout.addWidget(QLabel("Google Drive Upload:"), 0, 0)
        self.drive_service_status = QLabel("Disabled")
        self.drive_service_status.setStyleSheet("color: #666;")
        status_layout.addWidget(self.drive_service_status, 0, 1)
        
        # Email notifications status
        status_layout.addWidget(QLabel("Email Notifications:"), 1, 0)
        self.email_service_status = QLabel("Disabled")
        self.email_service_status.setStyleSheet("color: #666;")
        status_layout.addWidget(self.email_service_status, 1, 1)
        
        # Hourly reports status
        status_layout.addWidget(QLabel("Hourly Reports:"), 2, 0)
        self.hourly_service_status = QLabel("Disabled")
        self.hourly_service_status.setStyleSheet("color: #666;")
        status_layout.addWidget(self.hourly_service_status, 2, 1)
        
        # Storage cleanup status
        status_layout.addWidget(QLabel("Storage Cleanup:"), 3, 0)
        self.cleanup_service_status = QLabel("Disabled")
        self.cleanup_service_status.setStyleSheet("color: #666;")
        status_layout.addWidget(self.cleanup_service_status, 3, 1)
        
        status_group.setLayout(status_layout)
        left_layout.addWidget(status_group)
        
        left_layout.addStretch()
        
        # Right side widget - Google Drive and OpenAI Statistics
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Google Drive Upload Services (moved to right for more space)
        drive_group = QGroupBox("Google Drive Upload Services")
        drive_layout = QGridLayout()
        
        # Folder name
        drive_layout.addWidget(QLabel("Folder:"), 0, 0)
        folder_name = self.uploader.config.get('services', {}).get('drive_upload', {}).get('folder_name', 'Unknown')
        self.drive_folder_name = QLabel(folder_name)
        self.drive_folder_name.setStyleSheet("font-weight: bold; color: #2E7D32;")  # Dark green for readability
        drive_layout.addWidget(self.drive_folder_name, 0, 1)
        
        # Drive upload status
        drive_layout.addWidget(QLabel("Status:"), 1, 0)
        self.drive_status = QLabel("Checking...")
        self.drive_status.setStyleSheet("color: #FF6F00; font-weight: bold;")  # Dark orange for better readability
        drive_layout.addWidget(self.drive_status, 1, 1)
        
        # Upload queue
        drive_layout.addWidget(QLabel("Queue:"), 2, 0)
        self.drive_queue = QLabel("N/A")
        self.drive_queue.setStyleSheet("color: #424242; font-weight: bold;")  # Dark gray for readability
        drive_layout.addWidget(self.drive_queue, 2, 1)
        
        # File count
        drive_layout.addWidget(QLabel("Files in Drive:"), 3, 0)
        self.drive_file_count = QLabel("0")
        drive_layout.addWidget(self.drive_file_count, 3, 1)
        
        # Total size
        drive_layout.addWidget(QLabel("Total Size:"), 4, 0)
        self.drive_total_size = QLabel("0.0 MB")
        drive_layout.addWidget(self.drive_total_size, 4, 1)
        
        # Latest file
        drive_layout.addWidget(QLabel("Latest Upload:"), 5, 0)
        self.drive_latest_file = QLabel("None")
        drive_layout.addWidget(self.drive_latest_file, 5, 1)
        
        # Drive folder link
        drive_layout.addWidget(QLabel("View Folder:"), 6, 0)
        self.drive_folder_link = QLabel("Open Drive Folder")
        self.drive_folder_link.setStyleSheet("color: #1976D2; text-decoration: underline; font-weight: bold;")  # Darker blue for better contrast
        self.drive_folder_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.drive_folder_link.mousePressEvent = self.on_drive_folder_link_clicked
        drive_layout.addWidget(self.drive_folder_link, 6, 1)
        
        drive_group.setLayout(drive_layout)
        right_layout.addWidget(drive_group)
        
        # OpenAI API Statistics
        openai_group = QGroupBox("OpenAI Bird Identification")
        openai_layout = QGridLayout()
        
        # Title with larger font
        title_label = QLabel("AI Bird Analysis")
        title_font = title_label.font()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        openai_layout.addWidget(title_label, 0, 0, 1, 2)
        
        # Daily stats
        openai_layout.addWidget(QLabel("Images Analyzed Today:"), 1, 0)
        self.openai_daily_count = QLabel("0")
        self.openai_daily_count.setStyleSheet("font-size: 24px; font-weight: bold; color: #4CAF50;")
        openai_layout.addWidget(self.openai_daily_count, 1, 1)
        
        # Reset time info
        reset_label = QLabel("Resets at midnight")
        reset_label.setStyleSheet("font-size: 11px; color: #424242;")  # Darker gray for better readability
        openai_layout.addWidget(reset_label, 2, 0, 1, 2)
        
        openai_group.setLayout(openai_layout)
        right_layout.addWidget(openai_group)
        
        right_layout.addStretch()
        
        # Add widgets to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 400])  # Equal 50/50 split
        
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)
    
    def update_service_status(self, status):
        """Update service status - no longer using services table"""
        # Method kept for compatibility but functionality removed
        # since System Services section was removed from UI
        pass
    
    def update_upload_status(self):
        """Update upload service status"""
        if self.uploader:
            status = self.uploader.get_status()
            
            # Drive status
            drive_enabled = status['drive']['enabled']
            drive_queue = status['drive']['queue_size']
            
            # Debug logging
            logger.debug(f"Drive upload status: enabled={drive_enabled}, queue={drive_queue}")
            
            if drive_enabled:
                self.drive_status.setText("Running")
                self.drive_status.setStyleSheet("color: #00ff64;")  # Green for dark theme
            else:
                self.drive_status.setText("Disabled") 
                self.drive_status.setStyleSheet("color: #ff6464;")  # Red for dark theme
                
            self.drive_queue.setText(f"{drive_queue}")
            self.drive_queue.setStyleSheet("color: #ffffff;")
            
            # Drive folder statistics are now updated by background thread
            # No blocking calls here
    
    def update_drive_stats(self, stats):
        """Update Drive statistics from background thread"""
        logger.debug(f"Updating Drive stats in GUI: {stats}")
        if stats and stats.get('file_count', 0) > 0:
            self.drive_file_count.setText(str(stats['file_count']))
            
            # Convert size to readable format
            size_mb = stats['total_size'] / (1024 * 1024)
            if size_mb >= 1000:
                size_str = f"{size_mb/1024:.1f} GB"
            else:
                size_str = f"{size_mb:.1f} MB"
            self.drive_total_size.setText(size_str)
            
            # Latest file
            if stats['latest_file']:
                self.drive_latest_file.setText(stats['latest_file'])
            else:
                self.drive_latest_file.setText("None")
        else:
            # Keep showing 0 instead of Error if no stats yet
            logger.debug("No stats or zero file count")
            self.drive_file_count.setText("0")
            self.drive_total_size.setText("0.0 MB")
            self.drive_latest_file.setText("None")
            
    
    def update_email_status(self):
        """Update email service status"""
        if self.email_handler:
            queue_size = self.email_handler.get_queue_size()
            self.email_queue.setText(str(queue_size))
    
    def update_storage_status(self):
        """Update storage information with caching to reduce CPU usage"""
        try:
            # Add caching to reduce expensive file system operations
            if not hasattr(self, '_storage_stats_cache'):
                self._storage_stats_cache = {'count': 0, 'size': 0, 'last_update': 0}
            
            # Only recalculate every 30 seconds to reduce CPU load
            current_time = time.time()
            if current_time - self._storage_stats_cache['last_update'] > 30:
                storage_dir = self.config.get('storage', {}).get('save_dir', str(Path.home() / 'BirdPhotos'))
                if os.path.exists(storage_dir):
                    # Calculate total size and file count
                    total_size = 0
                    file_count = 0
                    
                    for root, dirs, files in os.walk(storage_dir):
                        for file in files:
                            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                                file_path = os.path.join(root, file)
                                try:
                                    total_size += os.path.getsize(file_path)
                                    file_count += 1
                                except OSError:
                                    pass
                    
                    self._storage_stats_cache = {
                        'count': file_count,
                        'size': total_size,
                        'last_update': current_time
                    }
                else:
                    self._storage_stats_cache = {'count': 0, 'size': 0, 'last_update': current_time}
            
            # Use cached values
            total_size = self._storage_stats_cache['size']
            file_count = self._storage_stats_cache['count']
            
            # Convert to GB
            size_gb = total_size / (1024**3)
            
            # Update labels
            if self._storage_stats_cache['count'] > 0 or self._storage_stats_cache['size'] > 0:
                self.storage_used.setText(f"{size_gb:.2f} GB")
                self.file_count.setText(str(file_count))
            else:
                self.storage_used.setText("Directory not found")
                self.file_count.setText("0")
        except Exception as e:
            logger.error(f"Error updating storage status: {e}")
            self.storage_used.setText("Error")
            self.file_count.setText("0")
    
    def update_watchdog_status(self):
        """Update watchdog service status"""
        try:
            import subprocess
            result = subprocess.run(
                ['systemctl', 'is-active', 'bird-detection-watchdog.service'],
                capture_output=True, text=True, timeout=5
            )
            status = result.stdout.strip()
            
            if status == 'active':
                self.watchdog_status.setText("Running")
                self.watchdog_status.setStyleSheet("color: #00ff64;")  # Green
            elif status == 'inactive':
                self.watchdog_status.setText("Stopped")
                self.watchdog_status.setStyleSheet("color: #ff6464;")  # Red
            else:
                self.watchdog_status.setText(f"Unknown ({status})")
                self.watchdog_status.setStyleSheet("color: #ffaa00;")  # Orange
                
        except Exception as e:
            self.watchdog_status.setText("Error")
            self.watchdog_status.setStyleSheet("color: #ff6464;")
            logger.error(f"Error checking watchdog status: {e}")
    
    def on_drive_folder_link_clicked(self, event):
        """Handle clicking on the Drive folder link"""
        try:
            if hasattr(self.uploader, 'drive_uploader') and self.uploader.drive_uploader:
                folder_url = self.uploader.drive_uploader.get_drive_folder_url()
                if folder_url:
                    QDesktopServices.openUrl(QUrl(folder_url))
                    logger.info(f"Opened Drive folder: {folder_url}")
                else:
                    logger.warning("Drive folder URL not available")
            else:
                logger.error("Drive uploader not available")
        except Exception as e:
            logger.error(f"Error opening Drive folder: {e}")
    
    def on_test_email(self):
        """Send test email using current configuration"""
        try:
            # Get current email config from the main config
            email_config = self.config.get('email', {})

            # Validate email settings
            if not email_config.get('sender'):
                QMessageBox.warning(self, "Email Not Configured",
                                  "Please configure email settings in the Configuration tab first.")
                return
            if not email_config.get('password'):
                QMessageBox.warning(self, "Email Not Configured",
                                  "Please configure email password in the Configuration tab first.")
                return

            # Create temporary email handler with current config
            temp_handler = EmailHandler(self.config)

            # Send test email
            test_info = {
                'hostname': 'test-system',
                'ip_address': '127.0.0.1',
                'uptime': '5 minutes'
            }
            result = temp_handler.send_reboot_notification(test_info)
            if result:
                QMessageBox.information(self, "Test Email", "Test email sent successfully!")
            else:
                QMessageBox.warning(self, "Test Email",
                                  "Failed to send test email. Check logs for details.\n\n"
                                  "Common issues:\n"
                                  "- Incorrect app password\n"
                                  "- 2-factor authentication not enabled\n"
                                  "- Configure email in Configuration tab")
            logger.info("Test email sent from Services tab")
        except Exception as e:
            logger.error(f"Error sending test email: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to send test email:\n\n{str(e)}")
    
    def update_service_statuses(self):
        """Update all service status displays"""
        if not self.config:
            return
            
        # Google Drive Upload status
        drive_enabled = self.config.get('services', {}).get('drive_upload', {}).get('enabled', False)
        self.drive_service_status.setText("Enabled" if drive_enabled else "Disabled")
        self.drive_service_status.setStyleSheet("color: #4CAF50; font-weight: bold;" if drive_enabled else "color: #666;")
        
        # Email notifications status
        email_enabled = self.config.get('email', {}).get('enabled', False)
        self.email_service_status.setText("Enabled" if email_enabled else "Disabled")
        self.email_service_status.setStyleSheet("color: #4CAF50; font-weight: bold;" if email_enabled else "color: #666;")
        
        # Hourly reports status
        hourly_enabled = self.config.get('email', {}).get('hourly_reports', False)
        self.hourly_service_status.setText("Enabled" if hourly_enabled else "Disabled")
        self.hourly_service_status.setStyleSheet("color: #4CAF50; font-weight: bold;" if hourly_enabled else "color: #666;")
        
        # Storage cleanup status
        cleanup_enabled = self.config.get('storage', {}).get('cleanup_enabled', False)
        self.cleanup_service_status.setText("Enabled" if cleanup_enabled else "Disabled")
        self.cleanup_service_status.setStyleSheet("color: #4CAF50; font-weight: bold;" if cleanup_enabled else "color: #666;")
    
    def update_openai_count(self):
        """Update OpenAI daily count display"""
        if self.bird_identifier:
            count = self.bird_identifier.get_daily_count()
            self.openai_daily_count.setText(str(count))
    
    def update_uptime(self):
        """Update app uptime display"""
        if hasattr(self, 'app_start_time'):
            uptime = datetime.now() - self.app_start_time
            hours = int(uptime.total_seconds() // 3600)
            minutes = int((uptime.total_seconds() % 3600) // 60)
            seconds = int(uptime.total_seconds() % 60)
            
            self.uptime_label.setText(f"{hours}h {minutes}m {seconds}s")
    

class ConfigTab(QWidget):
    """Configuration tab for all system settings"""
    
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.config = config_manager.config
        self.setup_ui()
        self.load_current_settings()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Scroll area for long config
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Email Configuration
        self.create_email_section(scroll_layout)
        
        # Local Storage Configuration
        self.create_local_storage_section(scroll_layout)
        
        # Google Drive Configuration
        self.create_drive_section(scroll_layout)
        
        # OpenAI Configuration
        self.create_openai_section(scroll_layout)
        
        # Pre-filter Configuration
        
        # System Management
        self.create_system_section(scroll_layout)
        
        # Logging Configuration
        self.create_logging_section(scroll_layout)
        
        # Save/Apply buttons
        self.create_buttons_section(scroll_layout)
        
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
    
    def create_email_section(self, layout):
        group = QGroupBox("Email Settings")
        group_layout = QGridLayout()
        
        # Email sender
        group_layout.addWidget(QLabel("Sender Email:"), 0, 0)
        self.email_sender = QLineEdit()
        group_layout.addWidget(self.email_sender, 0, 1, 1, 2)
        
        # App password
        group_layout.addWidget(QLabel("App Password:"), 1, 0)
        self.email_password = QLineEdit()
        self.email_password.setEchoMode(QLineEdit.EchoMode.Password)
        group_layout.addWidget(self.email_password, 1, 1)
        
        # App password help link
        app_password_link = QLabel('<a href="https://myaccount.google.com/apppasswords">Get App Password</a>')
        app_password_link.setOpenExternalLinks(True)
        group_layout.addWidget(app_password_link, 1, 2)
        
        # Email enabled checkbox
        self.email_notifications_enabled = QCheckBox("Enable Email Notifications")
        group_layout.addWidget(self.email_notifications_enabled, 2, 0, 1, 3)
        
        # Hourly reports checkbox
        self.hourly_reports_enabled = QCheckBox("Enable Hourly Reports")
        group_layout.addWidget(self.hourly_reports_enabled, 3, 0, 1, 3)
        
        # Test email button
        self.test_email_btn = QPushButton("Send Test Email")
        self.test_email_btn.clicked.connect(self.on_test_email)
        group_layout.addWidget(self.test_email_btn, 4, 0, 1, 3)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
    
    def create_local_storage_section(self, layout):
        group = QGroupBox("Local Storage")
        group_layout = QGridLayout()
        
        # Home folder
        group_layout.addWidget(QLabel("Save Directory:"), 0, 0)
        self.storage_dir = QLineEdit()
        group_layout.addWidget(self.storage_dir, 0, 1)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_storage_dir)
        group_layout.addWidget(browse_btn, 0, 2)
        
        # Storage limit
        group_layout.addWidget(QLabel("Max Storage (GB):"), 1, 0)
        self.storage_limit = QSpinBox()
        self.storage_limit.setRange(1, 1000)
        self.storage_limit.setValue(2)
        group_layout.addWidget(self.storage_limit, 1, 1)
        
        # Cleanup time
        group_layout.addWidget(QLabel("Cleanup Time:"), 2, 0)
        self.cleanup_time = QTimeEdit()
        self.cleanup_time.setDisplayFormat("HH:mm")
        group_layout.addWidget(self.cleanup_time, 2, 1)
        
        # Storage cleanup checkbox
        self.cleanup_enabled = QCheckBox("Enable Storage Cleanup")
        group_layout.addWidget(self.cleanup_enabled, 3, 0, 1, 2)
        
        # Manual cleanup button
        cleanup_now_btn = QPushButton("Run Cleanup Now")
        cleanup_now_btn.clicked.connect(self.run_cleanup_now)
        group_layout.addWidget(cleanup_now_btn, 3, 2)
        
        # Clear button
        clear_local_btn = QPushButton("Clear All Local Images")
        clear_local_btn.clicked.connect(self.clear_local_images)
        group_layout.addWidget(clear_local_btn, 4, 0, 1, 3)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
    
    def create_drive_section(self, layout):
        group = QGroupBox("Google Drive")
        group_layout = QGridLayout()
        
        # Drive enabled
        self.drive_upload_enabled = QCheckBox("Enable Google Drive Upload")
        group_layout.addWidget(self.drive_upload_enabled, 0, 0, 1, 3)
        
        # Folder name
        group_layout.addWidget(QLabel("Folder Name:"), 1, 0)
        self.drive_folder = QLineEdit()
        group_layout.addWidget(self.drive_folder, 1, 1, 1, 2)
        
        # Storage limit
        group_layout.addWidget(QLabel("Max Storage (GB):"), 2, 0)
        self.drive_limit = QSpinBox()
        self.drive_limit.setRange(1, 100)
        self.drive_limit.setValue(2)
        group_layout.addWidget(self.drive_limit, 2, 1)
        
        # Cleanup time
        group_layout.addWidget(QLabel("Cleanup Time:"), 3, 0)
        self.drive_cleanup_time = QTimeEdit()
        self.drive_cleanup_time.setTime(QTime(23, 30))  # Default 11:30 PM
        self.drive_cleanup_time.setDisplayFormat("HH:mm")
        group_layout.addWidget(self.drive_cleanup_time, 3, 1)
        
        # OAuth setup button
        setup_drive_btn = QPushButton("Setup Google Drive OAuth")
        setup_drive_btn.clicked.connect(self.setup_google_drive)
        group_layout.addWidget(setup_drive_btn, 4, 0, 1, 2)
        
        # Clear button
        clear_drive_btn = QPushButton("Clear All Drive Images")
        clear_drive_btn.clicked.connect(self.clear_drive_images)
        group_layout.addWidget(clear_drive_btn, 4, 2)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
    
    def create_openai_section(self, layout):
        group = QGroupBox("AI Bird Identification")
        group_layout = QGridLayout()
        
        # OpenAI enabled
        self.openai_enabled = QCheckBox("Enable AI Species Identification")
        group_layout.addWidget(self.openai_enabled, 0, 0, 1, 3)
        
        # API key
        group_layout.addWidget(QLabel("OpenAI API Key:"), 1, 0)
        self.openai_key = QLineEdit()
        self.openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        group_layout.addWidget(self.openai_key, 1, 1)
        
        # API key link
        api_link_btn = QPushButton("Get API Key")
        api_link_btn.setMaximumWidth(100)
        api_link_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        api_link_btn.clicked.connect(self.open_openai_api_page)
        group_layout.addWidget(api_link_btn, 1, 2)
        
        # Rate limit
        group_layout.addWidget(QLabel("Max Images/Hour:"), 2, 0)
        self.openai_limit = QSpinBox()
        self.openai_limit.setRange(1, 20)
        self.openai_limit.setValue(10)
        group_layout.addWidget(self.openai_limit, 2, 1)
        
        # Test API button
        self.test_api_btn = QPushButton("Test API Connection")
        self.test_api_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        self.test_api_btn.clicked.connect(self.test_openai_api)
        group_layout.addWidget(self.test_api_btn, 3, 0, 1, 3)

        # Clear species button
        clear_species_btn = QPushButton("Clear Species Database")
        clear_species_btn.clicked.connect(self.clear_species_database)
        group_layout.addWidget(clear_species_btn, 4, 0, 1, 3)

        group.setLayout(group_layout)
        layout.addWidget(group)
    
    
    def create_system_section(self, layout):
        group = QGroupBox("System Management")
        group_layout = QGridLayout()
        
        # Watchdog status
        group_layout.addWidget(QLabel("Watchdog Service:"), 0, 0)
        self.watchdog_status = QLabel("Unknown")
        group_layout.addWidget(self.watchdog_status, 0, 1)
        
        # Install watchdog button
        install_watchdog_btn = QPushButton("Install Watchdog Service")
        install_watchdog_btn.clicked.connect(self.install_watchdog)
        group_layout.addWidget(install_watchdog_btn, 1, 0)
        
        # Start/Stop watchdog buttons
        start_watchdog_btn = QPushButton("Start Watchdog")
        start_watchdog_btn.clicked.connect(self.start_watchdog)
        group_layout.addWidget(start_watchdog_btn, 1, 1)
        
        stop_watchdog_btn = QPushButton("Stop Watchdog")
        stop_watchdog_btn.clicked.connect(self.stop_watchdog)
        group_layout.addWidget(stop_watchdog_btn, 1, 2)
        
        # Check status button
        check_status_btn = QPushButton("Check Status")
        check_status_btn.clicked.connect(self.check_watchdog_status)
        group_layout.addWidget(check_status_btn, 2, 0)
        
        # View logs button
        view_logs_btn = QPushButton("View Watchdog Logs")
        view_logs_btn.clicked.connect(self.view_watchdog_logs)
        group_layout.addWidget(view_logs_btn, 2, 1)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
        
        # Check status on startup
        QTimer.singleShot(1000, self.check_watchdog_status)
        QTimer.singleShot(1000, self.check_management_status)
    
    def create_logging_section(self, layout):
        """Create logging configuration section"""
        group = QGroupBox("Logging Settings")
        group_layout = QGridLayout()
        
        # Logging enabled checkbox
        group_layout.addWidget(QLabel("Enable Verbose Logging:"), 0, 0)
        self.logging_enabled = QCheckBox()
        self.logging_enabled.setToolTip(
            "When enabled: Full logging (INFO, DEBUG, WARNING, ERROR)\n"
            "When disabled: Only errors logged (better performance)"
        )
        self.logging_enabled.toggled.connect(self.on_logging_toggled)
        group_layout.addWidget(self.logging_enabled, 0, 1)
        
        # Status indicator
        self.logging_status = QLabel("Status: Enabled")
        self.logging_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
        group_layout.addWidget(self.logging_status, 1, 0, 1, 2)
        
        # Performance note
        note = QLabel("💡 Disable logging to improve performance during normal operation")
        note.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        group_layout.addWidget(note, 2, 0, 1, 2)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
    
    def create_buttons_section(self, layout):
        button_layout = QHBoxLayout()
        
        save_btn = QPushButton("Save Configuration")
        save_btn.clicked.connect(self.save_config)
        button_layout.addWidget(save_btn)
        
        apply_btn = QPushButton("Apply & Restart Services")
        apply_btn.clicked.connect(self.apply_config)
        button_layout.addWidget(apply_btn)
        
        layout.addLayout(button_layout)
    
    def load_current_settings(self):
        """Load current config values into UI"""
        # Email settings
        email_config = self.config.get('email', {})
        self.email_sender.setText(email_config.get('sender', ''))
        self.email_password.setText(email_config.get('password', ''))
        # Set email notification checkboxes
        email_notifications = email_config.get('enabled', False)
        self.email_notifications_enabled.setChecked(email_notifications)
        
        hourly_reports = email_config.get('hourly_reports', False)
        self.hourly_reports_enabled.setChecked(hourly_reports)
        
        # Storage settings
        storage_config = self.config.get('storage', {})
        self.storage_dir.setText(storage_config.get('save_dir', str(Path.home() / 'BirdPhotos')))
        self.storage_limit.setValue(storage_config.get('max_size_gb', 2))
        
        cleanup_time = storage_config.get('cleanup_time', '23:30')
        hour, minute = map(int, cleanup_time.split(':'))
        self.cleanup_time.setTime(QTime(hour, minute))
        self.cleanup_enabled.setChecked(storage_config.get('cleanup_enabled', False))
        
        # Drive settings
        drive_config = self.config.get('services', {}).get('drive_upload', {})
        self.drive_upload_enabled.setChecked(drive_config.get('enabled', False))
        self.drive_folder.setText(drive_config.get('folder_name', 'Bird Photos'))
        self.drive_limit.setValue(drive_config.get('max_size_gb', 2))
        cleanup_time_str = drive_config.get('cleanup_time', '23:30')
        cleanup_time = QTime.fromString(cleanup_time_str, 'HH:mm')
        self.drive_cleanup_time.setTime(cleanup_time)
        
        # OpenAI settings
        openai_config = self.config.get('openai', {})
        self.openai_enabled.setChecked(openai_config.get('enabled', False))
        self.openai_key.setText(openai_config.get('api_key', ''))
        self.openai_limit.setValue(openai_config.get('max_images_per_hour', 10))
        
        
        # Logging settings
        logging_config = self.config.get('logging', {})
        logging_enabled = logging_config.get('enabled', True)
        self.logging_enabled.setChecked(logging_enabled)
        self.update_logging_status(logging_enabled)
    
    def browse_storage_dir(self):
        """Browse for storage directory"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Storage Directory", self.storage_dir.text()
        )
        if dir_path:
            self.storage_dir.setText(dir_path)
    
    def open_openai_api_page(self):
        """Open OpenAI API key page in browser"""
        try:
            url = QUrl("https://platform.openai.com/api-keys")
            QDesktopServices.openUrl(url)
            logger.info("Opened OpenAI API keys page in browser")
        except Exception as e:
            logger.error(f"Failed to open OpenAI API page: {e}")
            QMessageBox.information(
                self,
                "OpenAI API Keys",
                "Please visit: https://platform.openai.com/api-keys\n\n"
                "Create an account and generate an API key to enable bird identification."
            )

    def _update_api_button_status(self, status, duration=2000):
        """Update API test button with status (GOOD/BAD) for a short time"""
        original_text = "Test API Connection"
        if status == "GOOD":
            self.test_api_btn.setText(f"Test API Connection - ✓ GOOD")
            self.test_api_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    padding: 5px;
                    border-radius: 3px;
                    font-weight: bold;
                }
            """)
        elif status == "BAD":
            self.test_api_btn.setText(f"Test API Connection - ✗ BAD")
            self.test_api_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    border: none;
                    padding: 5px;
                    border-radius: 3px;
                    font-weight: bold;
                }
            """)

        # Reset after duration
        QTimer.singleShot(duration, lambda: self._reset_api_button())

    def _reset_api_button(self):
        """Reset API test button to original state"""
        self.test_api_btn.setText("Test API Connection")
        self.test_api_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)

    def test_openai_api(self):
        """Test OpenAI API connection with a simple request"""
        logger.info("=== TEST OPENAI API BUTTON CLICKED ===")
        import requests
        import base64
        from pathlib import Path

        api_key = self.openai_key.text().strip()
        logger.info(f"API key field value: {'[present]' if api_key else '[empty]'}")

        if not api_key:
            self._update_api_button_status("BAD")
            QMessageBox.warning(
                self,
                "No API Key",
                "Please enter your OpenAI API key before testing."
            )
            return

        # Show progress dialog
        progress = QMessageBox(self)
        progress.setWindowTitle("Testing API")
        progress.setText("Testing OpenAI API connection...\n\nPlease wait...")
        progress.setStandardButtons(QMessageBox.StandardButton.NoButton)
        progress.show()
        QApplication.processEvents()

        try:
            # Create a simple test image (1x1 pixel PNG)
            test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

            logger.info("Testing OpenAI API with test request...")

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            payload = {
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "This is a test. Please respond with 'API connection successful'."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{test_image_b64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 50
            }

            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )

            progress.close()

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']

                self._update_api_button_status("GOOD")
                QMessageBox.information(
                    self,
                    "API Test Successful",
                    f"✅ OpenAI API connection successful!\n\n"
                    f"Response: {content[:100]}...\n\n"
                    f"Your API key is valid and working.\n"
                    f"Model: {result.get('model', 'gpt-4o')}"
                )
                logger.info("OpenAI API test successful")

            elif response.status_code == 401:
                self._update_api_button_status("BAD")
                QMessageBox.critical(
                    self,
                    "Authentication Failed",
                    "❌ Invalid API key\n\n"
                    "The API key you entered is not valid.\n"
                    "Please check your API key and try again.\n\n"
                    "Get your API key at: https://platform.openai.com/api-keys"
                )
                logger.error("OpenAI API test failed: Invalid API key")

            elif response.status_code == 429:
                self._update_api_button_status("BAD")
                QMessageBox.warning(
                    self,
                    "Rate Limit Exceeded",
                    "⚠️ Rate limit exceeded\n\n"
                    "Your account has exceeded the rate limit.\n"
                    "Please wait a moment and try again.\n\n"
                    f"Error: {response.text[:200]}"
                )
                logger.error("OpenAI API test failed: Rate limit exceeded")

            elif response.status_code == 402:
                self._update_api_button_status("BAD")
                QMessageBox.critical(
                    self,
                    "Payment Required",
                    "❌ Payment required\n\n"
                    "Your OpenAI account requires payment setup.\n"
                    "Please add a payment method to your account.\n\n"
                    "Visit: https://platform.openai.com/account/billing"
                )
                logger.error("OpenAI API test failed: Payment required")

            else:
                self._update_api_button_status("BAD")
                QMessageBox.critical(
                    self,
                    "API Test Failed",
                    f"❌ API test failed\n\n"
                    f"Status code: {response.status_code}\n"
                    f"Error: {response.text[:200]}"
                )
                logger.error(f"OpenAI API test failed: {response.status_code} - {response.text[:200]}")

        except requests.exceptions.Timeout:
            progress.close()
            self._update_api_button_status("BAD")
            QMessageBox.critical(
                self,
                "Connection Timeout",
                "❌ Connection timeout\n\n"
                "The request to OpenAI API timed out.\n"
                "Please check your internet connection and try again."
            )
            logger.error("OpenAI API test failed: Timeout")

        except requests.exceptions.ConnectionError:
            progress.close()
            self._update_api_button_status("BAD")
            QMessageBox.critical(
                self,
                "Connection Error",
                "❌ Connection error\n\n"
                "Could not connect to OpenAI API.\n"
                "Please check your internet connection and try again."
            )
            logger.error("OpenAI API test failed: Connection error")

        except Exception as e:
            progress.close()
            self._update_api_button_status("BAD")
            QMessageBox.critical(
                self,
                "Test Failed",
                f"❌ API test failed\n\n"
                f"Error: {str(e)}"
            )
            logger.error(f"OpenAI API test failed: {e}")

    def setup_google_drive(self):
        """Launch Google Drive OAuth setup"""
        msg = QMessageBox()
        msg.setWindowTitle("Google Drive Setup")
        msg.setText("To setup Google Drive:\n\n"
                   "1. Place client_secret.json in the project directory\n"
                   "2. Click OK to start OAuth flow\n"
                   "3. Complete authorization in your browser\n\n"
                   "Need client_secret.json? See OAUTH_SETUP.md")
        
        if msg.exec() == QMessageBox.StandardButton.Ok:
            # Check if client_secret.json exists first
            client_secret_path = Path(__file__).parent / "client_secret.json"
            if not client_secret_path.exists():
                QMessageBox.critical(self, "Error", 
                                   f"client_secret.json not found!\n\n"
                                   f"Please download OAuth2 credentials from Google Cloud Console\n"
                                   f"and save as: {client_secret_path}")
                return
            
            # Run the external setup script
            setup_script = Path(__file__).parent / "setup_google_drive.py"
            
            QMessageBox.information(self, "Google Drive Setup", 
                                  "A terminal window will open for the OAuth setup.\n\n"
                                  "Follow the instructions in the terminal to authorize Google Drive access.")
            
            try:
                import subprocess
                # Run in terminal so user can see output and interact
                if sys.platform == "linux" or sys.platform == "linux2":
                    # Try to use x-terminal-emulator first (works on most Linux distros)
                    subprocess.Popen(["x-terminal-emulator", "-e", sys.executable, str(setup_script)])
                elif sys.platform == "darwin":
                    # macOS
                    subprocess.Popen(["open", "-a", "Terminal", str(setup_script)])
                else:
                    # Windows
                    subprocess.Popen(["start", "cmd", "/k", sys.executable, str(setup_script)], shell=True)
                    
            except Exception as e:
                # Fallback: try to run directly
                try:
                    subprocess.Popen([sys.executable, str(setup_script)])
                except Exception as e2:
                    QMessageBox.critical(self, "Error", 
                                       f"Failed to run setup script:\n\n{str(e2)}\n\n"
                                       f"Please run manually:\n"
                                       f"python3 {setup_script}")
    
    def run_cleanup_now(self):
        """Run storage cleanup manually"""
        try:
            from src.cleanup_manager import CleanupManager
            logger.info("Running manual storage cleanup...")
            cleanup_manager = CleanupManager(self.config)
            result = cleanup_manager.cleanup_old_files()
            
            if result['cleaned']:
                msg = f"Cleanup completed!\n\nDeleted {result['files_deleted']} files\nFreed {result['space_freed']/(1024*1024):.1f}MB\nCurrent size: {result['current_size']:.2f}GB"
                QMessageBox.information(self, "Cleanup Complete", msg)
            else:
                msg = f"No cleanup needed.\n\nCurrent size: {result['current_size']:.2f}GB\nLimit: {self.config['storage']['max_size_gb']}GB"
                QMessageBox.information(self, "Storage OK", msg)
                
        except Exception as e:
            logger.error(f"Manual cleanup failed: {e}")
            QMessageBox.critical(self, "Cleanup Failed", f"Storage cleanup failed:\n{str(e)}")
    
    def clear_local_images(self):
        """Clear all local images and related tracking files"""
        reply = QMessageBox.question(
            self, "Clear Local Images", 
            "Are you sure you want to delete all local images?\n\n"
            "This will also clear the Google Drive upload tracking.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                storage_path = Path(self.storage_dir.text())
                files_deleted = 0
                
                if storage_path.exists():
                    # Delete image files
                    for img_file in storage_path.glob("*.jpeg"):
                        img_file.unlink()
                        files_deleted += 1
                    for img_file in storage_path.glob("*.jpg"):
                        img_file.unlink()
                        files_deleted += 1
                    
                    # Delete Google Drive upload tracking file
                    drive_uploads_file = storage_path / "drive_uploads.json"
                    if drive_uploads_file.exists():
                        drive_uploads_file.unlink()
                        logger.info("Deleted drive_uploads.json tracking file")
                
                QMessageBox.information(self, "Success", 
                    f"Local images cleared!\n\n"
                    f"Deleted {files_deleted} image files and upload tracking.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear images: {str(e)}")
    
    def clear_drive_images(self):
        """Clear all Google Drive images and reset upload tracking"""
        reply = QMessageBox.question(
            self, "Clear Drive Images", 
            "Are you sure you want to delete all Google Drive images?\n\n"
            "This will also reset the upload tracking so files can be re-uploaded.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Reset the drive uploads tracking file
                storage_path = Path(self.storage_dir.text())
                drive_uploads_file = storage_path / "drive_uploads.json"
                
                # Create empty tracking file
                empty_tracking = {
                    "uploaded_files": [],
                    "last_updated": datetime.now().isoformat()
                }
                
                if drive_uploads_file.exists() or storage_path.exists():
                    storage_path.mkdir(exist_ok=True)
                    with open(drive_uploads_file, 'w') as f:
                        json.dump(empty_tracking, f, indent=2)
                    logger.info("Reset drive_uploads.json tracking file")
                
                # Note: Actual Google Drive deletion would require Drive API implementation
                QMessageBox.information(self, "Upload Tracking Reset", 
                    "Google Drive upload tracking has been reset.\n\n"
                    "Note: To delete files from Google Drive, please use the Google Drive web interface.\n"
                    "Local files will now be re-uploaded on next sync.")
                    
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to reset tracking: {str(e)}")
    
    def clear_species_database(self):
        """Clear all identified bird species"""
        reply = QMessageBox.question(
            self, "Clear Species Database", 
            "Are you sure you want to delete all identified bird species?\n\nThis will remove all AI identification history and IdentifiedSpecies photos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Clear the species database
                species_db_path = Path(__file__).parent / "species_database.json"
                if species_db_path.exists():
                    # Reset to empty database
                    empty_db = {"species": {}, "sightings": [], "daily_stats": {}}
                    with open(species_db_path, 'w') as f:
                        json.dump(empty_db, f, indent=2)
                
                # Clear IdentifiedSpecies folder
                import shutil
                identified_species_path = Path.home() / "BirdPhotos" / "IdentifiedSpecies"
                if identified_species_path.exists():
                    shutil.rmtree(identified_species_path)
                    identified_species_path.mkdir(parents=True, exist_ok=True)  # Recreate empty folder
                
                # Refresh species tab if it exists
                if hasattr(self, 'species_tab'):
                    self.species_tab.load_species()
                    # Force heatmap to clear by updating with empty bird identifier
                    if hasattr(self.species_tab, 'heatmap_widget'):
                        self.species_tab.heatmap_widget.update_data(None)
                
                QMessageBox.information(self, "Success", "Species database and IdentifiedSpecies folder cleared!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear species database: {str(e)}")
    
    def check_watchdog_status(self):
        """Check watchdog service status"""
        try:
            result = subprocess.run(['systemctl', 'is-active', 'bird-detection-watchdog.service'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                status = result.stdout.strip()
                if status == 'active':
                    self.watchdog_status.setText("🟢 Running")
                    self.watchdog_status.setStyleSheet("color: green")
                else:
                    self.watchdog_status.setText(f"🟡 {status}")
                    self.watchdog_status.setStyleSheet("color: orange")
            else:
                self.watchdog_status.setText("🔴 Not installed")
                self.watchdog_status.setStyleSheet("color: red")
        except Exception as e:
            self.watchdog_status.setText("🔴 Error")
            self.watchdog_status.setStyleSheet("color: red")
    
    def install_watchdog(self):
        """Install watchdog service"""
        msg = QMessageBox()
        msg.setWindowTitle("Install Watchdog Service")
        msg.setText("This will install the Bird Detection watchdog service.\n\n"
                   "The watchdog will:\n"
                   "• Automatically start the app on system boot\n"
                   "• Restart the app if it crashes\n"
                   "• Run in the background 24/7\n\n"
                   "This requires administrator privileges (sudo).")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        
        if msg.exec() == QMessageBox.StandardButton.Ok:
            try:
                install_script = Path(__file__).parent / "install_watchdog_dynamic.sh"
                if not install_script.exists():
                    QMessageBox.critical(self, "Error", f"Install script not found: {install_script}")
                    return
                
                # Run in terminal so user can see prompts and enter sudo password
                QMessageBox.information(self, "Running Installer", 
                                      "The installer will open in a terminal window.\n"
                                      "Follow the prompts to complete installation.")
                
                # Try different terminal emulators in order of preference
                terminals = [
                    ['gnome-terminal', '--', 'bash', str(install_script)],
                    ['x-terminal-emulator', '-e', f'bash {install_script}'],
                    ['xterm', '-e', f'bash {install_script}'],
                    ['konsole', '-e', f'bash {install_script}']
                ]

                success = False
                for terminal_cmd in terminals:
                    try:
                        subprocess.Popen(terminal_cmd)
                        success = True
                        break
                    except FileNotFoundError:
                        continue

                if not success:
                    QMessageBox.critical(self, "Error", "No terminal emulator found.\n\n"
                                                       "Please run the following command manually:\n\n"
                                                       f"bash {install_script}")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to run installer: {str(e)}")
    
    def force_shutdown_for_watchdog(self):
        """Force shutdown of the application for watchdog restart"""
        try:
            logger.info("Force shutdown requested for watchdog restart")
            
            # Immediately stop all timers to prevent new operations
            if hasattr(self, 'status_timer'):
                self.status_timer.stop()
            if hasattr(self, 'slow_timer'):
                self.slow_timer.stop()
            
            # Force stop services quickly
            try:
                self.email_handler.stop()
            except:
                pass
            try:
                self.uploader.stop() 
            except:
                pass
            try:
                self.service_monitor.stop()
            except:
                pass
            try:
                self.camera_controller.disconnect()
            except:
                pass
            
            # Force close camera thread
            if self.camera_thread:
                try:
                    self.camera_thread.stop()
                    self.camera_thread.wait(1000)  # Wait max 1 second
                except:
                    pass
            
            # Close web server immediately
            if hasattr(self, 'web_server_process') and self.web_server_process:
                try:
                    self.web_server_process.terminate()
                    self.web_server_process.wait(timeout=1)
                except:
                    try:
                        self.web_server_process.kill()
                    except:
                        pass
            
            # Force quit the application
            from PyQt6.QtWidgets import QApplication
            QApplication.instance().quit()
            
            # If that doesn't work, use os._exit as last resort
            import os
            import threading
            def delayed_exit():
                import time
                time.sleep(2)
                os._exit(0)
            
            threading.Thread(target=delayed_exit, daemon=True).start()
            
        except Exception as e:
            logger.error(f"Error during force shutdown: {e}")
            # Last resort - immediate exit
            import os
            os._exit(0)
    
    def start_watchdog(self):
        """Start watchdog service and close app for automatic restart"""
        reply = QMessageBox.question(
            self, "Start Watchdog Service",
            "This will start the 24/7 monitoring service.\n\n"
            "The app will close and automatically reopen within 60 seconds.\n\n"
            "You will be prompted for administrator password.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Use pkexec for graphical authentication
                result = subprocess.run(['pkexec', 'systemctl', 'start', 'bird-detection-watchdog.service'],
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    # Show brief notification
                    msg = QMessageBox(self)
                    msg.setIcon(QMessageBox.Icon.Information)
                    msg.setWindowTitle("Watchdog Started")
                    msg.setText("Watchdog service started successfully!\n\nThis app will now close and reopen automatically.")
                    msg.show()

                    # Use QTimer to delay shutdown so message shows briefly
                    QTimer.singleShot(2000, self.force_shutdown_for_watchdog)
                elif "dismissed" in result.stderr.lower() or result.returncode == 126:
                    # User cancelled authentication
                    logger.info("User cancelled watchdog start authentication")
                else:
                    QMessageBox.critical(self, "Error", f"Failed to start service:\n{result.stderr}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to start watchdog: {str(e)}")
    
    def stop_watchdog(self):
        """Stop watchdog service"""
        reply = QMessageBox.question(
            self, "Stop Watchdog Service", 
            "This will stop the 24/7 monitoring service.\n\n"
            "⚠️ If this app is managed by the watchdog, it will also close.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Try to stop the service using pkexec for graphical authentication
                result = subprocess.run(['pkexec', 'systemctl', 'stop', 'bird-detection-watchdog.service'],
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    # Check if we're running under watchdog
                    if self.is_managed_by_watchdog():
                        QMessageBox.information(self, "Stopping...",
                                              "Watchdog service stopped!\n\n"
                                              "This application will now close as it was managed by the watchdog.")
                        # Close application since watchdog will kill it anyway
                        QApplication.quit()
                    else:
                        QMessageBox.information(self, "Success", "Watchdog service stopped!")
                elif "dismissed" in result.stderr.lower() or result.returncode == 126:
                    # User cancelled authentication
                    logger.info("User cancelled watchdog stop authentication")
                else:
                    QMessageBox.critical(self, "Error", f"Failed to stop service:\n{result.stderr}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to stop watchdog: {str(e)}")
    
    def is_managed_by_watchdog(self):
        """Check if this process is managed by the watchdog"""
        try:
            # Check if our parent process is the watchdog
            parent_pid = os.getppid()
            with open(f'/proc/{parent_pid}/cmdline', 'r') as f:
                parent_cmd = f.read()
                return 'bird_watchdog.py' in parent_cmd
        except:
            return False
    
    def check_management_status(self):
        """Check and display if app is managed by watchdog"""
        if self.is_managed_by_watchdog():
            self.watchdog_status.setText("🟢 Running (Managing this app)")
            self.watchdog_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            # Keep existing status
            pass
    
    def view_watchdog_logs(self):
        """View watchdog logs"""
        try:
            subprocess.Popen(['x-terminal-emulator', '-e', 
                            'sudo journalctl -u bird-detection-watchdog.service -f'])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open logs: {str(e)}")
    
    def on_logging_toggled(self, enabled):
        """Handle logging toggle"""
        try:
            from src.logger import set_logging_enabled
            
            # Update configuration and re-setup logging
            config_path = self.config_manager.config_path
            set_logging_enabled(enabled, config_path)
            
            # Update UI
            self.update_logging_status(enabled)
            
            # Reload config
            self.config_manager.load_config()
            self.config = self.config_manager.config

            # Reload OpenAI settings in UI to reflect config file values
            self._reload_openai_settings()

            # Update status silently without popup
            status = "enabled" if enabled else "disabled"
            logger.info(f"Logging has been {status}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update logging: {str(e)}")
    
    def _reload_openai_settings(self):
        """Reload OpenAI settings from config into UI fields"""
        try:
            openai_config = self.config.get('openai', {})
            self.openai_enabled.setChecked(openai_config.get('enabled', False))
            self.openai_key.setText(openai_config.get('api_key', ''))
            self.openai_limit.setValue(openai_config.get('max_images_per_hour', 10))
            logger.debug("Reloaded OpenAI settings from config")
        except Exception as e:
            logger.error(f"Error reloading OpenAI settings: {e}")

    def update_logging_status(self, enabled):
        """Update the logging status display"""
        if enabled:
            self.logging_status.setText("Status: Enabled (Full Logging)")
            self.logging_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self.logging_status.setText("Status: Disabled (Errors Only)")
            self.logging_status.setStyleSheet("color: #FF9800; font-weight: bold;")
    
    
    def save_config(self):
        """Save configuration to file"""
        try:
            # Create local storage directory if it doesn't exist
            storage_path = Path(self.storage_dir.text())
            if not storage_path.exists():
                try:
                    storage_path.mkdir(parents=True, exist_ok=True)
                    QMessageBox.information(self, "Directory Created", f"Created storage directory: {storage_path}")
                except Exception as e:
                    QMessageBox.warning(self, "Warning", f"Could not create directory {storage_path}: {str(e)}")
            
            # Update config with UI values
            self.config['email'] = {
                'sender': self.email_sender.text().strip(),
                'password': self.email_password.text().strip(),
                'receivers': {'primary': self.email_sender.text().strip()},
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 465,
                'enabled': self.email_notifications_enabled.isChecked(),
                'hourly_reports': self.hourly_reports_enabled.isChecked(),
                'daily_email_time': '16:30',
                'quiet_hours': {'start': 23, 'end': 5}
            }
            
            self.config['storage'] = {
                'save_dir': self.storage_dir.text(),
                'max_size_gb': self.storage_limit.value(),
                'cleanup_time': self.cleanup_time.time().toString('HH:mm'),
                'cleanup_enabled': self.cleanup_enabled.isChecked()
            }
            
            if 'services' not in self.config:
                self.config['services'] = {}
            
            self.config['services']['drive_upload'] = {
                'enabled': self.drive_upload_enabled.isChecked(),
                'folder_name': self.drive_folder.text(),
                'upload_delay': 3,
                'max_size_gb': self.drive_limit.value(),
                'cleanup_time': self.drive_cleanup_time.time().toString('HH:mm'),
                'note': 'OAuth2 only - personal Google Drive folder'
            }
            
            self.config['openai'] = {
                'api_key': self.openai_key.text().strip(),
                'enabled': self.openai_enabled.isChecked(),
                'max_images_per_hour': self.openai_limit.value()
            }
            
            
            # Update the config_manager's config first
            self.config_manager.config = self.config
            
            # Save to file
            self.config_manager.save_config()
            
            # Update the EmailHandler with new configuration immediately
            main_window = self.window()
            if hasattr(main_window, 'email_handler') and main_window.email_handler:
                try:
                    # Reinitialize EmailHandler with updated config
                    main_window.email_handler = EmailHandler(self.config)
                    logger.info("EmailHandler updated with new configuration")
                    
                    # Update gallery tab's email handler reference
                    if hasattr(main_window, 'gallery_tab') and main_window.gallery_tab:
                        main_window.gallery_tab.email_handler = main_window.email_handler
                        
                except Exception as e:
                    logger.error(f"Failed to update EmailHandler: {e}")
                    
            QMessageBox.information(self, "Success", "Configuration saved and applied!")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config: {str(e)}")
    
    def apply_config(self):
        """Save and apply configuration changes"""
        self.save_config()
        
        reply = QMessageBox.question(
            self, "Restart Required", 
            "Configuration saved. Restart application to apply changes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            QApplication.quit()
    
    def on_test_email(self):
        """Send test email"""
        try:
            # First, update config with current UI values (but don't save to file yet)
            email_config = {
                'sender': self.email_sender.text().strip(),
                'password': self.email_password.text().strip(),
                'receivers': {'primary': self.email_sender.text().strip()},
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 465,
                'enabled': self.email_notifications_enabled.isChecked(),
                'hourly_reports': self.hourly_reports_enabled.isChecked(),
                'daily_email_time': '16:30',
                'quiet_hours': {'start': 23, 'end': 5}
            }

            # Validate email settings
            if not email_config['sender']:
                QMessageBox.warning(self, "Email Not Configured",
                                  "Please enter your sender email address.")
                return
            if not email_config['password']:
                QMessageBox.warning(self, "Email Not Configured",
                                  "Please enter your app password.")
                return

            # Create temporary email handler with current settings
            temp_config = self.config.copy()
            temp_config['email'] = email_config

            logger.info("Creating temporary EmailHandler for test email")
            test_handler = EmailHandler(temp_config)

            # Send test email
            test_info = {
                'hostname': 'test-system',
                'ip_address': '127.0.0.1',
                'uptime': '5 minutes'
            }
            result = test_handler.send_reboot_notification(test_info)
            if result:
                QMessageBox.information(self, "Test Email", "Test email sent successfully!")
            else:
                QMessageBox.warning(self, "Test Email",
                                  "Failed to send test email. Check logs for details.\n\n"
                                  "Common issues:\n"
                                  "- Incorrect app password\n"
                                  "- 2-factor authentication not enabled\n"
                                  "- App password needs to be generated at:\n"
                                  "  https://myaccount.google.com/apppasswords")
            logger.info("Test email sent")
        except Exception as e:
            logger.error(f"Error sending test email: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to send test email:\n\n{str(e)}")

class LogsTab(QWidget):
    """Real-time logs tab"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        
        # Timer for log updates
        self.log_timer = QTimer()
        self.log_timer.timeout.connect(self.update_logs)
        self.log_timer.start(5000)  # Update every 5 seconds to reduce CPU load
        
    def setup_ui(self):
        """Setup the logs tab UI"""
        layout = QVBoxLayout()
        
        # Log controls
        controls_layout = QHBoxLayout()
        
        self.clear_btn = QPushButton("Clear Display")
        self.clear_btn.clicked.connect(self.clear_logs)
        controls_layout.addWidget(self.clear_btn)
        
        self.refresh_btn = QPushButton("Refresh Logs")
        self.refresh_btn.clicked.connect(self.update_logs)
        controls_layout.addWidget(self.refresh_btn)
        
        self.journal_btn = QPushButton("View System Logs")
        self.journal_btn.clicked.connect(self.view_system_logs)
        controls_layout.addWidget(self.journal_btn)
        
        self.auto_scroll_cb = QCheckBox("Auto Scroll")
        self.auto_scroll_cb.setChecked(True)
        controls_layout.addWidget(self.auto_scroll_cb)
        
        controls_layout.addStretch()
        
        layout.addLayout(controls_layout)
        
        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Courier", 9))
        self.log_display.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")
        
        layout.addWidget(self.log_display)
        
        self.setLayout(layout)
    
    def update_logs(self):
        """Update log display"""
        try:
            # Get new log lines from buffer
            buffer_lines = log_buffer.get_lines()
            
            # Also try to read from log file for more comprehensive logs
            log_file_path = Path(__file__).parent / 'logs' / 'bird_detection.log'
            file_lines = []
            
            if log_file_path.exists():
                try:
                    with open(log_file_path, 'r') as f:
                        file_lines = f.readlines()[-200:]  # Last 200 lines
                        file_lines = [line.strip() for line in file_lines if line.strip()]
                except Exception as e:
                    logger.debug(f"Could not read log file: {e}")
            
            # Combine and deduplicate
            all_lines = file_lines if file_lines else buffer_lines
            
            # Update display
            if all_lines:
                self.log_display.clear()
                if isinstance(all_lines, list):
                    self.log_display.append('\n'.join(all_lines))
                else:
                    self.log_display.append(all_lines)
                
                # Auto scroll to bottom
                if self.auto_scroll_cb.isChecked():
                    cursor = self.log_display.textCursor()
                    cursor.movePosition(cursor.MoveOperation.End)
                    self.log_display.setTextCursor(cursor)
            elif not all_lines and not buffer_lines:
                # Show helpful message if no logs available
                self.log_display.setText("No logs available yet. Start capturing images to see activity logs.")
                    
        except Exception as e:
            logger.error(f"Error updating logs: {e}")
            self.log_display.setText(f"Error loading logs: {str(e)}")
    
    def clear_logs(self):
        """Clear log display"""
        self.log_display.clear()
        log_buffer.clear()
    
    def view_system_logs(self):
        """View system/journal logs in external terminal"""
        try:
            # Try to open system logs in a new terminal window
            import subprocess
            
            # Show a selection dialog
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setWindowTitle("System Logs")
            msg.setText("Choose which system logs to view:")
            
            app_logs_btn = msg.addButton("Application Logs", QMessageBox.ButtonRole.ActionRole)
            watchdog_logs_btn = msg.addButton("Watchdog Service Logs", QMessageBox.ButtonRole.ActionRole)
            all_logs_btn = msg.addButton("All Bird Detection Logs", QMessageBox.ButtonRole.ActionRole)
            cancel_btn = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            
            msg.exec()
            
            cmd = None
            if msg.clickedButton() == app_logs_btn:
                cmd = ['gnome-terminal', '--', 'journalctl', '-f', '--identifier=bird-detection']
            elif msg.clickedButton() == watchdog_logs_btn:
                cmd = ['gnome-terminal', '--', 'journalctl', '-f', '-u', 'bird-detection-watchdog.service']
            elif msg.clickedButton() == all_logs_btn:
                cmd = ['gnome-terminal', '--', 'journalctl', '-f', '--identifier=bird-detection', '-u', 'bird-detection-watchdog.service']
            
            if cmd:
                subprocess.Popen(cmd)
                logger.info("Opened system logs in terminal")
                
        except Exception as e:
            logger.error(f"Failed to open system logs: {e}")
            QMessageBox.information(
                self, 
                "System Logs", 
                f"Could not open system logs in terminal.\n\n"
                f"You can view them manually with:\n"
                f"journalctl -f --identifier=bird-detection\n"
                f"journalctl -f -u bird-detection-watchdog.service\n\n"
                f"Error: {str(e)}"
            )

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
        """Handle window resize events to scale camera preview"""
        super().resizeEvent(event)
        
        # Check if we have a camera preview and scale it based on window size
        if hasattr(self, 'camera_tab') and hasattr(self.camera_tab, 'preview_label'):
            # Consider the window "fullscreen-like" if it's significantly larger than default
            current_size = event.size()
            is_large = current_size.width() > 1200 or current_size.height() > 900
            
            self.camera_tab.preview_label.scale_for_fullscreen(is_large)
            logger.debug(f"Window resized to {current_size.width()}x{current_size.height()}, large: {is_large}")
    
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

def apply_dark_theme(app):
    """Apply dark theme to the application"""
    # Dark palette
    palette = QPalette()
    
    # Window colors
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    
    # Base colors (text input backgrounds)
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    
    # Text colors
    palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    
    # Button colors
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    
    # Highlight colors
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    
    # Link colors
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor(128, 0, 128))
    
    # Disabled colors
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(80, 80, 80))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor(127, 127, 127))
    
    app.setPalette(palette)
    
    # Additional dark theme styling
    app.setStyleSheet("""
        QMainWindow {
            background-color: #353535;
        }
        
        QTabWidget::pane {
            border: 1px solid #454545;
            background-color: #353535;
        }
        
        QTabBar::tab {
            background-color: #454545;
            color: #ffffff;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }
        
        QTabBar::tab:selected {
            background-color: #2a82da;
            color: #000000;
        }
        
        QTabBar::tab:hover {
            background-color: #555555;
        }
        
        QGroupBox {
            font-weight: bold;
            border: 2px solid #454545;
            border-radius: 8px;
            margin-top: 10px;
            padding-top: 10px;
            background-color: #404040;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
            color: #ffffff;
        }
        
        QPushButton {
            background-color: #454545;
            border: 2px solid #555555;
            border-radius: 6px;
            padding: 8px 16px;
            color: #ffffff;
            font-weight: bold;
        }
        
        QPushButton:hover {
            background-color: #555555;
            border: 2px solid #666666;
        }
        
        QPushButton:pressed {
            background-color: #2a82da;
            border: 2px solid #1a72da;
        }
        
        QSlider::groove:horizontal {
            border: 1px solid #454545;
            height: 8px;
            background: #252525;
            border-radius: 4px;
        }
        
        QSlider::handle:horizontal {
            background: #2a82da;
            border: 1px solid #1a72da;
            width: 18px;
            height: 18px;
            border-radius: 9px;
            margin: -5px 0;
        }
        
        QSlider::handle:horizontal:hover {
            background: #3a92ea;
        }
        
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 2px solid #555555;
            border-radius: 3px;
            background-color: #353535;
        }
        
        QCheckBox::indicator:checked {
            background-color: #2a82da;
            border: 2px solid #1a72da;
        }
        
        QCheckBox::indicator:checked:hover {
            background-color: #3a92ea;
        }
        
        QTableWidget {
            background-color: #353535;
            alternate-background-color: #404040;
            gridline-color: #454545;
            border: 1px solid #454545;
            border-radius: 4px;
        }
        
        QTableWidget::item {
            padding: 8px;
            border: none;
        }
        
        QTableWidget::item:selected {
            background-color: #2a82da;
            color: #000000;
        }
        
        QHeaderView::section {
            background-color: #454545;
            color: #ffffff;
            padding: 8px;
            border: 1px solid #555555;
            font-weight: bold;
        }
        
        QTextEdit {
            background-color: #252525;
            color: #ffffff;
            border: 1px solid #454545;
            border-radius: 4px;
            padding: 4px;
            font-family: 'Courier New', monospace;
        }
        
        QLabel {
            color: #ffffff;
        }
        
        QStatusBar {
            background-color: #454545;
            color: #ffffff;
            border-top: 1px solid #555555;
        }
        
        QScrollBar:vertical {
            background: #353535;
            width: 16px;
            border: 1px solid #454545;
        }
        
        QScrollBar::handle:vertical {
            background: #555555;
            border-radius: 8px;
            min-height: 20px;
        }
        
        QScrollBar::handle:vertical:hover {
            background: #666666;
        }
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            border: none;
            background: none;
        }
        
        QScrollBar:horizontal {
            background: #353535;
            height: 16px;
            border: 1px solid #454545;
        }
        
        QScrollBar::handle:horizontal {
            background: #555555;
            border-radius: 8px;
            min-width: 20px;
        }
        
        QScrollBar::handle:horizontal:hover {
            background: #666666;
        }
        
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            border: none;
            background: none;
        }
    """)

if __name__ == "__main__":
    main()
