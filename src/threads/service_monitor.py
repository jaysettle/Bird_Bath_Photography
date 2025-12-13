#!/usr/bin/env python3
"""Service monitor thread for checking systemd service status"""

import subprocess
from PyQt6.QtCore import QThread, pyqtSignal

from src.logger import get_logger

logger = get_logger(__name__)


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

                if self.running:
                    self.msleep(5000)

            except Exception as e:
                logger.error(f"Error in service monitor: {e}")
                self.msleep(1000)

    def stop(self):
        """Stop the service monitor"""
        self.running = False
        self.wait()
