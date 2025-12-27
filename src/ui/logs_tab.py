#!/usr/bin/env python3
"""Logs tab for viewing application and system logs"""

import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
                            QPushButton, QCheckBox, QMessageBox)
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont

from src.logger import get_logger, log_buffer

logger = get_logger(__name__)


class LogsTab(QWidget):
    """Real-time logs tab"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

        self.log_timer = QTimer()
        self.log_timer.timeout.connect(self.update_logs)
        self.log_timer.start(5000)

    def setup_ui(self):
        """Setup the logs tab UI"""
        layout = QVBoxLayout()

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

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Courier", 9))
        self.log_display.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")

        layout.addWidget(self.log_display)

        self.setLayout(layout)

    def update_logs(self):
        """Update log display"""
        try:
            buffer_lines = log_buffer.get_lines()

            log_file_path = Path(__file__).parent.parent.parent / 'logs' / 'bird_detection.log'
            file_lines = []

            if log_file_path.exists():
                try:
                    with open(log_file_path, 'r') as f:
                        file_lines = f.readlines()[-200:]
                        file_lines = [line.strip() for line in file_lines if line.strip()]
                except Exception as e:
                    logger.debug(f"Could not read log file: {e}")

            all_lines = file_lines if file_lines else buffer_lines

            if all_lines:
                self.log_display.clear()
                if isinstance(all_lines, list):
                    self.log_display.append('\n'.join(all_lines))
                else:
                    self.log_display.append(all_lines)

                if self.auto_scroll_cb.isChecked():
                    cursor = self.log_display.textCursor()
                    cursor.movePosition(cursor.MoveOperation.End)
                    self.log_display.setTextCursor(cursor)
            elif not all_lines and not buffer_lines:
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
