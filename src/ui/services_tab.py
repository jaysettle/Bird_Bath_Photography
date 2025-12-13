#!/usr/bin/env python3
"""Services monitoring and control tab"""

import os
import time
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                            QGroupBox, QLabel, QPushButton, QMessageBox, QSplitter)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices

from src.logger import get_logger
from src.threads import DriveStatsMonitor
from src.email_handler import EmailHandler

logger = get_logger(__name__)


class ServicesTab(QWidget):
    """Services monitoring and control tab"""

    def __init__(self, email_handler, uploader, config=None, bird_identifier=None):
        super().__init__()
        self.email_handler = email_handler
        self.uploader = uploader
        self.config = config or {}
        self.bird_identifier = bird_identifier

        self.drive_stats_monitor = DriveStatsMonitor(uploader)
        self.drive_stats_monitor.drive_stats_updated.connect(self.update_drive_stats)

        self.setup_ui()

        self.drive_stats_monitor.start()

        self.update_openai_count()
        self.openai_timer = QTimer()
        self.openai_timer.timeout.connect(self.update_openai_count)
        self.openai_timer.start(5000)

        self.app_start_time = datetime.now()

        self.uptime_timer = QTimer()
        self.uptime_timer.timeout.connect(self.update_uptime)
        self.uptime_timer.start(5000)
        self.update_uptime()

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

        # Mobile Web Interface
        mobile_group = QGroupBox("Mobile Web Interface")
        mobile_layout = QVBoxLayout()

        self.mobile_url_label = QLabel("Starting web server...")
        self.mobile_url_label.setOpenExternalLinks(True)
        self.mobile_url_label.setStyleSheet("font-size: 14px; padding: 10px;")
        mobile_layout.addWidget(self.mobile_url_label)

        mobile_group.setLayout(mobile_layout)
        main_layout.addWidget(mobile_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # Email service
        email_group = QGroupBox("Email Service")
        email_layout = QGridLayout()

        email_layout.addWidget(QLabel("Status:"), 0, 0)
        self.email_status = QLabel("Running")
        email_layout.addWidget(self.email_status, 0, 1)

        email_layout.addWidget(QLabel("Queue:"), 1, 0)
        self.email_queue = QLabel("0")
        email_layout.addWidget(self.email_queue, 1, 1)

        self.test_email_btn = QPushButton("Send Test Email")
        self.test_email_btn.clicked.connect(self.on_test_email)
        email_layout.addWidget(self.test_email_btn, 2, 0, 1, 2)

        email_group.setLayout(email_layout)
        left_layout.addWidget(email_group)

        # Storage
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

        app_status_layout.addWidget(QLabel("Uptime:"), 0, 0)
        self.uptime_label = QLabel("0h 0m 0s")
        self.uptime_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
        app_status_layout.addWidget(self.uptime_label, 0, 1)

        app_status_layout.addWidget(QLabel("Watchdog Service:"), 1, 0)
        self.watchdog_status = QLabel("Unknown")
        app_status_layout.addWidget(self.watchdog_status, 1, 1)

        app_status_group.setLayout(app_status_layout)
        left_layout.addWidget(app_status_group)

        # Service Status Overview
        status_group = QGroupBox("Service Status")
        status_layout = QGridLayout()

        status_layout.addWidget(QLabel("Google Drive Upload:"), 0, 0)
        self.drive_service_status = QLabel("Disabled")
        self.drive_service_status.setStyleSheet("color: #666;")
        status_layout.addWidget(self.drive_service_status, 0, 1)

        status_layout.addWidget(QLabel("Email Notifications:"), 1, 0)
        self.email_service_status = QLabel("Disabled")
        self.email_service_status.setStyleSheet("color: #666;")
        status_layout.addWidget(self.email_service_status, 1, 1)

        status_layout.addWidget(QLabel("Hourly Reports:"), 2, 0)
        self.hourly_service_status = QLabel("Disabled")
        self.hourly_service_status.setStyleSheet("color: #666;")
        status_layout.addWidget(self.hourly_service_status, 2, 1)

        status_layout.addWidget(QLabel("Storage Cleanup:"), 3, 0)
        self.cleanup_service_status = QLabel("Disabled")
        self.cleanup_service_status.setStyleSheet("color: #666;")
        status_layout.addWidget(self.cleanup_service_status, 3, 1)

        status_group.setLayout(status_layout)
        left_layout.addWidget(status_group)

        left_layout.addStretch()

        # Right side
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Google Drive
        drive_group = QGroupBox("Google Drive Upload Services")
        drive_layout = QGridLayout()

        drive_layout.addWidget(QLabel("Folder:"), 0, 0)
        folder_name = self.uploader.config.get('services', {}).get('drive_upload', {}).get('folder_name', 'Unknown')
        self.drive_folder_name = QLabel(folder_name)
        self.drive_folder_name.setStyleSheet("font-weight: bold; color: #2E7D32;")
        drive_layout.addWidget(self.drive_folder_name, 0, 1)

        drive_layout.addWidget(QLabel("Status:"), 1, 0)
        self.drive_status = QLabel("Checking...")
        self.drive_status.setStyleSheet("color: #FF6F00; font-weight: bold;")
        drive_layout.addWidget(self.drive_status, 1, 1)

        drive_layout.addWidget(QLabel("Queue:"), 2, 0)
        self.drive_queue = QLabel("N/A")
        self.drive_queue.setStyleSheet("color: #424242; font-weight: bold;")
        drive_layout.addWidget(self.drive_queue, 2, 1)

        drive_layout.addWidget(QLabel("Files in Drive:"), 3, 0)
        self.drive_file_count = QLabel("0")
        drive_layout.addWidget(self.drive_file_count, 3, 1)

        drive_layout.addWidget(QLabel("Total Size:"), 4, 0)
        self.drive_total_size = QLabel("0.0 MB")
        drive_layout.addWidget(self.drive_total_size, 4, 1)

        drive_layout.addWidget(QLabel("Latest Upload:"), 5, 0)
        self.drive_latest_file = QLabel("None")
        drive_layout.addWidget(self.drive_latest_file, 5, 1)

        drive_layout.addWidget(QLabel("View Folder:"), 6, 0)
        self.drive_folder_link = QLabel("Open Drive Folder")
        self.drive_folder_link.setStyleSheet("color: #1976D2; text-decoration: underline; font-weight: bold;")
        self.drive_folder_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.drive_folder_link.mousePressEvent = self.on_drive_folder_link_clicked
        drive_layout.addWidget(self.drive_folder_link, 6, 1)

        drive_group.setLayout(drive_layout)
        right_layout.addWidget(drive_group)

        # OpenAI
        openai_group = QGroupBox("OpenAI Bird Identification")
        openai_layout = QGridLayout()

        title_label = QLabel("AI Bird Analysis")
        title_font = title_label.font()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        openai_layout.addWidget(title_label, 0, 0, 1, 2)

        openai_layout.addWidget(QLabel("Images Analyzed Today:"), 1, 0)
        self.openai_daily_count = QLabel("0")
        self.openai_daily_count.setStyleSheet("font-size: 24px; font-weight: bold; color: #4CAF50;")
        openai_layout.addWidget(self.openai_daily_count, 1, 1)

        reset_label = QLabel("Resets at midnight")
        reset_label.setStyleSheet("font-size: 11px; color: #424242;")
        openai_layout.addWidget(reset_label, 2, 0, 1, 2)

        openai_group.setLayout(openai_layout)
        right_layout.addWidget(openai_group)

        right_layout.addStretch()

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 400])

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    def update_service_status(self, status):
        """Update service status - kept for compatibility"""
        pass

    def update_upload_status(self):
        """Update upload service status"""
        if self.uploader:
            status = self.uploader.get_status()
            drive_enabled = status['drive']['enabled']
            drive_queue = status['drive']['queue_size']

            logger.debug(f"Drive upload status: enabled={drive_enabled}, queue={drive_queue}")

            if drive_enabled:
                self.drive_status.setText("Running")
                self.drive_status.setStyleSheet("color: #00ff64;")
            else:
                self.drive_status.setText("Disabled")
                self.drive_status.setStyleSheet("color: #ff6464;")

            self.drive_queue.setText(f"{drive_queue}")
            self.drive_queue.setStyleSheet("color: #ffffff;")

    def update_drive_stats(self, stats):
        """Update Drive statistics from background thread"""
        logger.debug(f"Updating Drive stats in GUI: {stats}")
        if stats and stats.get('file_count', 0) > 0:
            self.drive_file_count.setText(str(stats['file_count']))

            size_mb = stats['total_size'] / (1024 * 1024)
            if size_mb >= 1000:
                size_str = f"{size_mb/1024:.1f} GB"
            else:
                size_str = f"{size_mb:.1f} MB"
            self.drive_total_size.setText(size_str)

            if stats['latest_file']:
                self.drive_latest_file.setText(stats['latest_file'])
            else:
                self.drive_latest_file.setText("None")
        else:
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
        """Update storage information with caching"""
        try:
            if not hasattr(self, '_storage_stats_cache'):
                self._storage_stats_cache = {'count': 0, 'size': 0, 'last_update': 0}

            current_time = time.time()
            if current_time - self._storage_stats_cache['last_update'] > 30:
                storage_dir = self.config.get('storage', {}).get('save_dir', str(Path.home() / 'BirdPhotos'))
                if os.path.exists(storage_dir):
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

            total_size = self._storage_stats_cache['size']
            file_count = self._storage_stats_cache['count']
            size_gb = total_size / (1024**3)

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
                self.watchdog_status.setStyleSheet("color: #00ff64;")
            elif status == 'inactive':
                self.watchdog_status.setText("Stopped")
                self.watchdog_status.setStyleSheet("color: #ff6464;")
            else:
                self.watchdog_status.setText(f"Unknown ({status})")
                self.watchdog_status.setStyleSheet("color: #ffaa00;")

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
        """Send test email"""
        try:
            email_config = self.config.get('email', {})

            if not email_config.get('sender'):
                QMessageBox.warning(self, "Email Not Configured",
                                  "Please configure email settings in the Configuration tab first.")
                return
            if not email_config.get('password'):
                QMessageBox.warning(self, "Email Not Configured",
                                  "Please configure email password in the Configuration tab first.")
                return

            temp_handler = EmailHandler(self.config)

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
                                  "Failed to send test email. Check logs for details.")
            logger.info("Test email sent from Services tab")
        except Exception as e:
            logger.error(f"Error sending test email: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to send test email:\n\n{str(e)}")

    def update_service_statuses(self):
        """Update all service status displays"""
        if not self.config:
            return

        drive_enabled = self.config.get('services', {}).get('drive_upload', {}).get('enabled', False)
        self.drive_service_status.setText("Enabled" if drive_enabled else "Disabled")
        self.drive_service_status.setStyleSheet("color: #4CAF50; font-weight: bold;" if drive_enabled else "color: #666;")

        email_enabled = self.config.get('email', {}).get('enabled', False)
        self.email_service_status.setText("Enabled" if email_enabled else "Disabled")
        self.email_service_status.setStyleSheet("color: #4CAF50; font-weight: bold;" if email_enabled else "color: #666;")

        hourly_enabled = self.config.get('email', {}).get('hourly_reports', False)
        self.hourly_service_status.setText("Enabled" if hourly_enabled else "Disabled")
        self.hourly_service_status.setStyleSheet("color: #4CAF50; font-weight: bold;" if hourly_enabled else "color: #666;")

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
