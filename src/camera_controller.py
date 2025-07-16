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
        
        # Threading
        self.control_lock = threading.Lock()
        self.last_control_time = 0
        self.control_delay = 0.1
        
        # Callbacks
        self.motion_callback = None
        self.capture_callback = None
        
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
            
            # Set preview size
            cam.setPreviewSize(self.config['preview_width'], self.config['preview_height'])
            cam.setInterleaved(False)
            cam.setColorOrder(dai.ColorCameraProperties.ColorOrder.BGR)
            
            # Set resolution
            resolution_map = {
                '4k': dai.ColorCameraProperties.SensorResolution.THE_4_K,
                '12mp': dai.ColorCameraProperties.SensorResolution.THE_12_MP,
                '1080p': dai.ColorCameraProperties.SensorResolution.THE_1080_P
            }
            cam.setResolution(resolution_map[self.config['resolution']])
            
            if self.config['resolution'] == '12mp':
                cam.setSensorCrop(0.02662721835076809, 0.14473684132099152)
            
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
            
            logger.info(f"Pipeline configured for {self.config['resolution']} resolution")
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
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to camera: {e}")
            return False
    
    def _apply_initial_settings(self):
        """Apply initial camera settings"""
        try:
            # Start with manual exposure to reset state
            ctrl = dai.CameraControl()
            ctrl.setManualExposure(20000, 800)
            self.control_queue.send(ctrl)
            time.sleep(0.1)
            
            # Enable auto exposure
            ctrl = dai.CameraControl()
            ctrl.setAutoExposureEnable()
            ctrl.setAutoExposureLock(False)
            ctrl.setManualWhiteBalance(self.config['white_balance'])
            ctrl.setAutoFocusMode(dai.CameraControl.AutoFocusMode.OFF)
            ctrl.setManualFocus(self.config['focus'])
            
            # Set image quality settings
            ctrl.setSharpness(self.config['sharpness'])
            ctrl.setSaturation(self.config['saturation'])
            ctrl.setContrast(self.config['contrast'])
            ctrl.setBrightness(self.config['brightness'])
            ctrl.setLumaDenoise(self.config['luma_denoise'])
            ctrl.setChromaDenoise(self.config['chroma_denoise'])
            
            self.control_queue.send(ctrl)
            
            logger.info("Initial camera settings applied")
            
        except Exception as e:
            logger.error(f"Failed to apply initial settings: {e}")
    
    def get_frame(self):
        """Get current preview frame"""
        try:
            if not self.preview_queue:
                return None
                
            packet = self.preview_queue.tryGet()
            if packet is not None:
                return packet.getCvFrame()
            return None
            
        except Exception as e:
            logger.error(f"Error getting frame: {e}")
            return None
    
    def process_motion(self, frame):
        """Process motion detection on frame"""
        if not self.roi_defined:
            return False
        
        try:
            # Extract ROI
            x1, y1 = self.roi_start_pt
            x2, y2 = self.roi_end_pt
            
            # Ensure coordinates are within bounds
            x1 = max(0, min(x1, self.config['preview_width'] - 1))
            y1 = max(0, min(y1, self.config['preview_height'] - 1))
            x2 = max(0, min(x2, self.config['preview_width'] - 1))
            y2 = max(0, min(y2, self.config['preview_height'] - 1))
            
            roi_frame = frame[y1:y2, x1:x2]
            
            if roi_frame.size == 0:
                return False
            
            # Detect motion
            motion_detected, contours = self.motion_detector.detect(roi_frame)
            
            if motion_detected:
                current_time = time.time()
                if current_time - self.last_capture_time >= self.debounce_time:
                    logger.info("Motion detected in ROI - triggering capture")
                    self.capture_still()
                    self.last_capture_time = current_time
                    
                    # Call motion callback if set
                    if self.motion_callback:
                        self.motion_callback(contours)
                    
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error processing motion: {e}")
            return False
    
    def capture_still(self):
        """Capture still image"""
        try:
            if not self.control_queue:
                return False
                
            ctrl = dai.CameraControl()
            ctrl.setCaptureStill(True)
            self.control_queue.send(ctrl)
            logger.info("Still capture command sent")
            return True
            
        except Exception as e:
            logger.error(f"Error capturing still: {e}")
            return False
    
    def get_captured_image(self):
        """Get captured still image"""
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
                    # Save image
                    timestamp = int(time.time())
                    filename = os.path.join(
                        self.storage_config['save_dir'], 
                        f"motion_{timestamp}.jpeg"
                    )
                    
                    # Ensure directory exists
                    os.makedirs(self.storage_config['save_dir'], exist_ok=True)
                    
                    if cv2.imwrite(filename, decoded_frame):
                        logger.info(f"Saved captured image: {filename}")
                        
                        # Call capture callback if set
                        if self.capture_callback:
                            self.capture_callback(filename)
                        
                        return filename
                    else:
                        logger.error(f"Failed to save image: {filename}")
                
            return None
            
        except Exception as e:
            logger.error(f"Error getting captured image: {e}")
            return None
    
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
        try:
            self.ae_start_pt = start_pt
            self.ae_end_pt = end_pt
            self.ae_defined = True
            
            # Apply to camera
            frame = self.get_frame()
            if frame is not None:
                frame_height, frame_width = frame.shape[:2]
                
                # Scale coordinates
                scale_x = frame_width / self.config['preview_width']
                scale_y = frame_height / self.config['preview_height']
                
                scaled_x = int(start_pt[0] * scale_x)
                scaled_y = int(start_pt[1] * scale_y)
                scaled_width = int((end_pt[0] - start_pt[0]) * scale_x)
                scaled_height = int((end_pt[1] - start_pt[1]) * scale_y)
                
                ctrl = dai.CameraControl()
                ctrl.setAutoExposureRegion(scaled_x, scaled_y, scaled_width, scaled_height)
                self.control_queue.send(ctrl)
                
                logger.info(f"Auto exposure region set: {start_pt} to {end_pt}")
                
        except Exception as e:
            logger.error(f"Error setting auto exposure region: {e}")
    
    def update_camera_setting(self, setting, value):
        """Update camera setting"""
        try:
            with self.control_lock:
                current_time = time.time()
                if current_time - self.last_control_time < self.control_delay:
                    return
                self.last_control_time = current_time
                
                ctrl = dai.CameraControl()
                
                if setting == 'focus':
                    ctrl.setManualFocus(value)
                elif setting == 'exposure':
                    ctrl.setManualExposure(value * 1000, 800)
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
                        ctrl.setAutoExposureEnable()
                    else:
                        ctrl.setManualExposure(self.config['exposure_ms'] * 1000, 800)
                
                self.control_queue.send(ctrl)
                logger.info(f"Camera setting updated: {setting} = {value}")
                
        except Exception as e:
            logger.error(f"Error updating camera setting {setting}: {e}")
    
    def set_callbacks(self, motion_callback=None, capture_callback=None):
        """Set callbacks for motion detection and capture events"""
        self.motion_callback = motion_callback
        self.capture_callback = capture_callback
    
    def disconnect(self):
        """Disconnect from camera"""
        try:
            if self.device:
                self.device.close()
                self.device = None
                logger.info("Camera disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting camera: {e}")
    
    def __del__(self):
        """Cleanup on destruction"""
        self.disconnect()