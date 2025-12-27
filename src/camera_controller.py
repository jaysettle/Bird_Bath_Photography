#!/usr/bin/env python3
"""
Camera Controller for OAK-D Camera with DepthAI
"""

import cv2
import depthai as dai
import numpy as np
import time
import threading
from queue import Queue, Empty
from datetime import datetime
import os
import json
from .logger import get_logger

logger = get_logger(__name__)

class MotionDetector:
    """Motion detection using frame differencing"""
    
    def __init__(self, threshold=50, min_area=500):
        self.threshold = threshold
        self.min_area = min_area
        self.prev_gray = None
        logger.info(f"Motion detector initialized - threshold: {threshold}, min_area: {min_area}")
        
    def detect(self, frame):
        """Detect motion in the provided frame"""
        motion_detected = False
        contours_list = []
        
        try:
            if frame is None or frame.size == 0:
                return False, []
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)
            
            if self.prev_gray is None:
                self.prev_gray = gray
                return False, []
            
            # Calculate frame difference
            frame_delta = cv2.absdiff(self.prev_gray, gray)
            thresh = cv2.threshold(frame_delta, self.threshold, 255, cv2.THRESH_BINARY)[1]
            thresh = cv2.dilate(thresh, None, iterations=2)
            
            # Find contours
            contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            significant_contours = []
            for contour in contours:
                if cv2.contourArea(contour) >= self.min_area:
                    motion_detected = True
                    significant_contours.append(contour)
            
            self.prev_gray = gray
            return motion_detected, significant_contours
            
        except Exception as e:
            logger.error(f"Error in motion detection: {e}")
            self.prev_gray = None
            return False, []
    
    def update_settings(self, threshold=None, min_area=None):
        """Update motion detection settings"""
        if threshold is not None:
            self.threshold = threshold
            logger.info(f"Motion threshold updated to: {threshold}")
        if min_area is not None:
            self.min_area = min_area
            logger.info(f"Motion min_area updated to: {min_area}")
    
    def reset(self):
        """Reset motion detector background"""
        self.prev_gray = None
        logger.info("Motion detector background reset")

class CameraController:
    """Main camera controller for OAK-D with DepthAI"""
    
    def __init__(self, config):
        self.config = config['camera']
        self.motion_config = config['motion_detection']
        self.storage_config = config['storage']

        # Camera state
        self.device = None
        self.pipeline = None
        self.preview_queue = None
        self.still_queue = None
        self.control_queue = None

        # Preview resolution (can be changed dynamically)
        self.preview_resolution = 'THE_1080_P'  # Fixed preview resolution (1920x1080)

        # Motion detection
        self.motion_detector = MotionDetector(
            threshold=self.motion_config['threshold'],
            min_area=self.motion_config['min_area']
        )
        
        # ROI settings
        self.roi_defined = False
        self.roi_start_pt = (-1, -1)
        self.roi_end_pt = (-1, -1)
        
        # Auto exposure region
        self.ae_defined = False
        self.ae_start_pt = (-1, -1)
        self.ae_end_pt = (-1, -1)
        

        # Capture control
        self.last_capture_time = 0
        self.debounce_time = self.motion_config['debounce_time']
        logger.info(f"Debounce time initialized: {self.debounce_time}s")

        # Threading
        self.control_lock = threading.Lock()
        self.last_control_time = 0
        self.control_delay = 0.1
        self.connection_error_count = 0
        self.reconnect_attempts = 0
        self.is_reconnecting = False

        # Callbacks
        self.motion_callback = None
        self.capture_callback = None

        # Weather-based pause
        self.motion_paused = False
        self.pause_reason = ""

        logger.info("Camera controller initialized")
    
    def setup_pipeline(self):
        """Setup DepthAI pipeline"""
        try:
            self.pipeline = dai.Pipeline()
            
            # Color camera
            cam = self.pipeline.create(dai.node.ColorCamera)
            
            # Set camera socket
            socket_map = {
                'rgb': dai.CameraBoardSocket.CAM_A,
                'left': dai.CameraBoardSocket.CAM_B,
                'right': dai.CameraBoardSocket.CAM_C
            }
            cam.setBoardSocket(socket_map[self.config['socket']])
            
            # Set orientation
            if self.config['orientation'] == 'rotate_180':
                cam.setImageOrientation(dai.CameraImageOrientation.ROTATE_180_DEG)

            # Set preview resolution
            preview_res_map = {
                'THE_1211x1013': (1211, 1013),
                'THE_1250x1036': (1250, 1036),
                'THE_1080_P': (1920, 1080),
                'THE_720_P': (1280, 720),
                'THE_480_P': (640, 480),
                'THE_400_P': (640, 400),
                'THE_300_P': (640, 300)
            }
            preview_width, preview_height = preview_res_map.get(self.preview_resolution, (1211, 1013))

            logger.info(f"Setting preview resolution: {self.preview_resolution} -> {preview_width}x{preview_height}")
            cam.setPreviewSize(preview_width, preview_height)
            cam.setInterleaved(False)
            cam.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
            
            # Set resolution - only include supported resolutions
            resolution_map = {
                '4k': dai.ColorCameraProperties.SensorResolution.THE_4_K,
                '12mp': dai.ColorCameraProperties.SensorResolution.THE_12_MP,
                '13mp': dai.ColorCameraProperties.SensorResolution.THE_13_MP,
                '1080p': dai.ColorCameraProperties.SensorResolution.THE_1080_P,
                '720p': dai.ColorCameraProperties.SensorResolution.THE_720_P,
                '5mp': dai.ColorCameraProperties.SensorResolution.THE_5_MP
            }
            # Default to 4k if resolution not found
            resolution = resolution_map.get(self.config['resolution'], dai.ColorCameraProperties.SensorResolution.THE_4_K)
            cam.setResolution(resolution)
            
            if self.config['resolution'] == '12mp':
                # cam.setSensorCrop(0.02662721835076809, 0.14473684132099152)  # Disabled to see full sensor
                pass  # Keep the if block valid
            
            # Still encoder
            still_encoder = self.pipeline.create(dai.node.VideoEncoder)
            still_encoder.setDefaultProfilePreset(30, dai.VideoEncoderProperties.Profile.MJPEG)
            still_encoder.setQuality(98)
            still_encoder.setNumFramesPool(2)
            still_encoder.setMaxOutputFrameSize(18678784)
            cam.still.link(still_encoder.input)
            
            # Outputs
            preview_out = self.pipeline.create(dai.node.XLinkOut)
            preview_out.setStreamName("preview")
            cam.preview.link(preview_out.input)
            
            still_out = self.pipeline.create(dai.node.XLinkOut)
            still_out.setStreamName("still")
            still_encoder.bitstream.link(still_out.input)
            
            # Control input
            control_in = self.pipeline.create(dai.node.XLinkIn)
            control_in.setStreamName("control")
            control_in.out.link(cam.inputControl)
            
            logger.info(f"Pipeline configured for {self.config['resolution']} capture resolution, {preview_width}x{preview_height} preview")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup pipeline: {e}")
            return False
    
    def connect(self):
        """Connect to camera device"""
        try:
            if not self.setup_pipeline():
                return False
            
            self.device = dai.Device(self.pipeline)
            
            # Get queues
            self.preview_queue = self.device.getOutputQueue("preview", maxSize=4, blocking=False)
            self.still_queue = self.device.getOutputQueue("still", maxSize=1, blocking=False)
            self.control_queue = self.device.getInputQueue("control")
            
            # Log device info
            logger.info(f"Connected to device: {self.device.getDeviceName()}")
            logger.info(f"Connected cameras: {self.device.getConnectedCameraFeatures()}")
            logger.info(f"USB speed: {self.device.getUsbSpeed().name}")
            
            # Initialize camera settings
            self._apply_initial_settings()
            self._post_reconnect_setup()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to camera: {e}")
            return False
    
    def _apply_initial_settings(self):
        """Apply initial camera settings with X_LINK error handling"""
        try:
            # Start with manual exposure to reset state
            ctrl = dai.CameraControl()
            initial_iso = self.config.get('iso_max', 800)
            ctrl.setManualExposure(20000, initial_iso)
            self.control_queue.send(ctrl)
            time.sleep(0.1)

            # Enable auto exposure
            ctrl = dai.CameraControl()
            ctrl.setAutoExposureEnable()
            ctrl.setAutoExposureLock(False)
            ctrl.setManualWhiteBalance(self.config['white_balance'])
            ctrl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
            ctrl.setManualFocus(self.config['focus'])

            # Set EV compensation if configured
            ev_compensation = self.config.get('ev_compensation', 0)
            if ev_compensation != 0:
                ctrl.setAutoExposureCompensation(ev_compensation)
                logger.info(f"[EV] Applied EV compensation from config: {ev_compensation:+d}")

            # Set image quality settings
            ctrl.setSharpness(self.config['sharpness'])
            ctrl.setSaturation(self.config['saturation'])
            ctrl.setContrast(self.config['contrast'])
            ctrl.setBrightness(self.config['brightness'])
            ctrl.setLumaDenoise(self.config['luma_denoise'])
            ctrl.setChromaDenoise(self.config['chroma_denoise'])

            self.control_queue.send(ctrl)

            logger.info("Initial camera settings applied")

        except RuntimeError as e:
            # X_LINK errors typically raise RuntimeError
            error_msg = str(e).lower()
            if ('x_link' in error_msg or 'xlink' in error_msg or
                'x_link_error' in error_msg or 'connection' in error_msg or
                'usb' in error_msg or 'device' in error_msg):
                logger.error(f"X_LINK_ERROR in _apply_initial_settings (USB disconnect): {e}")
                self._mark_disconnected()
                raise ConnectionError(f"Camera USB disconnected: {e}")
            else:
                logger.error(f"Runtime error applying initial settings: {e}")
        except Exception as e:
            logger.error(f"Failed to apply initial settings: {e}")
    
    def get_frame(self):
        """Get current preview frame with X_LINK error handling"""
        try:
            if not self.preview_queue:
                return None

            packet = self.preview_queue.tryGet()
            if packet is not None:
                return packet.getCvFrame()
            return None

        except RuntimeError as e:
            # X_LINK errors typically raise RuntimeError
            error_msg = str(e).lower()
            if ('x_link' in error_msg or 'xlink' in error_msg or
                'x_link_error' in error_msg or 'connection' in error_msg or
                'usb' in error_msg or 'device' in error_msg):
                logger.error(f"X_LINK_ERROR detected (USB disconnect): {e}")
                self._mark_disconnected()
                raise ConnectionError(f"Camera USB disconnected: {e}")
            else:
                logger.error(f"Runtime error getting frame: {e}")
                return None
        except Exception as e:
            logger.error(f"Error getting frame: {e}")
            return None
    
    def process_motion(self, frame):
        """Process motion detection on frame"""
        if self.motion_paused:
            logger.debug(f"Motion detection paused: {self.pause_reason}")
            return False

        if not self.roi_defined:
            logger.debug("ROI not defined - no motion detection")
            return False

        try:
            # Extract ROI
            x1, y1 = self.roi_start_pt
            x2, y2 = self.roi_end_pt

            # Get actual current preview dimensions
            preview_res_map = {
                'THE_1211x1013': (1211, 1013),
                'THE_1250x1036': (1250, 1036),
                'THE_1080_P': (1920, 1080),
                'THE_720_P': (1280, 720),
                'THE_480_P': (640, 480),
                'THE_400_P': (640, 400),
                'THE_300_P': (640, 300)
            }
            current_width, current_height = preview_res_map.get(self.preview_resolution, (1211, 1013))

            # Get actual frame dimensions
            actual_height, actual_width = frame.shape[:2]

            logger.debug(f"MOTION DEBUG: ROI=({x1},{y1})-({x2},{y2}), Expected={current_width}x{current_height}, Actual Frame={actual_width}x{actual_height}, Resolution={self.preview_resolution}")

            # Check if frame dimensions don't match expected preview resolution
            if actual_width != current_width or actual_height != current_height:
                logger.warning(f"FRAME SIZE MISMATCH! Expected {current_width}x{current_height} but got {actual_width}x{actual_height}")

                # Scale ROI coordinates to match actual frame size
                scale_x = actual_width / current_width
                scale_y = actual_height / current_height

                x1_scaled = int(x1 * scale_x)
                y1_scaled = int(y1 * scale_y)
                x2_scaled = int(x2 * scale_x)
                y2_scaled = int(y2 * scale_y)

                logger.info(f"SCALING ROI: Original=({x1},{y1})-({x2},{y2}) -> Scaled=({x1_scaled},{y1_scaled})-({x2_scaled},{y2_scaled})")

                x1, y1, x2, y2 = x1_scaled, y1_scaled, x2_scaled, y2_scaled

            # Ensure coordinates are within bounds of actual frame
            x1 = max(0, min(x1, actual_width - 1))
            y1 = max(0, min(y1, actual_height - 1))
            x2 = max(0, min(x2, actual_width - 1))
            y2 = max(0, min(y2, actual_height - 1))

            logger.debug(f"ROI coordinates after bounds check: ({x1},{y1}) to ({x2},{y2}) - frame size: {frame.shape}")

            # Ensure x2 > x1 and y2 > y1
            if x2 <= x1 or y2 <= y1:
                logger.warning(f"Invalid ROI dimensions: ({x1},{y1}) to ({x2},{y2})")
                return False

            roi_frame = frame[y1:y2, x1:x2]

            if roi_frame.size == 0:
                logger.warning(f"ROI frame is empty: ({x1},{y1}) to ({x2},{y2})")
                return False

            logger.debug(f"ROI frame size: {roi_frame.shape}")

            # Detect motion
            motion_detected, contours = self.motion_detector.detect(roi_frame)

            if motion_detected:
                # Log contour details
                contour_info = []
                for i, contour in enumerate(contours):
                    area = cv2.contourArea(contour)
                    x_cont, y_cont, w_cont, h_cont = cv2.boundingRect(contour)
                    # Convert relative ROI coordinates back to absolute frame coordinates
                    abs_x = x1 + x_cont
                    abs_y = y1 + y_cont
                    contour_info.append(f"Contour{i}: area={area:.0f}, roi_pos=({x_cont},{y_cont},{w_cont}x{h_cont}), abs_pos=({abs_x},{abs_y},{w_cont}x{h_cont})")

                logger.info(f"Motion contours detected: {len(contours)} total. Details: {'; '.join(contour_info)}")

                current_time = time.time()
                if current_time - self.last_capture_time >= self.debounce_time:
                    logger.info(f"Motion detected in ROI ({x1},{y1})-({x2},{y2}) - triggering capture")
                    try:
                        self.capture_still()
                        self.last_capture_time = current_time

                        # Call motion callback if set
                        if self.motion_callback:
                            self.motion_callback(contours)

                        return True
                    except ConnectionError as e:
                        # Re-raise ConnectionError to be handled by camera thread
                        logger.error(f"Connection error during motion capture: {e}")
                        raise
                else:
                    logger.debug(f"Motion detected but debounce active: {current_time - self.last_capture_time:.1f}s < {self.debounce_time}s")

            return False

        except ConnectionError:
            # Re-raise ConnectionError to be handled by camera thread
            raise
        except Exception as e:
            logger.error(f"Error processing motion: {e}")
            return False
    
    def capture_still(self):
        """Capture still image with X_LINK error handling"""
        try:
            if not self.control_queue:
                return False

            ctrl = dai.CameraControl()
            ctrl.setCaptureStill(True)
            self.control_queue.send(ctrl)
            logger.info("Still capture command sent")
            return True

        except RuntimeError as e:
            # X_LINK errors typically raise RuntimeError
            error_msg = str(e).lower()
            if ('x_link' in error_msg or 'xlink' in error_msg or
                'x_link_error' in error_msg or 'connection' in error_msg or
                'usb' in error_msg or 'device' in error_msg):
                logger.error(f"X_LINK_ERROR in capture_still (USB disconnect): {e}")
                self._mark_disconnected()
                raise ConnectionError(f"Camera USB disconnected: {e}")
            else:
                logger.error(f"Runtime error capturing still: {e}")
                return False
        except Exception as e:
            logger.error(f"Error capturing still: {e}")
            return False
    
    def get_captured_image(self):
        """Get captured still image with X_LINK error handling"""
        try:
            if not self.still_queue:
                return None

            packet = self.still_queue.tryGet()
            if packet is not None:
                still_data = packet.getData()
                decoded_frame = cv2.imdecode(
                    np.frombuffer(still_data, dtype=np.uint8),
                    cv2.IMREAD_COLOR
                )

                if decoded_frame is not None:
                    # Save image with date-based organization
                    timestamp = int(time.time())
                    current_date = datetime.now().strftime('%Y-%m-%d')
                    date_dir = os.path.join(self.storage_config['save_dir'], current_date)
                    filename = os.path.join(
                        date_dir,
                        f"motion_{timestamp}.jpeg"
                    )

                    # Ensure date directory exists
                    os.makedirs(date_dir, exist_ok=True)

                    # Add focus point overlay
                    overlay_frame = self.add_focus_overlay(decoded_frame)

                    if cv2.imwrite(filename, overlay_frame):
                        logger.info(f"Saved captured image: {filename}")

                        # Call capture callback if set
                        if self.capture_callback:
                            self.capture_callback(filename)

                        return filename
                    else:
                        logger.error(f"Failed to save image: {filename}")

            return None

        except RuntimeError as e:
            # X_LINK errors typically raise RuntimeError
            error_msg = str(e).lower()
            if ('x_link' in error_msg or 'xlink' in error_msg or
                'x_link_error' in error_msg or 'connection' in error_msg or
                'usb' in error_msg or 'device' in error_msg):
                logger.error(f"X_LINK_ERROR in get_captured_image (USB disconnect): {e}")
                self._mark_disconnected()
                raise ConnectionError(f"Camera USB disconnected: {e}")
            else:
                logger.error(f"Runtime error getting captured image: {e}")
                return None
        except Exception as e:
            logger.error(f"Error getting captured image: {e}")
            return None
    
    def add_focus_overlay(self, frame):
        """Add focus point indicator, datestamp, and depth info to frame"""
        try:
            overlay = frame.copy()
            height, width = overlay.shape[:2]
            
            # Add datestamp at the very top left
            from datetime import datetime
            current_time = datetime.now()
            datestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(overlay, datestamp, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)  # White text
            
            # Focus crosshair and rectangle removed per user request
            
            # Add focus value text (moved down to make room for datestamp)
            focus_text = f"Focus: {self.config.get('focus', 'Unknown')}"
            cv2.putText(overlay, focus_text, (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # Add exposure value
            exposure_ms = self.config.get('exposure_ms', 'Unknown')
            if exposure_ms != 'Unknown':
                exposure_text = f"Exposure: {exposure_ms:.1f}ms"
            else:
                exposure_text = f"Exposure: {exposure_ms}"
            cv2.putText(overlay, exposure_text, (10, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # Add ISO value
            iso_value = self.config.get('iso_max', 'Unknown')
            iso_text = f"ISO: {iso_value}"
            cv2.putText(overlay, iso_text, (10, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # Add hyperfocal distance suggestion
            # Hyperfocal and DOF text removed per user request

            return overlay
            
        except Exception as e:
            logger.error(f"Error adding focus overlay: {e}")
            return frame
    
    def get_device_info(self):
        """Get camera device information"""
        if not self.device:
            return {
                'name': 'Disconnected',
                'usb_speed': 'Not Connected',
                'sensor_resolution': 'Unknown',
                'connected': False
            }
        
        try:
            # Get sensor resolution string - only supported resolutions
            resolution_display = {
                '4k': '4056×3040',
                '12mp': '4056×3040', 
                '13mp': '4208×3120',
                '1080p': '1920×1080',
                '720p': '1280×720',
                '5mp': '2592×1944'
            }
            
            return {
                'name': self.device.getDeviceName() or 'OAK Camera',
                'usb_speed': self.device.getUsbSpeed().name,
                'sensor_resolution': resolution_display.get(self.config['resolution'], '4056x3040'),
                'connected': True
            }
        except Exception as e:
            logger.error(f"Error getting device info: {e}")
            return {
                'name': 'Error',
                'usb_speed': 'Unknown',
                'sensor_resolution': 'Unknown',
                'connected': False
            }
    
    def set_roi(self, start_pt, end_pt):
        """Set motion detection ROI"""
        self.roi_start_pt = start_pt
        self.roi_end_pt = end_pt
        self.roi_defined = True
        self.motion_detector.reset()
        logger.info(f"ROI set: {start_pt} to {end_pt}")
    
    def clear_roi(self):
        """Clear motion detection ROI"""
        self.roi_defined = False
        self.roi_start_pt = (-1, -1)
        self.roi_end_pt = (-1, -1)
        self.motion_detector.reset()
        logger.info("ROI cleared")
    
    
    def set_auto_exposure_region(self, start_pt, end_pt):
        """Set auto exposure region"""
        self.ae_start_pt = start_pt
        self.ae_end_pt = end_pt
        self.ae_defined = True
        self._apply_auto_exposure_region()

    def _apply_auto_exposure_region(self):
        """Apply stored auto exposure region to the device with X_LINK error handling"""
        if not self.ae_defined or not self.control_queue:
            return

        try:
            preview_res_map = {
                'THE_1211x1013': (1211, 1013),
                'THE_1250x1036': (1250, 1036),
                'THE_1080_P': (1920, 1080),
                'THE_720_P': (1280, 720),
                'THE_480_P': (640, 480),
                'THE_400_P': (640, 400),
                'THE_300_P': (640, 300)
            }

            frame_width, frame_height = preview_res_map.get(
                self.preview_resolution,
                (1211, 1013)
            )

            ui_width = self.config.get('preview_width', 600)
            ui_height = self.config.get('preview_height', 400)

            scale_x = frame_width / max(1, ui_width)
            scale_y = frame_height / max(1, ui_height)

            start_pt = self.ae_start_pt
            end_pt = self.ae_end_pt

            scaled_x = int(start_pt[0] * scale_x)
            scaled_y = int(start_pt[1] * scale_y)
            scaled_width = int(max(1, (end_pt[0] - start_pt[0]) * scale_x))
            scaled_height = int(max(1, (end_pt[1] - start_pt[1]) * scale_y))

            ctrl = dai.CameraControl()
            ctrl.setAutoExposureRegion(scaled_x, scaled_y, scaled_width, scaled_height)
            self.control_queue.send(ctrl)

            logger.info(
                "Auto exposure region applied: UI(%s to %s) -> Device(%s, %s, %s x %s)",
                start_pt, end_pt, scaled_x, scaled_y, scaled_width, scaled_height
            )

        except RuntimeError as e:
            # X_LINK errors typically raise RuntimeError
            error_msg = str(e).lower()
            if ('x_link' in error_msg or 'xlink' in error_msg or
                'x_link_error' in error_msg or 'connection' in error_msg or
                'usb' in error_msg or 'device' in error_msg):
                logger.error(f"X_LINK_ERROR in _apply_auto_exposure_region (USB disconnect): {e}")
                self._mark_disconnected()
                raise ConnectionError(f"Camera USB disconnected: {e}")
            else:
                logger.error(f"Runtime error applying auto exposure region: {e}")
        except Exception as e:
            logger.error(f"Error applying auto exposure region: {e}")

    def _post_reconnect_setup(self):
        """Restore runtime state after a successful reconnect"""
        try:
            # Reapply auto exposure region if one was previously defined
            self._apply_auto_exposure_region()

            # Reset motion detector background to avoid stale frames
            if self.roi_defined:
                self.motion_detector.reset()

            logger.info("Post-reconnect camera state restored")

        except Exception as e:
            logger.error(f"Error during post-reconnect setup: {e}")
    
    def update_camera_setting(self, setting, value):
        """Update camera setting with X_LINK error handling"""
        try:
            # Check if camera is connected
            if not self.control_queue:
                logger.debug(f"Camera not connected yet, skipping {setting} update")
                return

            with self.control_lock:
                current_time = time.time()
                if current_time - self.last_control_time < self.control_delay:
                    return
                self.last_control_time = current_time

                ctrl = dai.CameraControl()

                if setting == 'focus':
                    ctrl.setManualFocus(value)
                    # Update config so overlay shows correct value
                    self.config['focus'] = value
                elif setting == 'exposure':
                    # Use ISO from config (default to 800 if not set)
                    iso = self.config.get('iso_max', 800)
                    exposure_us = int(value * 1000)
                    logger.info(f"[EXPOSURE] Setting manual exposure: {value}ms ({exposure_us}us), ISO={iso}")
                    ctrl.setManualExposure(exposure_us, iso)
                    # Update config so overlay shows correct value
                    self.config['exposure_ms'] = value
                    logger.info(f"[EXPOSURE] Config updated: exposure_ms={value}")
                elif setting == 'iso':
                    # ISO is set as part of exposure, so update exposure with new ISO
                    exposure_us = self.config.get('exposure_ms', 20) * 1000
                    ctrl.setManualExposure(exposure_us, value)
                    # Update config so overlay shows correct value
                    self.config['iso_max'] = value
                elif setting == 'white_balance':
                    ctrl.setManualWhiteBalance(value)
                elif setting == 'sharpness':
                    ctrl.setSharpness(value)
                elif setting == 'saturation':
                    ctrl.setSaturation(value)
                elif setting == 'contrast':
                    ctrl.setContrast(value)
                elif setting == 'brightness':
                    ctrl.setBrightness(value)
                elif setting == 'auto_exposure':
                    if value:
                        logger.info(f"[EXPOSURE] Enabling auto exposure")
                        ctrl.setAutoExposureEnable()
                    else:
                        # Use ISO from config when disabling auto exposure
                        iso = self.config.get('iso_max', 800)
                        exposure_ms = self.config.get('exposure_ms', 20)
                        exposure_us = int(exposure_ms * 1000)
                        logger.info(f"[EXPOSURE] Disabling auto exposure - setting manual: {exposure_ms}ms ({exposure_us}us), ISO={iso}")
                        ctrl.setManualExposure(exposure_us, iso)
                elif setting == 'ev_compensation':
                    # Exposure compensation for auto exposure mode (-9 to +9)
                    logger.info(f"[EXPOSURE] Setting EV compensation: {value}")
                    ctrl.setAutoExposureCompensation(value)
                    self.config['ev_compensation'] = value

                self.control_queue.send(ctrl)
                logger.info(f"Camera setting updated: {setting} = {value}")

        except RuntimeError as e:
            # X_LINK errors typically raise RuntimeError
            error_msg = str(e).lower()
            if ('x_link' in error_msg or 'xlink' in error_msg or
                'x_link_error' in error_msg or 'connection' in error_msg or
                'usb' in error_msg or 'device' in error_msg):
                logger.error(f"X_LINK_ERROR in update_camera_setting (USB disconnect): {e}")
                self._mark_disconnected()
                raise ConnectionError(f"Camera USB disconnected: {e}")
            else:
                logger.error(f"Runtime error updating camera setting {setting}: {e}")
        except Exception as e:
            logger.error(f"Error updating camera setting {setting}: {e}")
    
    def set_callbacks(self, motion_callback=None, capture_callback=None):
        """Set callbacks for motion detection and capture events"""
        self.motion_callback = motion_callback
        self.capture_callback = capture_callback
    
    def is_connected(self):
        """Check if camera is connected"""
        return self.device is not None and self.preview_queue is not None

    def reconnect(self, max_attempts=3, delay=2):
        """Attempt to reconnect to the camera"""
        if self.is_reconnecting:
            logger.debug("Reconnection already in progress; skipping additional request")
            return False

        self.is_reconnecting = True

        try:
            logger.info(f"Attempting to reconnect camera (max {max_attempts} attempts)...")

            # First disconnect cleanly
            self.disconnect()

            for attempt in range(1, max_attempts + 1):
                logger.info(f"Reconnection attempt {attempt}/{max_attempts}")

                try:
                    # Wait before reconnecting to avoid thrashing USB bus
                    time.sleep(delay)

                    # Try to connect
                    if self.connect():
                        logger.info("Camera reconnected successfully!")
                        self.reconnect_attempts = 0
                        self._post_reconnect_setup()
                        return True

                except Exception as e:
                    logger.error(f"Reconnection attempt {attempt} failed: {e}")

            self.reconnect_attempts += 1
            logger.error(f"Failed to reconnect after {max_attempts} attempts (failures: {self.reconnect_attempts})")
            return False

        finally:
            self.is_reconnecting = False

    def disconnect(self):
        """Disconnect from camera"""
        try:
            if self.device:
                self.device.close()
                logger.info("Camera disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting camera: {e}")

        self._mark_disconnected()

    def _mark_disconnected(self):
        """Mark controller resources as disconnected"""
        self.device = None
        self.preview_queue = None
        self.still_queue = None
        self.control_queue = None
    
    def __del__(self):
        """Cleanup on destruction"""
        self.disconnect()
