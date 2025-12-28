#!/usr/bin/env python3
"""Camera control and preview tab"""

import os
import json
from datetime import datetime
import time
from pathlib import Path

# Get app root directory (two levels up from this file)
APP_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = APP_ROOT / 'config.json'
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                            QGroupBox, QLabel, QSlider, QPushButton, QCheckBox,
                            QComboBox, QSpinBox, QMessageBox, QApplication, QToolTip)
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QPixmap, QImage

from src.logger import get_logger
from src.ui.preview_widgets import InteractivePreviewLabel

logger = get_logger(__name__)


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
        # Preview is now fixed at 960x540 (no need to set resolution)
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
        # Range: 1-3300 (represents 0.01ms to 33ms in 0.01ms increments)
        self.exposure_slider.setRange(1, 3300)
        self.exposure_slider.setValue(200)
        self.exposure_slider.valueChanged.connect(self.on_exposure_changed)
        camera_layout.addWidget(self.exposure_slider, 1, 1)
        self.exposure_value = QLabel("2.0ms")
        camera_layout.addWidget(self.exposure_value, 1, 2)
        
        # Auto exposure checkbox
        self.auto_exposure_cb = QCheckBox("Auto Exposure")
        self.auto_exposure_cb.setChecked(True)
        self.auto_exposure_cb.stateChanged.connect(self.on_auto_exposure_changed)
        camera_layout.addWidget(self.auto_exposure_cb, 2, 0, 1, 3)

        # Exposure compensation slider (for auto exposure mode)
        camera_layout.addWidget(QLabel("EV Offset:"), 3, 0)
        self.ev_offset_slider = QSlider(Qt.Orientation.Horizontal)
        self.ev_offset_slider.setRange(-9, 9)
        self.ev_offset_slider.setValue(0)
        self.ev_offset_slider.valueChanged.connect(self.on_ev_offset_changed)
        camera_layout.addWidget(self.ev_offset_slider, 3, 1)
        self.ev_offset_value = QLabel("0")
        camera_layout.addWidget(self.ev_offset_value, 3, 2)

        # White balance slider
        camera_layout.addWidget(QLabel("White Balance:"), 4, 0)
        self.wb_slider = QSlider(Qt.Orientation.Horizontal)
        self.wb_slider.setRange(2000, 7500)
        self.wb_slider.setValue(6637)
        self.wb_slider.valueChanged.connect(self.on_wb_changed)
        camera_layout.addWidget(self.wb_slider, 4, 1)
        self.wb_value = QLabel("6637K")
        camera_layout.addWidget(self.wb_value, 4, 2)

        # Brightness slider
        camera_layout.addWidget(QLabel("Brightness:"), 5, 0)
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(-10, 10)
        self.brightness_slider.setValue(0)
        self.brightness_slider.valueChanged.connect(self.on_brightness_changed)
        camera_layout.addWidget(self.brightness_slider, 5, 1)
        self.brightness_value = QLabel("0")
        camera_layout.addWidget(self.brightness_value, 5, 2)

        # ISO Min
        camera_layout.addWidget(QLabel("ISO Min:"), 6, 0)
        self.iso_min_slider = QSlider(Qt.Orientation.Horizontal)
        self.iso_min_slider.setRange(100, 3200)
        self.iso_min_slider.setValue(100)
        self.iso_min_slider.valueChanged.connect(self.on_iso_min_changed)
        camera_layout.addWidget(self.iso_min_slider, 6, 1)
        self.iso_min_value = QLabel("100")
        camera_layout.addWidget(self.iso_min_value, 6, 2)

        # ISO Max
        camera_layout.addWidget(QLabel("ISO Max:"), 7, 0)
        self.iso_max_slider = QSlider(Qt.Orientation.Horizontal)
        self.iso_max_slider.setRange(100, 3200)
        self.iso_max_slider.setValue(800)
        self.iso_max_slider.valueChanged.connect(self.on_iso_max_changed)
        camera_layout.addWidget(self.iso_max_slider, 7, 1)
        self.iso_max_value = QLabel("800")
        camera_layout.addWidget(self.iso_max_value, 7, 2)

        # Capture Resolution dropdown
        camera_layout.addWidget(QLabel("Capture:"), 8, 0)
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
        camera_layout.addWidget(self.resolution_combo, 8, 1, 1, 2)

        # Preview resolution is now fixed at 1080p - no UI selector needed
        
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
        self.debounce_slider.setValue(4)
        self.debounce_slider.valueChanged.connect(self.on_debounce_changed)
        motion_settings_layout.addWidget(self.debounce_slider, 0, 1)
        self.debounce_value = QLabel("4.0s")
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
        
        # Preview and capture info
        self.preview_res_label = QLabel("Preview: Unknown")
        self.preview_res_label.setStyleSheet("font-size: 11px;")
        stats_layout.addWidget(self.preview_res_label, 2, 1)

        self.capture_res_label = QLabel("Capture: Unknown")
        self.capture_res_label.setStyleSheet("font-size: 11px;")
        stats_layout.addWidget(self.capture_res_label, 3, 1)

        # Column 3 - Zoom and ROI
        self.zoom_label = QLabel("Zoom: 1.00x")
        self.zoom_label.setStyleSheet("font-size: 11px;")
        stats_layout.addWidget(self.zoom_label, 0, 2)

        self.roi_label = QLabel("ROI: None")
        self.roi_label.setStyleSheet("font-size: 11px;")
        stats_layout.addWidget(self.roi_label, 1, 2)

        # Weather status (shown when enabled)
        self.weather_label = QLabel("Weather: --")
        self.weather_label.setStyleSheet("font-size: 11px;")
        stats_layout.addWidget(self.weather_label, 2, 2)

        # Motion detection status (active/inactive based on weather)
        self.motion_status_label = QLabel("Motion: Active")
        self.motion_status_label.setStyleSheet("font-size: 11px; color: #4CAF50; font-weight: bold;")
        stats_layout.addWidget(self.motion_status_label, 3, 2)

        # Weather override checkbox
        self.weather_override_cb = QCheckBox("Override Rain Pause")
        self.weather_override_cb.setStyleSheet("font-size: 10px;")
        self.weather_override_cb.setToolTip("Enable motion detection even when raining")
        self.weather_override_cb.stateChanged.connect(self.on_weather_override_changed)
        stats_layout.addWidget(self.weather_override_cb, 4, 2)

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
        frame_start_time = time.time()
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
            q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).rgbSwapped()

            if q_image.isNull():
                logger.error("[FREEZE-CHECK] Failed to create QImage from frame data")
                return

            pixmap = QPixmap.fromImage(q_image)
            if pixmap.isNull():
                logger.error("[FREEZE-CHECK] Failed to create QPixmap from QImage")
                return

            scaled_pixmap = pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )

            self.preview_label.setPixmap(scaled_pixmap)

            # Update FPS in stats (approximate)
            if hasattr(self, 'sensor_fps_label'):
                sensor_res = getattr(self, 'sensor_resolution_label', QLabel()).text()
                if sensor_res == "Unknown":
                    sensor_res = "4056x3040"
                self.sensor_fps_label.setText(f"Sensor: {sensor_res} | FPS: ~30")

            # Log slow frame updates
            frame_total_time = time.time() - frame_start_time
            if frame_total_time > 0.05:  # >50ms is slow for 30fps
                logger.warning(f"[FRAME-SLOW] update_frame took {frame_total_time:.3f}s - this blocks Qt event loop!")

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
        
        # Update resolution mode (capture resolution from config)
        capture_res = self.config.get('camera', {}).get('resolution', '13mp')
        self.resolution_mode_label.setText(f"Resolution: {capture_res}")

        # Update preview resolution
        preview_res = self.config.get('camera', {}).get('preview_resolution', 'THE_720_P')
        # Convert preview resolution to readable format
        preview_map = {
            'THE_1211x1013': '1211x1013',
            'THE_1250x1036': '1250x1036',
            'THE_1080_P': '1080p',
            'THE_720_P': '720p',
            'THE_480_P': '480p',
            'THE_400_P': '400p',
            'THE_300_P': '300p'
        }
        preview_readable = preview_map.get(preview_res, preview_res)
        self.preview_res_label.setText(f"Preview: {preview_readable}")

        # Update capture resolution (more detailed than mode)
        capture_readable = capture_res.upper()
        self.capture_res_label.setText(f"Capture: {capture_readable}")

        # Update zoom level
        if hasattr(self.preview_label, 'zoom_factor'):
            zoom = self.preview_label.zoom_factor
            self.zoom_label.setText(f"Zoom: {zoom:.2f}x")

        # Update ROI info
        if self.camera_controller.roi_defined and hasattr(self.preview_label, 'roi_rect'):
            roi_rect = self.preview_label.roi_rect
            if not roi_rect.isEmpty():
                # Show ROI in base coordinates (not zoomed)
                zoom_factor = getattr(self.preview_label, 'zoom_factor', 1.0)
                base_x = int(roi_rect.x() / zoom_factor)
                base_y = int(roi_rect.y() / zoom_factor)
                base_w = int(roi_rect.width() / zoom_factor)
                base_h = int(roi_rect.height() / zoom_factor)
                self.roi_label.setText(f"ROI: {base_x},{base_y} {base_w}x{base_h}")
            else:
                self.roi_label.setText("ROI: None")
        else:
            self.roi_label.setText("ROI: None")
    
    def on_motion_detected(self):
        """Called when motion is detected - updates stats"""
        self.motion_event_count += 1
        self.daily_motion_events += 1
        
    def on_photo_captured(self):
        """Called when a photo is captured - updates stats"""
        self.session_capture_count += 1
        self.last_capture_time = datetime.now()

    def update_weather_status(self, weather_status):
        """Update weather status display in stats panel"""
        if not weather_status.get('enabled', False):
            self.weather_label.setText("Weather: Disabled")
            self.motion_status_label.setText("Motion: Active")
            self.motion_status_label.setStyleSheet("font-size: 11px; color: #4CAF50; font-weight: bold;")
            return

        # Show weather description and temperature
        description = weather_status.get('description', 'Unknown')
        temperature = weather_status.get('temperature')
        if temperature:
            self.weather_label.setText(f"Weather: {description}, {temperature:.0f}°F")
        else:
            self.weather_label.setText(f"Weather: {description}")

        # Check if override is active
        override_active = self.weather_override_cb.isChecked()

        # Show motion status with colors
        if weather_status.get('is_raining', False) and not override_active:
            # Inactive - red
            self.motion_status_label.setText("Motion: INACTIVE (Rain)")
            self.motion_status_label.setStyleSheet("font-size: 11px; color: #F44336; font-weight: bold;")
        else:
            # Active - green
            if override_active and weather_status.get('is_raining', False):
                self.motion_status_label.setText("Motion: Active (Override)")
                self.motion_status_label.setStyleSheet("font-size: 11px; color: #FF9800; font-weight: bold;")
            else:
                self.motion_status_label.setText("Motion: Active")
                self.motion_status_label.setStyleSheet("font-size: 11px; color: #4CAF50; font-weight: bold;")

    def on_weather_override_changed(self, state):
        """Handle weather override checkbox change"""
        override_active = state == Qt.CheckState.Checked.value
        logger.info(f"[WEATHER] Override {'enabled' if override_active else 'disabled'}")

        # Update camera controller pause state
        if override_active:
            # Override - unpause motion detection
            self.camera_controller.motion_paused = False
            self.camera_controller.pause_reason = ""
        # Note: If override is disabled and it's raining, the next weather check will re-pause

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
        # Slider value is in 0.01ms units (1-3300 = 0.01-33ms)
        exposure_ms = value / 100.0
        self.exposure_value.setText(f"{exposure_ms:.2f}ms")

        auto_exposure_enabled = self.auto_exposure_cb.isChecked()
        logger.info(f"[EXPOSURE] Slider changed: value={value}, exposure_ms={exposure_ms:.2f}ms, auto_exposure={auto_exposure_enabled}")

        if not auto_exposure_enabled:
            logger.info(f"[EXPOSURE] Applying manual exposure: {exposure_ms:.2f}ms")
            self.camera_controller.update_camera_setting('exposure', exposure_ms)
        else:
            logger.info(f"[EXPOSURE] Skipping - auto exposure is enabled")
    
    def on_auto_exposure_changed(self, state):
        """Handle auto exposure checkbox change"""
        enabled = state == Qt.CheckState.Checked.value
        logger.info(f"[EXPOSURE] Auto exposure changed: enabled={enabled}, state={state}")
        self.camera_controller.update_camera_setting('auto_exposure', enabled)
        self.exposure_slider.setEnabled(not enabled)
        # EV offset only works in auto exposure mode
        self.ev_offset_slider.setEnabled(enabled)
        logger.info(f"[EXPOSURE] Exposure slider {'disabled' if enabled else 'enabled'}, EV offset {'enabled' if enabled else 'disabled'}")

    def on_ev_offset_changed(self, value):
        """Handle EV offset slider change (exposure compensation for auto mode)"""
        self.ev_offset_value.setText(f"{value:+d}" if value != 0 else "0")
        logger.info(f"[EXPOSURE] EV offset changed: {value}")
        self.camera_controller.update_camera_setting('ev_compensation', value)

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
            with open(CONFIG_PATH, 'w') as f:
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
            # Use self.config instead of loading from file
            motion_config = self.config.get('motion_detection', {})
            
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
                # Load ROI coordinates directly (no zoom conversion - fixed 960x540 preview)
                logger.info("=" * 80)
                logger.info(f"ROI LOAD: {roi_config} (preview: 960x540)")

                x = roi_config.get('x', 0)
                y = roi_config.get('y', 0)
                width = roi_config.get('width', 960)
                height = roi_config.get('height', 540)

                logger.info(f"ROI LOAD: x={x}, y={y}, w={width}, h={height}")

                # Set ROI in preview label (directly, no conversion needed)
                self.preview_label.set_roi_rect(x, y, width, height)

                # Scale ROI coordinates from display (960x540) to camera resolution (1920x1080)
                # Fixed scaling: camera is 2x display size
                camera_x1 = x * 2
                camera_y1 = y * 2
                camera_x2 = (x + width) * 2
                camera_y2 = (y + height) * 2

                # Set ROI in camera controller with scaled coordinates
                self.camera_controller.set_roi((camera_x1, camera_y1), (camera_x2, camera_y2))

                logger.info(f"ROI LOAD: Display ({x}, {y}) to ({x + width}, {y + height})")
                logger.info(f"ROI LOAD: Camera ({camera_x1}, {camera_y1}) to ({camera_x2}, {camera_y2})")
                logger.info("=" * 80)
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
            # Convert exposure from ms to slider units (0.01ms increments)
            exposure_ms = camera_config.get('exposure_ms', 2.0)
            self.exposure_slider.setValue(int(exposure_ms * 100))
            self.wb_slider.setValue(camera_config.get('white_balance', 6637))
            self.brightness_slider.setValue(camera_config.get('brightness', 0))
            self.brightness_value.setText(str(self.brightness_slider.value()))
            self.iso_min_slider.setValue(camera_config.get('iso_min', 100))
            self.iso_max_slider.setValue(camera_config.get('iso_max', 800))

            # Load EV compensation offset
            ev_offset = camera_config.get('ev_compensation', 0)
            self.ev_offset_slider.setValue(ev_offset)
            self.ev_offset_value.setText(f"{ev_offset:+d}" if ev_offset != 0 else "0")
            # EV offset only works in auto exposure mode (which is default on)
            self.ev_offset_slider.setEnabled(True)
            logger.info(f"[EV] Loaded EV offset from config: {ev_offset:+d}")
            # Apply EV offset to camera
            if ev_offset != 0:
                self.camera_controller.update_camera_setting('ev_compensation', ev_offset)

            # Preview resolution is now fixed at THE_1080_P - no loading needed

            # Load motion detection settings
            motion_config = self.config.get('motion_detection', {})
            threshold_value = motion_config.get('threshold', 50)
            self.sensitivity_slider.setValue(threshold_value)
            # Update display with inverted value
            display_value = 110 - threshold_value
            self.sensitivity_value.setText(str(display_value))

            # Load debounce time
            debounce_value = motion_config.get('debounce_time', 4)
            self.debounce_slider.setValue(int(debounce_value))
            self.debounce_value.setText(f"{int(debounce_value)}.0s")
            self.camera_controller.debounce_time = int(debounce_value)

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
            # Convert slider value (0.01ms units) to milliseconds
            new_exposure = self.exposure_slider.value() / 100.0
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

            old_ev_offset = self.config['camera'].get('ev_compensation', 0)
            new_ev_offset = self.ev_offset_slider.value()
            if old_ev_offset != new_ev_offset:
                changes.append(f"• EV Offset: {old_ev_offset:+d} → {new_ev_offset:+d}")

            # Check motion detection changes
            old_threshold = self.config['motion_detection'].get('threshold', 50)
            new_threshold = self.sensitivity_slider.value()
            if old_threshold != new_threshold:
                # Show as sensitivity (inverted) for user clarity
                changes.append(f"• Motion Sensitivity: {110 - old_threshold} → {110 - new_threshold}")

            old_debounce = self.config['motion_detection'].get('debounce_time', 4)
            new_debounce = self.debounce_slider.value()
            if old_debounce != new_debounce:
                changes.append(f"• Debounce Time: {old_debounce}s → {new_debounce}s")

            # Preview resolution is now fixed at THE_1080_P - no changes possible
            preview_changed = False

            # Update config with current values
            self.config['camera']['focus'] = new_focus
            self.config['camera']['exposure_ms'] = new_exposure
            self.config['camera']['white_balance'] = new_wb
            self.config['camera']['brightness'] = new_brightness
            self.config['camera']['iso_min'] = new_iso_min
            self.config['camera']['iso_max'] = new_iso_max
            self.config['camera']['ev_compensation'] = new_ev_offset
            # Preview resolution is now fixed at THE_1080_P - no need to save
            self.config['motion_detection']['threshold'] = new_threshold
            self.config['motion_detection']['debounce_time'] = new_debounce
            
            # Save current ROI settings if defined (no zoom - fixed 960x540 preview)
            roi_changed = False
            if self.camera_controller.roi_defined:
                roi_rect = self.preview_label.roi_rect
                if not roi_rect.isEmpty():
                    # Save ROI coordinates directly (no conversion needed)
                    x = roi_rect.x()
                    y = roi_rect.y()
                    width = roi_rect.width()
                    height = roi_rect.height()

                    logger.info("=" * 80)
                    logger.info(f"ROI SAVE: x={x}, y={y}, w={width}, h={height} (preview: 960x540)")
                    logger.info("=" * 80)

                    new_roi = {
                        'x': x,
                        'y': y,
                        'width': width,
                        'height': height
                    }
                    old_roi = self.config['motion_detection'].get('current_roi', {})
                    if old_roi != new_roi:
                        changes.append(f"• ROI: Updated to ({x}, {y}, {width}x{height})")
                        roi_changed = True

                    self.config['motion_detection']['current_roi'] = new_roi
            
            # Save to file
            save_start = time.time()
            logger.info("[FILE-IO] Starting config save to config.json")
            with open(CONFIG_PATH, 'w') as f:
                json.dump(self.config, f, indent=4)
            save_time = time.time() - save_start
            logger.info(f"[FILE-IO] Config saved in {save_time:.3f}s")

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
        """Show a visual save confirmation by changing save button to green"""
        try:
            logger.info(f"Save notification - Changes: {changes_count}, Preview changed: {preview_changed}")

            # Change save button to green with checkmark
            self.save_settings_btn.setText("✓ Saved")
            self.save_settings_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    font-weight: bold;
                    border: none;
                    border-radius: 4px;
                    padding: 5px 15px;
                }
            """)
            logger.info(f"Save button turned green - {changes_count} changes saved")

            # Use a timer to reset button after 3 seconds
            if hasattr(self, 'save_btn_timer'):
                self.save_btn_timer.stop()
            else:
                self.save_btn_timer = QTimer()
                self.save_btn_timer.setSingleShot(True)
                self.save_btn_timer.timeout.connect(self.reset_save_button)

            self.save_btn_timer.start(3000)  # Reset after 3 seconds

        except Exception as e:
            logger.error(f"Failed to show save notification: {e}")

    def reset_save_button(self):
        """Reset save button to original state"""
        try:
            self.save_settings_btn.setText("Save")
            self.save_settings_btn.setStyleSheet("")  # Reset to default style
            logger.info("Save button reset to original state")
        except Exception as e:
            logger.error(f"Failed to reset save button: {e}")

    def hide_save_notification(self):
        """Hide the save notification (legacy method)"""
        pass  # No longer used

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
            self.ev_offset_slider.setEnabled(False)
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
            # Exposure slider and EV offset depend on auto exposure state
            auto_exp_on = self.auto_exposure_cb.isChecked()
            self.exposure_slider.setEnabled(not auto_exp_on)
            self.ev_offset_slider.setEnabled(auto_exp_on)
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

