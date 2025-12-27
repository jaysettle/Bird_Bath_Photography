#!/usr/bin/env python3
"""Full-size image viewer dialog with keyboard navigation"""

import threading
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QSizePolicy, QApplication, QMessageBox,
                            QMainWindow)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap

from src.logger import get_logger

logger = get_logger(__name__)


class ImageViewerDialog(QDialog):
    """Full-size image viewer dialog with keyboard navigation"""

    email_finished = pyqtSignal(bool, str)

    def __init__(self, parent, current_image_path, all_image_paths):
        super().__init__(parent)

        self.email_finished.connect(self._email_complete)
        self.current_image_path = str(current_image_path)
        self.all_image_paths = [str(p) for p in all_image_paths]
        self.current_index = self.all_image_paths.index(self.current_image_path)

        self.setWindowTitle(Path(current_image_path).name)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(1200, 800)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.image_label, 1)

        self.nav_label = QLabel()
        self.nav_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nav_label.setStyleSheet("color: #888; padding: 5px;")
        layout.addWidget(self.nav_label)

        button_layout = QHBoxLayout()

        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.clicked.connect(self.show_previous)
        button_layout.addWidget(self.prev_btn)

        self.email_btn = QPushButton("📧 Send to Email")
        self.email_btn.clicked.connect(self.send_to_email)
        button_layout.addWidget(self.email_btn)

        close_btn = QPushButton("Close (Esc)")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        self.next_btn = QPushButton("Next →")
        self.next_btn.clicked.connect(self.show_next)
        button_layout.addWidget(self.next_btn)

        layout.addLayout(button_layout)

        self.load_current_image()

        self.resize(1600, 1200)
        self.setMinimumSize(1600, 1200)

        self.original_pixmap = None

    def keyPressEvent(self, event):
        """Handle keyboard navigation"""
        if event.key() == Qt.Key.Key_Left:
            self.show_previous()
        elif event.key() == Qt.Key.Key_Right:
            self.show_next()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        """Handle window resize - rescale image to fit new size"""
        super().resizeEvent(event)
        if hasattr(self, 'original_pixmap') and self.original_pixmap:
            QTimer.singleShot(50, self.scale_and_display_image)

    def scale_and_display_image(self):
        """Scale and display the current image to fit available space"""
        if not self.original_pixmap:
            return

        try:
            available_size = self.image_label.size()
            max_width = max(available_size.width() - 40, 600)
            max_height = max(available_size.height() - 40, 400)

            if (self.original_pixmap.width() > max_width or
                self.original_pixmap.height() > max_height):
                scaled_pixmap = self.original_pixmap.scaled(
                    max_width, max_height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
            else:
                scaled_pixmap = self.original_pixmap

            self.image_label.setPixmap(scaled_pixmap)

        except Exception as e:
            logger.error(f"Error scaling image: {e}")

    def load_current_image(self):
        """Load and display the current image"""
        try:
            self.original_pixmap = QPixmap(self.current_image_path)
            self.scale_and_display_image()

            filename = Path(self.current_image_path).name
            self.setWindowTitle(filename)
            self.nav_label.setText(f"Image {self.current_index + 1} of {len(self.all_image_paths)} | Use arrow keys to navigate")

            self.prev_btn.setEnabled(self.current_index > 0)
            self.next_btn.setEnabled(self.current_index < len(self.all_image_paths) - 1)

        except Exception as e:
            logger.error(f"Error loading image: {e}")
            self.image_label.setText("Error loading image")

    def show_previous(self):
        """Show previous image"""
        if self.current_index > 0:
            self.current_index -= 1
            self.current_image_path = self.all_image_paths[self.current_index]
            self.load_current_image()

    def show_next(self):
        """Show next image"""
        if self.current_index < len(self.all_image_paths) - 1:
            self.current_index += 1
            self.current_image_path = self.all_image_paths[self.current_index]
            self.load_current_image()

    def send_to_email(self):
        """Send current image via email"""
        try:
            main_window = self.parent()
            while main_window and not isinstance(main_window, QMainWindow):
                main_window = main_window.parent()

            if not main_window or not hasattr(main_window, 'email_handler'):
                QMessageBox.warning(self, "Email Error", "Email handler not available")
                return

            email_handler = main_window.email_handler
            if not email_handler or not email_handler.email_password:
                QMessageBox.warning(self, "Email Error", "Email is not configured. Please configure email in the Configuration tab.")
                return

            config = main_window.config
            recipient = config.get('email', {}).get('receivers', {}).get('primary', '')
            if not recipient:
                QMessageBox.warning(self, "Email Error", "No email recipient configured")
                return

            self.email_btn.setEnabled(False)
            self.email_btn.setText("Sending...")
            QApplication.processEvents()

            filename = Path(self.current_image_path).name

            def send_email_thread():
                try:
                    success = email_handler.send_email_with_attachments(
                        recipient=recipient,
                        subject=f"Bird Photo: {filename}",
                        body=f"Bird photo captured: {filename}\n\nSent from Bird Detection System",
                        attachment_paths=[self.current_image_path]
                    )
                    self.email_finished.emit(success, "")
                except Exception as e:
                    logger.error(f"Error sending email: {e}")
                    self.email_finished.emit(False, str(e))

            thread = threading.Thread(target=send_email_thread, daemon=True)
            thread.start()

        except Exception as e:
            logger.error(f"Error in send_to_email: {e}")
            QMessageBox.critical(self, "Email Error", f"Failed to send email: {str(e)}")
            self.email_btn.setEnabled(True)
            self.email_btn.setText("📧 Send to Email")

    def _email_complete(self, success, error_msg):
        """Called when email send completes"""
        self.email_btn.setEnabled(True)
        if success:
            self.email_btn.setText("✓ Sent!")
            QTimer.singleShot(2000, lambda: self.email_btn.setText("📧 Send to Email"))
        else:
            self.email_btn.setText("📧 Send to Email")
            error = error_msg or "Unknown error"
            QMessageBox.warning(self, "Email Failed", f"Failed to send email: {error}")
