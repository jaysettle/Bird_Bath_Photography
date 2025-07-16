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

# PyQt6 imports
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, 
                           QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton,
                           QTextEdit, QGroupBox, QGridLayout, QCheckBox, QSpinBox,
                           QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
                           QSplitter, QFrame)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QMutex, QPoint, QRect
from PyQt6.QtGui import QPixmap, QImage, QFont, QPalette, QColor, QPainter, QPen, QMouseEvent
import cv2
import numpy as np

# Local imports
from src.logger import setup_logging, setup_gui_logging, get_logger, log_buffer
from src.camera_controller import CameraController
from src.email_handler import EmailHandler
from src.drive_uploader_simple import CombinedUploader

# Set up logging
setup_logging()
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
                
                # Check for captured images
                captured_image = self.camera_controller.get_captured_image()
                if captured_image:
                    self.image_captured.emit(captured_image)
                
                # Small delay to prevent high CPU usage
                self.msleep(33)  # ~30 FPS
                
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
            'cleanup.service'
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
                for _ in range(50):
                    if not self.running:
                        break
                    self.msleep(100)
                    
            except Exception as e:
                logger.error(f"Error in service monitor: {e}")
                self.msleep(1000)
    
    def stop(self):
        """Stop the service monitor"""
        self.running = False
        self.wait()

class CameraTab(QWidget):
    """Camera control and preview tab"""
    
    def __init__(self, camera_controller):
        super().__init__()
        self.camera_controller = camera_controller
        self.current_frame = None
        self.roi_drawing = False
        self.roi_start = None
        self.roi_end = None
        self.setup_ui()
        self.load_default_roi()
        
    def setup_ui(self):
        """Setup the camera tab UI"""
        layout = QHBoxLayout()
        
        # Left side - Camera preview
        preview_layout = QVBoxLayout()
        
        # Camera preview label
        self.preview_label = InteractivePreviewLabel()
        self.preview_label.roi_selected.connect(self.on_roi_selected)
        preview_layout.addWidget(self.preview_label)
        
        # Camera info
        self.info_label = QLabel("Camera: Disconnected")
        self.info_label.setStyleSheet("font-family: monospace; background-color: #f0f0f0; padding: 5px;")
        preview_layout.addWidget(self.info_label)
        
        # Instructions
        instructions = QLabel("💡 Click and drag on preview to set Motion ROI")
        instructions.setStyleSheet("color: #666; font-size: 11px; padding: 2px;")
        preview_layout.addWidget(instructions)
        
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
        
        # Update info
        self.info_label.setText(f"Camera: Connected | Frame: {width}x{height} | FPS: ~30")
    
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
    
    def on_save_settings(self):
        """Save current settings"""
        # Save to config file
        logger.info("Settings saved")

class ServicesTab(QWidget):
    """Services monitoring and control tab"""
    
    def __init__(self, email_handler, uploader):
        super().__init__()
        self.email_handler = email_handler
        self.uploader = uploader
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the services tab UI"""
        layout = QVBoxLayout()
        
        # System services status
        services_group = QGroupBox("System Services")
        services_layout = QVBoxLayout()
        
        self.services_table = QTableWidget()
        self.services_table.setColumnCount(3)
        self.services_table.setHorizontalHeaderLabels(["Service", "Status", "Action"])
        self.services_table.horizontalHeader().setStretchLastSection(True)
        
        services_layout.addWidget(self.services_table)
        services_group.setLayout(services_layout)
        layout.addWidget(services_group)
        
        # Upload services status
        upload_group = QGroupBox("Upload Services")
        upload_layout = QGridLayout()
        
        # Drive upload status
        upload_layout.addWidget(QLabel("Google Drive:"), 0, 0)
        self.drive_status = QLabel("Disabled (Quota Full)")
        self.drive_status.setStyleSheet("color: orange;")
        upload_layout.addWidget(self.drive_status, 0, 1)
        self.drive_queue = QLabel("N/A")
        self.drive_queue.setStyleSheet("color: gray;")
        upload_layout.addWidget(self.drive_queue, 0, 2)
        
        
        upload_group.setLayout(upload_layout)
        layout.addWidget(upload_group)
        
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
        layout.addWidget(email_group)
        
        # Storage status
        storage_group = QGroupBox("Storage")
        storage_layout = QGridLayout()
        
        storage_layout.addWidget(QLabel("Save Directory:"), 0, 0)
        self.storage_path = QLabel("/home/jaysettle/PiShare")
        storage_layout.addWidget(self.storage_path, 0, 1)
        
        storage_layout.addWidget(QLabel("Used Space:"), 1, 0)
        self.storage_used = QLabel("0.0 GB")
        storage_layout.addWidget(self.storage_used, 1, 1)
        
        storage_layout.addWidget(QLabel("File Count:"), 2, 0)
        self.file_count = QLabel("0")
        storage_layout.addWidget(self.file_count, 2, 1)
        
        storage_group.setLayout(storage_layout)
        layout.addWidget(storage_group)
        
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
        layout.addWidget(config_group)
        
        layout.addStretch()
        self.setLayout(layout)
        
        # Load current configuration
        self.load_config_toggles()
    
    def update_service_status(self, status):
        """Update service status table"""
        self.services_table.setRowCount(len(status))
        
        for i, (service, state) in enumerate(status.items()):
            # Service name
            name_item = QTableWidgetItem(service)
            self.services_table.setItem(i, 0, name_item)
            
            # Status with color
            status_item = QTableWidgetItem(state)
            if state == 'active':
                status_item.setBackground(QColor(0, 128, 0))  # Dark green
                status_item.setForeground(QColor(255, 255, 255))  # White text
            elif state in ['inactive', 'failed']:
                status_item.setBackground(QColor(128, 0, 0))  # Dark red
                status_item.setForeground(QColor(255, 255, 255))  # White text
            else:
                status_item.setBackground(QColor(128, 128, 0))  # Dark yellow
                status_item.setForeground(QColor(255, 255, 255))  # White text
            
            self.services_table.setItem(i, 1, status_item)
            
            # Action button (placeholder)
            action_item = QTableWidgetItem("Restart")
            self.services_table.setItem(i, 2, action_item)
    
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
                
            self.drive_queue.setText(f"Queue: {drive_queue}")
            self.drive_queue.setStyleSheet("color: #ffffff;")
            
    
    def update_email_status(self):
        """Update email service status"""
        if self.email_handler:
            queue_size = self.email_handler.get_queue_size()
            self.email_queue.setText(str(queue_size))
    
    def update_storage_status(self):
        """Update storage information"""
        try:
            storage_dir = "/home/jaysettle/PiShare"
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
                
                # Convert to GB
                size_gb = total_size / (1024**3)
                
                # Update labels
                self.storage_used.setText(f"{size_gb:.2f} GB")
                self.file_count.setText(str(file_count))
            else:
                self.storage_used.setText("Directory not found")
                self.file_count.setText("0")
                
        except Exception as e:
            logger.error(f"Error updating storage status: {e}")
            self.storage_used.setText("Error")
            self.file_count.setText("0")
    
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

class LogsTab(QWidget):
    """Real-time logs tab"""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        
        # Timer for log updates
        self.log_timer = QTimer()
        self.log_timer.timeout.connect(self.update_logs)
        self.log_timer.start(1000)  # Update every second
        
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
        self.setWindowTitle("Bird Detection System")
        self.setGeometry(100, 100, 1200, 800)
        
        # Load configuration
        self.load_config()
        
        # Initialize services
        self.init_services()
        
        # Setup UI
        self.setup_ui()
        
        # Setup timers
        self.setup_timers()
        
        # Start services
        self.start_services()
        
        logger.info("Main window initialized")
    
    def load_config(self):
        """Load configuration"""
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        try:
            with open(config_path, 'r') as f:
                self.config = json.load(f)
            logger.info("Configuration loaded")
            
            # Log configuration status
            logger.info(f"Drive upload {'enabled' if self.config.get('services', {}).get('drive_upload', {}).get('enabled', False) else 'disabled'}")
            logger.info(f"Storage cleanup {'enabled' if self.config.get('services', {}).get('cleanup', {}).get('enabled', False) else 'disabled'}")
            logger.info(f"Hourly reports {'enabled' if self.config.get('email', {}).get('hourly_report', False) else 'disabled'}")
            logger.info(f"Email notifications {'enabled' if self.config.get('email', {}).get('sender') else 'disabled'}")
            
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.config = {}
    
    def init_services(self):
        """Initialize all services"""
        # Camera controller
        self.camera_controller = CameraController(self.config)
        
        # Email handler
        self.email_handler = EmailHandler(self.config)
        
        # Upload service
        self.uploader = CombinedUploader(self.config)
        
        # Service monitor
        self.service_monitor = ServiceMonitor()
        
        # Camera thread
        self.camera_thread = None
    
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
        self.camera_tab = CameraTab(self.camera_controller)
        self.tab_widget.addTab(self.camera_tab, "Camera")
        
        # Services tab
        self.services_tab = ServicesTab(self.email_handler, self.uploader)
        self.tab_widget.addTab(self.services_tab, "Services")
        
        # Logs tab
        self.logs_tab = LogsTab()
        self.tab_widget.addTab(self.logs_tab, "Logs")
        
        layout.addWidget(self.tab_widget)
        
        # Status bar
        self.statusBar().showMessage("Initializing...")
    
    def setup_timers(self):
        """Setup update timers"""
        # Status update timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(5000)  # Update every 5 seconds
    
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
            
            # Start upload service
            self.uploader.start()
            
            # Start service monitor
            self.service_monitor.service_status_updated.connect(
                self.services_tab.update_service_status
            )
            self.service_monitor.start()
            
            self.statusBar().showMessage("All services started")
            logger.info("All services started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start services: {e}")
            self.statusBar().showMessage(f"Error starting services: {e}")
    
    def update_status(self):
        """Update status information"""
        self.services_tab.update_upload_status()
        self.services_tab.update_email_status()
        self.services_tab.update_storage_status()
    
    def on_image_captured(self, image_path):
        """Handle image capture"""
        logger.info(f"Image captured: {image_path}")
        
        # Queue for upload
        self.uploader.queue_file(image_path)
        
        # Email notifications are sent via hourly reports only
        # Individual motion capture emails are disabled
        
        self.statusBar().showMessage(f"Image captured: {os.path.basename(image_path)}")
    
    def closeEvent(self, event):
        """Handle application close"""
        logger.info("Shutting down application...")
        
        # Stop camera thread
        if self.camera_thread:
            self.camera_thread.stop()
        
        # Stop services
        self.camera_controller.disconnect()
        self.email_handler.stop()
        self.uploader.stop()
        self.service_monitor.stop()
        
        event.accept()
        logger.info("Application closed")

def main():
    """Main function"""
    # Set environment variables
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    os.environ["DISPLAY"] = ":0"
    
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