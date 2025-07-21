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
from datetime import datetime
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
            # Try to load from config.example.json as fallback
            example_path = self.config_path.replace('config.json', 'config.example.json')
            try:
                with open(example_path, 'r') as f:
                    self.config = json.load(f)
                    # Clear sensitive fields
                    if 'email' in self.config:
                        self.config['email']['sender'] = ''
                        self.config['email']['password'] = ''
                    if 'openai' in self.config:
                        self.config['openai']['api_key'] = ''
            except FileNotFoundError:
                self.config = self._get_default_config()
                # Expand paths even for default config
                self._expand_paths()
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
                           QSplitter, QFrame, QLineEdit, QTimeEdit, QFileDialog, 
                           QMessageBox, QScrollArea)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QMutex, QPoint, QRect, QUrl, QTime
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

# Set up logging with configuration
config_path = os.path.join(os.path.dirname(__file__), 'config.json')
setup_logging(config_path)
setup_gui_logging()
logger = get_logger(__name__)

class InteractivePreviewLabel(QLabel):
    """Custom QLabel that handles mouse events for ROI selection"""
    roi_selected = pyqtSignal(QPoint, QPoint)
    
    def __init__(self):
        super().__init__()
        self.setMinimumSize(600, 400)
        self.setStyleSheet("border: 2px solid #555555; background-color: #252525;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("Camera Preview")
        
        # ROI selection state
        self.drawing = False
        self.roi_start = QPoint()
        self.roi_end = QPoint()
        self.roi_rect = QRect()
        self.current_pixmap = None
        
    def mousePressEvent(self, event):
        """Handle mouse press for ROI selection"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            self.roi_start = event.pos()
            self.roi_end = event.pos()
            self.update()
            
    def mouseMoveEvent(self, event):
        """Handle mouse move for ROI selection"""
        if self.drawing:
            self.roi_end = event.pos()
            self.update()
            
    def mouseReleaseEvent(self, event):
        """Handle mouse release for ROI selection"""
        if event.button() == Qt.MouseButton.LeftButton and self.drawing:
            self.drawing = False
            self.roi_end = event.pos()
            
            # Ensure we have a valid rectangle
            if abs(self.roi_end.x() - self.roi_start.x()) > 10 and abs(self.roi_end.y() - self.roi_start.y()) > 10:
                # Normalize coordinates
                x1 = min(self.roi_start.x(), self.roi_end.x())
                y1 = min(self.roi_start.y(), self.roi_end.y())
                x2 = max(self.roi_start.x(), self.roi_end.x())
                y2 = max(self.roi_start.y(), self.roi_end.y())
                
                self.roi_rect = QRect(x1, y1, x2 - x1, y2 - y1)
                self.roi_selected.emit(QPoint(x1, y1), QPoint(x2, y2))
                logger.info(f"ROI selected: ({x1}, {y1}) to ({x2}, {y2})")
            else:
                # Clear ROI if too small
                self.roi_rect = QRect()
                self.roi_selected.emit(QPoint(-1, -1), QPoint(-1, -1))
                
            self.update()
            
    def paintEvent(self, event):
        """Custom paint event to draw ROI rectangle"""
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
                
            painter.end()
    
    def setPixmap(self, pixmap):
        """Override setPixmap to store current pixmap"""
        self.current_pixmap = pixmap
        super().setPixmap(pixmap)
        
    def clear_roi(self):
        """Clear the ROI rectangle"""
        self.roi_rect = QRect()
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
    
    def __init__(self, camera_controller):
        super().__init__()
        self.camera_controller = camera_controller
        self.running = False
        self.mutex = QMutex()
        
    def run(self):
        """Main camera loop"""
        self.running = True
        
        while self.running:
            try:
                # Get frame
                frame = self.camera_controller.get_frame()
                if frame is not None:
                    self.frame_ready.emit(frame.copy())
                    
                    # Process motion detection
                    if self.camera_controller.process_motion(frame):
                        # Motion was detected and capture triggered
                        pass
                    
                    # Normal frame rate when frames are available
                    self.msleep(33)  # ~30 FPS
                else:
                    # Longer delay when no frames available (camera disconnected)
                    self.msleep(200)  # 5 FPS polling rate
                
                # Check for captured images
                captured_image = self.camera_controller.get_captured_image()
                if captured_image:
                    self.image_captured.emit(captured_image)
                
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
                        logger.info(f"DriveStatsMonitor: Got stats: {stats}")
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
                
                # Check every 10 seconds
                if self.running:
                    self.msleep(10000)
                    
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
        self.daily_motion_events = 0
        
        self.setup_ui()
        self.load_default_roi()
        self.load_camera_settings()
        
    def setup_ui(self):
        """Setup the camera tab UI"""
        layout = QHBoxLayout()
        
        # Left side - Camera preview
        preview_layout = QVBoxLayout()
        
        # Camera preview label
        self.preview_label = InteractivePreviewLabel()
        self.preview_label.roi_selected.connect(self.on_roi_selected)
        preview_layout.addWidget(self.preview_label)
        
        # Camera stats panel
        self.create_camera_stats_panel(preview_layout)
        
        # Right side - Controls
        controls_layout = QVBoxLayout()
        
        # Camera controls
        camera_group = QGroupBox("Camera Controls")
        camera_layout = QGridLayout()
        
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
        self.exposure_slider.setRange(1, 33)
        self.exposure_slider.setValue(20)
        self.exposure_slider.valueChanged.connect(self.on_exposure_changed)
        camera_layout.addWidget(self.exposure_slider, 1, 1)
        self.exposure_value = QLabel("20ms")
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
        
        # ISO sliders
        camera_layout.addWidget(QLabel("ISO Min:"), 4, 0)
        self.iso_min_slider = QSlider(Qt.Orientation.Horizontal)
        self.iso_min_slider.setRange(100, 3200)
        self.iso_min_slider.setValue(100)
        self.iso_min_slider.valueChanged.connect(self.on_iso_min_changed)
        camera_layout.addWidget(self.iso_min_slider, 4, 1)
        self.iso_min_value = QLabel("100")
        camera_layout.addWidget(self.iso_min_value, 4, 2)
        
        camera_layout.addWidget(QLabel("ISO Max:"), 5, 0)
        self.iso_max_slider = QSlider(Qt.Orientation.Horizontal)
        self.iso_max_slider.setRange(100, 3200)
        self.iso_max_slider.setValue(800)
        self.iso_max_slider.valueChanged.connect(self.on_iso_max_changed)
        camera_layout.addWidget(self.iso_max_slider, 5, 1)
        self.iso_max_value = QLabel("800")
        camera_layout.addWidget(self.iso_max_value, 5, 2)
        
        camera_group.setLayout(camera_layout)
        controls_layout.addWidget(camera_group)
        
        # Motion detection controls
        motion_group = QGroupBox("Motion Detection")
        motion_layout = QGridLayout()
        
        # Sensitivity slider
        motion_layout.addWidget(QLabel("Sensitivity:"), 0, 0)
        self.sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.sensitivity_slider.setRange(10, 100)
        self.sensitivity_slider.setValue(50)
        self.sensitivity_slider.valueChanged.connect(self.on_sensitivity_changed)
        motion_layout.addWidget(self.sensitivity_slider, 0, 1)
        self.sensitivity_value = QLabel("50")
        motion_layout.addWidget(self.sensitivity_value, 0, 2)
        
        # Min area slider
        motion_layout.addWidget(QLabel("Min Area:"), 1, 0)
        self.min_area_slider = QSlider(Qt.Orientation.Horizontal)
        self.min_area_slider.setRange(100, 2000)
        self.min_area_slider.setValue(500)
        self.min_area_slider.valueChanged.connect(self.on_min_area_changed)
        motion_layout.addWidget(self.min_area_slider, 1, 1)
        self.min_area_value = QLabel("500")
        motion_layout.addWidget(self.min_area_value, 1, 2)
        
        # ROI buttons
        roi_layout = QHBoxLayout()
        self.set_roi_btn = QPushButton("Drag on Preview")
        self.set_roi_btn.clicked.connect(self.on_set_roi)
        roi_layout.addWidget(self.set_roi_btn)
        
        self.clear_roi_btn = QPushButton("Clear ROI")
        self.clear_roi_btn.clicked.connect(self.on_clear_roi)
        roi_layout.addWidget(self.clear_roi_btn)
        
        motion_layout.addLayout(roi_layout, 2, 0, 1, 3)
        
        motion_group.setLayout(motion_layout)
        controls_layout.addWidget(motion_group)
        
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
        controls_layout.addWidget(motion_settings_group)
        
        # Action buttons
        action_group = QGroupBox("Actions")
        action_layout = QVBoxLayout()
        
        self.capture_btn = QPushButton("Manual Capture")
        self.capture_btn.clicked.connect(self.on_manual_capture)
        action_layout.addWidget(self.capture_btn)
        
        self.save_settings_btn = QPushButton("Save Settings")
        self.save_settings_btn.clicked.connect(self.on_save_settings)
        action_layout.addWidget(self.save_settings_btn)
        
        action_group.setLayout(action_layout)
        controls_layout.addWidget(action_group)
        
        controls_layout.addStretch()
        
        # Add to main layout
        layout.addLayout(preview_layout, 2)
        layout.addLayout(controls_layout, 1)
        
        self.setLayout(layout)
    
    def create_camera_stats_panel(self, layout):
        """Create camera statistics panel below preview"""
        stats_group = QGroupBox("Camera Statistics")
        stats_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                padding-top: 10px;
                margin-top: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        
        stats_layout = QGridLayout()
        stats_layout.setSpacing(3)  # Reduced spacing for more compact layout
        stats_layout.setVerticalSpacing(2)  # Tighter vertical spacing
        stats_layout.setHorizontalSpacing(8)  # Keep horizontal spacing readable
        
        # Camera Info Section
        row = 0
        
        # Camera Model
        stats_layout.addWidget(QLabel("Model:"), row, 0)
        self.camera_model_label = QLabel("Unknown")
        self.camera_model_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
        stats_layout.addWidget(self.camera_model_label, row, 1)
        
        # Connection Type
        stats_layout.addWidget(QLabel("Connection:"), row, 2)
        self.connection_type_label = QLabel("Disconnected")
        stats_layout.addWidget(self.connection_type_label, row, 3)
        
        row += 1
        
        # Sensor Resolution
        stats_layout.addWidget(QLabel("Sensor:"), row, 0)
        self.sensor_resolution_label = QLabel("Unknown")
        stats_layout.addWidget(self.sensor_resolution_label, row, 1)
        
        # Current FPS
        stats_layout.addWidget(QLabel("FPS:"), row, 2)
        self.fps_label = QLabel("0")
        self.fps_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        stats_layout.addWidget(self.fps_label, row, 3)
        
        row += 1
        
        # Separator line
        separator = QLabel()
        separator.setStyleSheet("border-bottom: 1px solid #555; margin: 5px 0;")
        separator.setFixedHeight(1)
        stats_layout.addWidget(separator, row, 0, 1, 4)
        
        row += 1
        
        # Capture Statistics
        stats_layout.addWidget(QLabel("Photos (session):"), row, 0)
        self.session_photos_label = QLabel("0")
        self.session_photos_label.setStyleSheet("font-weight: bold; color: #FF9800;")
        stats_layout.addWidget(self.session_photos_label, row, 1)
        
        # Last Capture
        stats_layout.addWidget(QLabel("Last Capture:"), row, 2)
        self.last_capture_label = QLabel("None")
        stats_layout.addWidget(self.last_capture_label, row, 3)
        
        row += 1
        
        # Motion Events Today
        stats_layout.addWidget(QLabel("Motion Events:"), row, 0)
        self.motion_events_label = QLabel("0")
        self.motion_events_label.setStyleSheet("font-weight: bold; color: #E91E63;")
        stats_layout.addWidget(self.motion_events_label, row, 1)
        
        # Current Resolution Mode
        stats_layout.addWidget(QLabel("Resolution:"), row, 2)
        self.resolution_mode_label = QLabel("4K")
        stats_layout.addWidget(self.resolution_mode_label, row, 3)
        
        # Instructions at bottom
        row += 1
        instructions = QLabel("💡 Click and drag on preview to set Motion ROI")
        instructions.setStyleSheet("color: #888; font-size: 11px; font-style: italic; padding-top: 5px;")
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stats_layout.addWidget(instructions, row, 0, 1, 4)
        
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
        self.current_frame = frame.copy()
        
        # Convert to Qt format
        height, width, channel = frame.shape
        bytes_per_line = 3 * width
        q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).rgbSwapped()
        
        # Scale to fit preview
        pixmap = QPixmap.fromImage(q_image)
        scaled_pixmap = pixmap.scaled(
            self.preview_label.size(), 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        
        self.preview_label.setPixmap(scaled_pixmap)
        
        # Update FPS in stats (approximate)
        if hasattr(self, 'fps_label'):
            self.fps_label.setText("~30")
    
    def update_camera_stats(self):
        """Update camera statistics display"""
        if not hasattr(self, 'camera_model_label'):
            return
            
        # Update camera info from camera controller
        if self.camera_controller:
            device_info = self.camera_controller.get_device_info()
            
            # Camera model
            model = device_info.get('name', 'OAK Camera')
            self.camera_model_label.setText(model)
            
            # Connection type
            usb_speed = device_info.get('usb_speed', 'Unknown')
            if device_info.get('connected'):
                self.connection_type_label.setText(f"USB {usb_speed}")
            else:
                self.connection_type_label.setText(usb_speed)
            
            # Sensor resolution
            sensor_res = device_info.get('sensor_resolution', '4056x3040')
            self.sensor_resolution_label.setText(sensor_res)
            
            # Connection status styling
            if device_info.get('connected'):
                self.connection_type_label.setStyleSheet("color: #4CAF50;")
            else:
                self.connection_type_label.setStyleSheet("color: #F44336;")
        else:
            self.camera_model_label.setText("Disconnected")
            self.connection_type_label.setText("Not Connected")
            self.connection_type_label.setStyleSheet("color: #F44336;")
            self.sensor_resolution_label.setText("Unknown")
            self.fps_label.setText("0")
        
        # Update session photos count
        self.session_photos_label.setText(str(self.session_capture_count))
        
        # Update last capture time
        if self.last_capture_time:
            time_str = self.last_capture_time.strftime("%H:%M:%S")
            self.last_capture_label.setText(time_str)
        else:
            self.last_capture_label.setText("None")
        
        # Update motion events (this would need to be connected to motion detection)
        self.motion_events_label.setText(str(self.daily_motion_events))
        
        # Update resolution mode
        self.resolution_mode_label.setText("4K")
    
    def on_motion_detected(self):
        """Called when motion is detected - updates stats"""
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
        self.exposure_value.setText(f"{value}ms")
        if not self.auto_exposure_cb.isChecked():
            self.camera_controller.update_camera_setting('exposure', value)
    
    def on_auto_exposure_changed(self, state):
        """Handle auto exposure checkbox change"""
        enabled = state == Qt.CheckState.Checked.value
        self.camera_controller.update_camera_setting('auto_exposure', enabled)
        self.exposure_slider.setEnabled(not enabled)
    
    def on_wb_changed(self, value):
        """Handle white balance slider change"""
        self.wb_value.setText(f"{value}K")
        self.camera_controller.update_camera_setting('white_balance', value)
    
    def on_iso_min_changed(self, value):
        """Handle ISO min slider change"""
        self.iso_min_value.setText(str(value))
        # Ensure max >= min
        if value > self.iso_max_slider.value():
            self.iso_max_slider.setValue(value)
    
    def on_iso_max_changed(self, value):
        """Handle ISO max slider change"""
        self.iso_max_value.setText(str(value))
        # Ensure max >= min
        if value < self.iso_min_slider.value():
            self.iso_min_slider.setValue(value)
    
    def on_sensitivity_changed(self, value):
        """Handle sensitivity slider change"""
        self.sensitivity_value.setText(str(value))
        self.camera_controller.motion_detector.update_settings(threshold=value)
    
    def on_min_area_changed(self, value):
        """Handle min area slider change"""
        self.min_area_value.setText(str(value))
        self.camera_controller.motion_detector.update_settings(min_area=value)
    
    def on_roi_selected(self, start_point, end_point):
        """Handle ROI selection from preview label"""
        if start_point.x() == -1:  # Clear ROI
            self.camera_controller.clear_roi()
            logger.info("ROI cleared")
        else:
            # Convert preview coordinates to actual coordinates
            # For now, just use the preview coordinates directly
            self.camera_controller.set_roi(
                (start_point.x(), start_point.y()),
                (end_point.x(), end_point.y())
            )
            logger.info(f"ROI set: ({start_point.x()}, {start_point.y()}) to ({end_point.x()}, {end_point.y()})")
    
    def on_set_roi(self):
        """Set ROI for motion detection"""
        # This button now just provides instructions
        logger.info("Click and drag on the preview to set ROI")
    
    def on_clear_roi(self):
        """Clear ROI"""
        self.camera_controller.clear_roi()
        self.preview_label.clear_roi()
        logger.info("ROI cleared")
    
    def load_default_roi(self):
        """Load default ROI from config"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'config.json')
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            roi_config = config.get('motion_detection', {}).get('default_roi', {})
            if roi_config.get('enabled', False):
                x = roi_config.get('x', 0)
                y = roi_config.get('y', 0)
                width = roi_config.get('width', 600)
                height = roi_config.get('height', 400)
                
                # Set ROI in preview label
                self.preview_label.set_roi_rect(x, y, width, height)
                
                # Set ROI in camera controller
                self.camera_controller.set_roi((x, y), (x + width, y + height))
                
                logger.info(f"Default ROI loaded: ({x}, {y}) to ({x + width}, {y + height})")
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
            self.exposure_slider.setValue(camera_config.get('exposure_ms', 20))
            self.wb_slider.setValue(camera_config.get('white_balance', 6637))
            self.iso_min_slider.setValue(camera_config.get('iso_min', 100))
            self.iso_max_slider.setValue(camera_config.get('iso_max', 800))
            
            # Load motion detection settings
            motion_config = self.config.get('motion_detection', {})
            self.sensitivity_slider.setValue(motion_config.get('threshold', 50))
            self.min_area_slider.setValue(motion_config.get('min_area', 500))
            
            logger.info("Camera settings loaded from config")
        except Exception as e:
            logger.error(f"Failed to load camera settings: {e}")
    
    def on_save_settings(self):
        """Save current settings"""
        try:
            # Update config with current camera settings
            self.config['camera']['focus'] = self.focus_slider.value()
            self.config['camera']['exposure_ms'] = self.exposure_slider.value()
            self.config['camera']['white_balance'] = self.wb_slider.value()
            self.config['camera']['iso_min'] = self.iso_min_slider.value()
            self.config['camera']['iso_max'] = self.iso_max_slider.value()
            
            # Update motion detection settings
            self.config['motion_detection']['threshold'] = self.sensitivity_slider.value()
            self.config['motion_detection']['min_area'] = self.min_area_slider.value()
            
            # Save to file
            config_path = os.path.join(
                os.path.dirname(__file__),
                'config.json'
            )
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            
            logger.info("Settings saved to config.json")
            
            # Settings will be applied automatically through the slider change events
            # when the camera controller reads the config on next connect
            logger.info("Camera settings will be applied on next camera connection")
            
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

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
        
        # Google Drive Upload Services
        drive_group = QGroupBox("Google Drive Upload Services")
        drive_layout = QGridLayout()
        
        # Folder name
        drive_layout.addWidget(QLabel("Folder:"), 0, 0)
        folder_name = self.uploader.config.get('services', {}).get('drive_upload', {}).get('folder_name', 'Unknown')
        self.drive_folder_name = QLabel(folder_name)
        self.drive_folder_name.setStyleSheet("color: #ffffff; font-weight: bold;")
        drive_layout.addWidget(self.drive_folder_name, 0, 1)
        
        # Drive upload status
        drive_layout.addWidget(QLabel("Status:"), 1, 0)
        self.drive_status = QLabel("Checking...")
        self.drive_status.setStyleSheet("color: orange;")
        drive_layout.addWidget(self.drive_status, 1, 1)
        
        # Upload queue
        drive_layout.addWidget(QLabel("Queue:"), 2, 0)
        self.drive_queue = QLabel("N/A")
        self.drive_queue.setStyleSheet("color: gray;")
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
        self.drive_folder_link.setStyleSheet("color: #4285f4; text-decoration: underline;")
        self.drive_folder_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.drive_folder_link.mousePressEvent = self.on_drive_folder_link_clicked
        drive_layout.addWidget(self.drive_folder_link, 6, 1)
        
        # Clear folder button
        self.clear_drive_btn = QPushButton("Clear Drive Folder")
        self.clear_drive_btn.clicked.connect(self.on_clear_drive_folder)
        drive_layout.addWidget(self.clear_drive_btn, 7, 0, 1, 2)
        
        drive_group.setLayout(drive_layout)
        left_layout.addWidget(drive_group)
        
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
        
        # Configuration toggles
        config_group = QGroupBox("Configuration")
        config_layout = QGridLayout()
        
        # Drive upload toggle
        config_layout.addWidget(QLabel("Google Drive Upload:"), 0, 0)
        self.drive_upload_cb = QCheckBox("Enabled")
        self.drive_upload_cb.stateChanged.connect(self.on_drive_upload_changed)
        config_layout.addWidget(self.drive_upload_cb, 0, 1)
        
        
        # Email notifications toggle
        config_layout.addWidget(QLabel("Email Notifications:"), 1, 0)
        self.email_notifications_cb = QCheckBox("Enabled")
        self.email_notifications_cb.stateChanged.connect(self.on_email_notifications_changed)
        config_layout.addWidget(self.email_notifications_cb, 1, 1)
        
        # Hourly reports toggle
        config_layout.addWidget(QLabel("Hourly Reports:"), 2, 0)
        self.hourly_reports_cb = QCheckBox("Enabled")
        self.hourly_reports_cb.stateChanged.connect(self.on_hourly_reports_changed)
        config_layout.addWidget(self.hourly_reports_cb, 2, 1)
        
        # Cleanup service toggle
        config_layout.addWidget(QLabel("Storage Cleanup:"), 3, 0)
        self.cleanup_cb = QCheckBox("Enabled")
        self.cleanup_cb.stateChanged.connect(self.on_cleanup_changed)
        config_layout.addWidget(self.cleanup_cb, 3, 1)
        
        # Save config button
        self.save_config_btn = QPushButton("Save Configuration")
        self.save_config_btn.clicked.connect(self.on_save_config)
        config_layout.addWidget(self.save_config_btn, 4, 0, 1, 2)
        
        config_group.setLayout(config_layout)
        left_layout.addWidget(config_group)
        
        left_layout.addStretch()
        
        # Right side widget - OpenAI Statistics
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
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
        reset_label.setStyleSheet("font-size: 10px; color: #888;")
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
        
        # Load current configuration
        self.load_config_toggles()
    
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
        logger.info(f"Updating Drive stats in GUI: {stats}")
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
    
    def on_clear_drive_folder(self):
        """Clear Google Drive folder"""
        try:
            if hasattr(self.uploader, 'drive_uploader') and self.uploader.drive_uploader:
                if self.uploader.drive_uploader.clear_drive_folder():
                    logger.info("Drive folder cleared successfully")
                    # Update stats immediately
                    self.update_upload_status()
                else:
                    logger.error("Failed to clear Drive folder")
            else:
                logger.error("Drive uploader not available")
        except Exception as e:
            logger.error(f"Error clearing Drive folder: {e}")
    
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
        """Send test email"""
        if self.email_handler:
            test_info = {
                'hostname': 'test-system',
                'ip_address': '127.0.0.1',
                'uptime': '5 minutes'
            }
            self.email_handler.send_reboot_notification(test_info)
            logger.info("Test email sent")
    
    def on_drive_upload_changed(self, state):
        """Handle Drive upload toggle change"""
        enabled = state == Qt.CheckState.Checked.value
        logger.info(f"Drive upload {'enabled' if enabled else 'disabled'}")
        # Update will be applied when Save Config is clicked
    
    def on_email_notifications_changed(self, state):
        """Handle Email notifications toggle change"""
        enabled = state == Qt.CheckState.Checked.value
        logger.info(f"Email notifications {'enabled' if enabled else 'disabled'}")
        # Update will be applied when Save Config is clicked
    
    def on_hourly_reports_changed(self, state):
        """Handle Hourly reports toggle change"""
        enabled = state == Qt.CheckState.Checked.value
        logger.info(f"Hourly reports {'enabled' if enabled else 'disabled'}")
        # Update will be applied when Save Config is clicked
    
    def on_cleanup_changed(self, state):
        """Handle Storage cleanup toggle change"""
        enabled = state == Qt.CheckState.Checked.value
        logger.info(f"Storage cleanup {'enabled' if enabled else 'disabled'}")
        # Update will be applied when Save Config is clicked
    
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
    
    def on_save_config(self):
        """Save configuration changes"""
        try:
            # Load current config
            config_path = os.path.join(os.path.dirname(__file__), 'config.json')
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Update config based on toggle states
            config['services']['drive_upload']['enabled'] = self.drive_upload_cb.isChecked()
            config['services']['cleanup']['enabled'] = self.cleanup_cb.isChecked()
            config['email']['hourly_report'] = self.hourly_reports_cb.isChecked()
            
            # Save config
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
            
            logger.info("Configuration saved successfully")
            
            # Show confirmation
            from PyQt6.QtWidgets import QMessageBox
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText("Configuration saved successfully!")
            msg.setInformativeText("Restart the application for changes to take effect.")
            msg.setWindowTitle("Configuration Saved")
            msg.exec()
            
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            
            # Show error
            from PyQt6.QtWidgets import QMessageBox
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setText("Error saving configuration!")
            msg.setInformativeText(str(e))
            msg.setWindowTitle("Configuration Error")
            msg.exec()
    
    def load_config_toggles(self):
        """Load current configuration into toggles"""
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'config.json')
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Set toggle states based on config
            self.drive_upload_cb.setChecked(config['services']['drive_upload']['enabled'])
            self.cleanup_cb.setChecked(config['services']['cleanup']['enabled'])
            self.hourly_reports_cb.setChecked(config['email']['hourly_report'])
            
            # Email notifications are always enabled for now
            self.email_notifications_cb.setChecked(True)
            
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")

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
        self.email_enabled = QCheckBox("Enable Email Notifications")
        group_layout.addWidget(self.email_enabled, 2, 0, 1, 3)
        
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
        
        # Clear button
        clear_local_btn = QPushButton("Clear All Local Images")
        clear_local_btn.clicked.connect(self.clear_local_images)
        group_layout.addWidget(clear_local_btn, 3, 0, 1, 3)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
    
    def create_drive_section(self, layout):
        group = QGroupBox("Google Drive")
        group_layout = QGridLayout()
        
        # Drive enabled
        self.drive_enabled = QCheckBox("Enable Google Drive Upload")
        group_layout.addWidget(self.drive_enabled, 0, 0, 1, 3)
        
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
        
        # OAuth setup button
        setup_drive_btn = QPushButton("Setup Google Drive OAuth")
        setup_drive_btn.clicked.connect(self.setup_google_drive)
        group_layout.addWidget(setup_drive_btn, 3, 0, 1, 2)
        
        # Clear button
        clear_drive_btn = QPushButton("Clear All Drive Images")
        clear_drive_btn.clicked.connect(self.clear_drive_images)
        group_layout.addWidget(clear_drive_btn, 3, 2)
        
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
        group_layout.addWidget(self.openai_key, 1, 1, 1, 2)
        
        # Rate limit
        group_layout.addWidget(QLabel("Max Images/Hour:"), 2, 0)
        self.openai_limit = QSpinBox()
        self.openai_limit.setRange(1, 20)
        self.openai_limit.setValue(10)
        group_layout.addWidget(self.openai_limit, 2, 1)
        
        # Clear species button
        clear_species_btn = QPushButton("Clear Species Database")
        clear_species_btn.clicked.connect(self.clear_species_database)
        group_layout.addWidget(clear_species_btn, 3, 0, 1, 3)
        
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
        self.email_enabled.setChecked(bool(email_config.get('sender')))
        
        # Storage settings
        storage_config = self.config.get('storage', {})
        self.storage_dir.setText(storage_config.get('save_dir', str(Path.home() / 'BirdPhotos')))
        self.storage_limit.setValue(storage_config.get('max_size_gb', 2))
        
        cleanup_time = storage_config.get('cleanup_time', '23:30')
        hour, minute = map(int, cleanup_time.split(':'))
        self.cleanup_time.setTime(QTime(hour, minute))
        
        # Drive settings
        drive_config = self.config.get('services', {}).get('drive_upload', {})
        self.drive_enabled.setChecked(drive_config.get('enabled', False))
        self.drive_folder.setText(drive_config.get('folder_name', 'Bird Photos'))
        self.drive_limit.setValue(drive_config.get('max_size_gb', 2))
        
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
    
    def clear_local_images(self):
        """Clear all local images"""
        reply = QMessageBox.question(
            self, "Clear Local Images", 
            "Are you sure you want to delete all local images?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                storage_path = Path(self.storage_dir.text())
                if storage_path.exists():
                    for img_file in storage_path.glob("*.jpeg"):
                        img_file.unlink()
                    for img_file in storage_path.glob("*.jpg"):
                        img_file.unlink()
                QMessageBox.information(self, "Success", "Local images cleared!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear images: {str(e)}")
    
    def clear_drive_images(self):
        """Clear all Google Drive images"""
        reply = QMessageBox.question(
            self, "Clear Drive Images", 
            "Are you sure you want to delete all Google Drive images?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            QMessageBox.information(self, "Info", "Drive clearing not yet implemented. Use Google Drive web interface.")
    
    def clear_species_database(self):
        """Clear all identified bird species"""
        reply = QMessageBox.question(
            self, "Clear Species Database", 
            "Are you sure you want to delete all identified bird species?\n\nThis will remove all AI identification history.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                species_db_path = Path(__file__).parent / "species_database.json"
                if species_db_path.exists():
                    # Reset to empty database
                    empty_db = {"species": {}, "sightings": []}
                    with open(species_db_path, 'w') as f:
                        json.dump(empty_db, f, indent=2)
                    QMessageBox.information(self, "Success", "Species database cleared!")
                else:
                    QMessageBox.information(self, "Info", "Species database doesn't exist yet.")
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
                
                subprocess.Popen(['x-terminal-emulator', '-e', f'bash {install_script}'])
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to run installer: {str(e)}")
    
    def start_watchdog(self):
        """Start watchdog service"""
        try:
            result = subprocess.run(['sudo', 'systemctl', 'start', 'bird-detection-watchdog.service'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                QMessageBox.information(self, "Success", "Watchdog service started!")
                self.check_watchdog_status()
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
                # Try to stop the service
                result = subprocess.run(['sudo', 'systemctl', 'stop', 'bird-detection-watchdog.service'], 
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
                        self.check_watchdog_status()
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
            
            # Show confirmation
            status = "enabled" if enabled else "disabled"
            QMessageBox.information(self, "Logging Settings", 
                                  f"Logging has been {status}.\n"
                                  f"{'Full verbosity restored.' if enabled else 'Only errors will be logged for better performance.'}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update logging: {str(e)}")
    
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
                'sender': self.email_sender.text(),
                'password': self.email_password.text(),
                'receivers': {'primary': self.email_sender.text()},
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 465,
                'hourly_report': True,
                'daily_email_time': '16:30',
                'quiet_hours': {'start': 23, 'end': 5}
            }
            
            self.config['storage'] = {
                'save_dir': self.storage_dir.text(),
                'max_size_gb': self.storage_limit.value(),
                'cleanup_time': self.cleanup_time.time().toString('HH:mm')
            }
            
            if 'services' not in self.config:
                self.config['services'] = {}
            
            self.config['services']['drive_upload'] = {
                'enabled': self.drive_enabled.isChecked(),
                'folder_name': self.drive_folder.text(),
                'upload_delay': 3,
                'max_size_gb': self.drive_limit.value(),
                'note': 'OAuth2 only - personal Google Drive folder'
            }
            
            self.config['openai'] = {
                'api_key': self.openai_key.text(),
                'enabled': self.openai_enabled.isChecked(),
                'max_images_per_hour': self.openai_limit.value()
            }
            
            # Save to file
            self.config_manager.save_config()
            QMessageBox.information(self, "Success", "Configuration saved!")
            
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
        
        self.clear_btn = QPushButton("Clear Logs")
        self.clear_btn.clicked.connect(self.clear_logs)
        controls_layout.addWidget(self.clear_btn)
        
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
            # Get new log lines
            lines = log_buffer.get_lines()
            
            # Update display
            if lines:
                self.log_display.clear()
                self.log_display.append('\n'.join(lines))
                
                # Auto scroll to bottom
                if self.auto_scroll_cb.isChecked():
                    cursor = self.log_display.textCursor()
                    cursor.movePosition(cursor.MoveOperation.End)
                    self.log_display.setTextCursor(cursor)
                    
        except Exception as e:
            logger.error(f"Error updating logs: {e}")
    
    def clear_logs(self):
        """Clear log display"""
        self.log_display.clear()
        log_buffer.clear()

class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        current_dir = Path(__file__).parent.name
        self.base_title = f"Bird Detection System - {current_dir}"
        self.setWindowTitle(self.base_title)
        self.setGeometry(100, 100, 1200, 800)
        
        # Clock timer
        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(10000)  # Update every 10 seconds to reduce CPU load
        
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
        
        layout.addWidget(self.tab_widget)
        
        # Status bar
        self.statusBar().showMessage("Initializing...")
    
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
    
    def start_services(self):
        """Start all services"""
        try:
            # Start camera
            if self.camera_controller.connect():
                self.camera_thread = CameraThread(self.camera_controller)
                self.camera_thread.frame_ready.connect(self.camera_tab.update_frame)
                self.camera_thread.image_captured.connect(self.on_image_captured)
                self.camera_thread.start()
                logger.info("Camera service started")
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
                stderr=subprocess.PIPE
            )
            
            # Give it a moment to start
            time.sleep(1)
            
            # Check if process started successfully
            if self.web_server_process.poll() is not None:
                # Process already exited - get error
                stdout, stderr = self.web_server_process.communicate()
                logger.error(f"Web server failed to start: {stderr.decode()}")
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
            
            self.mobile_url = f"http://{local_ip}:8080"
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
        """Update window title with current time"""
        from datetime import datetime
        current_time = datetime.now().strftime("%H:%M:%S")
        self.setWindowTitle(f"{self.base_title} - {current_time}")
    
    def on_image_captured(self, image_path):
        """Handle image capture"""
        logger.info(f"Image captured: {image_path}")
        
        # Update camera tab stats
        if hasattr(self, 'camera_tab'):
            self.camera_tab.on_photo_captured()
            self.camera_tab.on_motion_detected()  # Photo capture means motion was detected
        
        # Queue for upload
        self.uploader.queue_file(image_path)
        
        # AI Bird Identification (Day 1 Feature)
        if self.bird_identifier.enabled:
            # Run identification in a separate thread to avoid blocking
            def identify_bird():
                result = self.bird_identifier.identify_bird(image_path)
                if result and result.get('identified'):
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
                elif result and not result.get('identified'):
                    # No bird detected - delete the image to save space
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
        
        # Stop camera thread
        if self.camera_thread:
            self.camera_thread.stop()
        
        # Stop timers
        if hasattr(self, 'status_timer'):
            self.status_timer.stop()
        if hasattr(self, 'slow_timer'):
            self.slow_timer.stop()
        
        # Stop services
        self.camera_controller.disconnect()
        self.email_handler.stop()
        self.uploader.stop()
        self.service_monitor.stop()
        
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