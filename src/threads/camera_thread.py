#!/usr/bin/env python3
"""Camera thread for frame capture and motion detection"""

import time
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal, QMutex

from src.logger import get_logger

logger = get_logger(__name__)


class CameraThread(QThread):
    """Thread for camera operations"""
    frame_ready = pyqtSignal(np.ndarray)
    motion_detected = pyqtSignal(list)
    image_captured = pyqtSignal(str)
    connection_lost = pyqtSignal()
    connection_restored = pyqtSignal()

    def __init__(self, camera_controller):
        super().__init__()
        self.camera_controller = camera_controller
        self.running = False
        self.mutex = QMutex()
        self.connection_error_count = 0
        self.last_reconnect_attempt = 0
        self.reconnect_interval = 5

    def run(self):
        """Main camera loop with USB disconnect handling"""
        self.running = True
        was_connected = True
        last_heartbeat = time.time()
        heartbeat_interval = 30
        last_successful_frame = time.time()
        frame_timeout = 15
        consecutive_frame_failures = 0
        max_frame_failures = 5

        while self.running:
            try:
                current_time = time.time()
                if current_time - last_heartbeat >= heartbeat_interval:
                    logger.info(f"[HEARTBEAT] Camera thread alive - connected: {self.camera_controller.is_connected()}, errors: {self.connection_error_count}, frames_ok: {time.time() - last_successful_frame:.1f}s ago")
                    last_heartbeat = current_time

                time_since_frame = current_time - last_successful_frame
                if time_since_frame > frame_timeout and self.camera_controller.is_connected():
                    logger.error(f"[FREEZE-DETECT] No frames processed for {time_since_frame:.1f}s - forcing camera reconnect to recover")
                    self.camera_controller.disconnect()
                    was_connected = False
                    consecutive_frame_failures = 0
                    continue

                if not self.camera_controller.is_connected():
                    if was_connected:
                        logger.warning("Camera disconnected - attempting reconnection")
                        self.connection_lost.emit()
                        was_connected = False

                    current_time = time.time()
                    if current_time - self.last_reconnect_attempt >= self.reconnect_interval:
                        self.last_reconnect_attempt = current_time

                        if self.camera_controller.reconnect():
                            logger.info("Camera reconnected successfully")
                            self.connection_restored.emit()
                            was_connected = True
                            self.connection_error_count = 0
                            last_successful_frame = time.time()
                            consecutive_frame_failures = 0
                        else:
                            logger.warning(f"Reconnection failed, will retry in {self.reconnect_interval} seconds")

                    self.msleep(1000)
                    continue

                frame = self.camera_controller.get_frame()
                if frame is not None:
                    logger.debug(f"[FRAME] Got frame, shape: {frame.shape}, emitting to GUI")
                    self.frame_ready.emit(frame.copy())
                    logger.debug(f"[FRAME] Frame emitted successfully")
                    self.connection_error_count = 0
                    last_successful_frame = time.time()
                    consecutive_frame_failures = 0

                    if self.camera_controller.process_motion(frame):
                        pass

                    self.msleep(66)  # ~15fps - reduced from 30fps to lower CPU
                else:
                    consecutive_frame_failures += 1
                    if consecutive_frame_failures >= max_frame_failures:
                        logger.warning(f"[FREEZE-DETECT] {consecutive_frame_failures} consecutive frame failures - possible camera stall")

                    self.msleep(200)

                captured_image = self.camera_controller.get_captured_image()
                if captured_image:
                    self.image_captured.emit(captured_image)

            except ConnectionError as e:
                logger.error(f"Camera connection error: {e}")
                self.connection_error_count += 1

                if self.connection_error_count == 1:
                    logger.warning("Camera USB disconnected - will attempt automatic reconnection")
                    self.connection_lost.emit()
                    was_connected = False

                self.msleep(1000)

            except Exception as e:
                logger.error(f"Error in camera thread: {e}")
                self.msleep(100)

    def stop(self):
        """Stop the camera thread"""
        self.running = False
        self.wait()
