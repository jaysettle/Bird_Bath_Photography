#!/usr/bin/env python3
"""Drive stats monitor thread for Google Drive folder statistics"""

from PyQt6.QtCore import QThread, pyqtSignal

from src.logger import get_logger

logger = get_logger(__name__)


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
                        self.drive_stats_updated.emit({
                            'file_count': 0,
                            'total_size': 0,
                            'latest_file': None,
                            'latest_upload_time': None
                        })
                else:
                    self.drive_stats_updated.emit({
                        'file_count': 0,
                        'total_size': 0,
                        'latest_file': None,
                        'latest_upload_time': None
                    })

                if self.running:
                    self.msleep(30000)

            except Exception as e:
                logger.error(f"Error in Drive stats monitor: {e}")
                self.msleep(5000)

    def stop(self):
        """Stop the Drive stats monitor"""
        self.running = False
        self.wait()
