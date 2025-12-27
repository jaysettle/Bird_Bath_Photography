#!/usr/bin/env python3
"""Configuration tab for all system settings"""

import os
import json
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                            QGroupBox, QLabel, QLineEdit, QCheckBox, QSpinBox,
                            QPushButton, QTimeEdit, QScrollArea, QFileDialog,
                            QMessageBox, QApplication)
from PyQt6.QtCore import Qt, QTimer, QTime, QUrl
from PyQt6.QtGui import QDesktopServices

from src.logger import get_logger
from src.email_handler import EmailHandler

logger = get_logger(__name__)


class ConfigTab(QWidget):
    """Configuration tab for all system settings"""
    
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.config = config_manager.config
        self.setup_ui()
        self.load_current_settings()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Scroll area for long config
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Email Configuration
        self.create_email_section(scroll_layout)
        
        # Local Storage Configuration
        self.create_local_storage_section(scroll_layout)
        
        # Google Drive Configuration
        self.create_drive_section(scroll_layout)
        
        # OpenAI Configuration
        self.create_openai_section(scroll_layout)
        
        # Pre-filter Configuration
        
        # System Management
        self.create_system_section(scroll_layout)
        
        # Logging Configuration
        self.create_logging_section(scroll_layout)
        
        # Save/Apply buttons
        self.create_buttons_section(scroll_layout)
        
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
    
    def create_email_section(self, layout):
        group = QGroupBox("Email Settings")
        group_layout = QGridLayout()
        
        # Email sender
        group_layout.addWidget(QLabel("Sender Email:"), 0, 0)
        self.email_sender = QLineEdit()
        group_layout.addWidget(self.email_sender, 0, 1, 1, 2)
        
        # App password
        group_layout.addWidget(QLabel("App Password:"), 1, 0)
        self.email_password = QLineEdit()
        self.email_password.setEchoMode(QLineEdit.EchoMode.Password)
        group_layout.addWidget(self.email_password, 1, 1)
        
        # App password help link
        app_password_link = QLabel('<a href="https://myaccount.google.com/apppasswords">Get App Password</a>')
        app_password_link.setOpenExternalLinks(True)
        group_layout.addWidget(app_password_link, 1, 2)
        
        # Email enabled checkbox
        self.email_notifications_enabled = QCheckBox("Enable Email Notifications")
        group_layout.addWidget(self.email_notifications_enabled, 2, 0, 1, 3)
        
        # Hourly reports checkbox
        self.hourly_reports_enabled = QCheckBox("Enable Hourly Reports")
        group_layout.addWidget(self.hourly_reports_enabled, 3, 0, 1, 3)
        
        # Test email button
        self.test_email_btn = QPushButton("Send Test Email")
        self.test_email_btn.clicked.connect(self.on_test_email)
        group_layout.addWidget(self.test_email_btn, 4, 0, 1, 3)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
    
    def create_local_storage_section(self, layout):
        group = QGroupBox("Local Storage")
        group_layout = QGridLayout()
        
        # Home folder
        group_layout.addWidget(QLabel("Save Directory:"), 0, 0)
        self.storage_dir = QLineEdit()
        group_layout.addWidget(self.storage_dir, 0, 1)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_storage_dir)
        group_layout.addWidget(browse_btn, 0, 2)
        
        # Storage limit
        group_layout.addWidget(QLabel("Max Storage (GB):"), 1, 0)
        self.storage_limit = QSpinBox()
        self.storage_limit.setRange(1, 1000)
        self.storage_limit.setValue(2)
        group_layout.addWidget(self.storage_limit, 1, 1)
        
        # Cleanup time
        group_layout.addWidget(QLabel("Cleanup Time:"), 2, 0)
        self.cleanup_time = QTimeEdit()
        self.cleanup_time.setDisplayFormat("HH:mm")
        group_layout.addWidget(self.cleanup_time, 2, 1)
        
        # Storage cleanup checkbox
        self.cleanup_enabled = QCheckBox("Enable Storage Cleanup")
        group_layout.addWidget(self.cleanup_enabled, 3, 0, 1, 2)
        
        # Manual cleanup button
        cleanup_now_btn = QPushButton("Run Cleanup Now")
        cleanup_now_btn.clicked.connect(self.run_cleanup_now)
        group_layout.addWidget(cleanup_now_btn, 3, 2)
        
        # Clear button
        clear_local_btn = QPushButton("Clear All Local Images")
        clear_local_btn.clicked.connect(self.clear_local_images)
        group_layout.addWidget(clear_local_btn, 4, 0, 1, 3)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
    
    def create_drive_section(self, layout):
        group = QGroupBox("Google Drive")
        group_layout = QGridLayout()
        
        # Drive enabled
        self.drive_upload_enabled = QCheckBox("Enable Google Drive Upload")
        group_layout.addWidget(self.drive_upload_enabled, 0, 0, 1, 3)
        
        # Folder name
        group_layout.addWidget(QLabel("Folder Name:"), 1, 0)
        self.drive_folder = QLineEdit()
        group_layout.addWidget(self.drive_folder, 1, 1, 1, 2)
        
        # Storage limit
        group_layout.addWidget(QLabel("Max Storage (GB):"), 2, 0)
        self.drive_limit = QSpinBox()
        self.drive_limit.setRange(1, 100)
        self.drive_limit.setValue(2)
        group_layout.addWidget(self.drive_limit, 2, 1)
        
        # Cleanup time
        group_layout.addWidget(QLabel("Cleanup Time:"), 3, 0)
        self.drive_cleanup_time = QTimeEdit()
        self.drive_cleanup_time.setTime(QTime(23, 30))  # Default 11:30 PM
        self.drive_cleanup_time.setDisplayFormat("HH:mm")
        group_layout.addWidget(self.drive_cleanup_time, 3, 1)
        
        # OAuth setup button
        setup_drive_btn = QPushButton("Setup Google Drive OAuth")
        setup_drive_btn.clicked.connect(self.setup_google_drive)
        group_layout.addWidget(setup_drive_btn, 4, 0, 1, 2)
        
        # Clear button
        clear_drive_btn = QPushButton("Clear All Drive Images")
        clear_drive_btn.clicked.connect(self.clear_drive_images)
        group_layout.addWidget(clear_drive_btn, 4, 2)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
    
    def create_openai_section(self, layout):
        group = QGroupBox("AI Bird Identification")
        group_layout = QGridLayout()
        
        # OpenAI enabled
        self.openai_enabled = QCheckBox("Enable AI Species Identification")
        group_layout.addWidget(self.openai_enabled, 0, 0, 1, 3)
        
        # API key
        group_layout.addWidget(QLabel("OpenAI API Key:"), 1, 0)
        self.openai_key = QLineEdit()
        self.openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        group_layout.addWidget(self.openai_key, 1, 1)
        
        # API key link
        api_link_btn = QPushButton("Get API Key")
        api_link_btn.setMaximumWidth(100)
        api_link_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        api_link_btn.clicked.connect(self.open_openai_api_page)
        group_layout.addWidget(api_link_btn, 1, 2)
        
        # Rate limit
        group_layout.addWidget(QLabel("Max Images/Hour:"), 2, 0)
        self.openai_limit = QSpinBox()
        self.openai_limit.setRange(1, 20)
        self.openai_limit.setValue(10)
        group_layout.addWidget(self.openai_limit, 2, 1)
        
        # Test API button
        self.test_api_btn = QPushButton("Test API Connection")
        self.test_api_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        self.test_api_btn.clicked.connect(self.test_openai_api)
        group_layout.addWidget(self.test_api_btn, 3, 0, 1, 3)

        # Clear species button
        clear_species_btn = QPushButton("Clear Species Database")
        clear_species_btn.clicked.connect(self.clear_species_database)
        group_layout.addWidget(clear_species_btn, 4, 0, 1, 3)

        group.setLayout(group_layout)
        layout.addWidget(group)
    
    
    def create_system_section(self, layout):
        group = QGroupBox("System Management")
        group_layout = QGridLayout()
        
        # Watchdog status
        group_layout.addWidget(QLabel("Watchdog Service:"), 0, 0)
        self.watchdog_status = QLabel("Unknown")
        group_layout.addWidget(self.watchdog_status, 0, 1)
        
        # Install watchdog button
        install_watchdog_btn = QPushButton("Install Watchdog Service")
        install_watchdog_btn.clicked.connect(self.install_watchdog)
        group_layout.addWidget(install_watchdog_btn, 1, 0)
        
        # Start/Stop watchdog buttons
        start_watchdog_btn = QPushButton("Start Watchdog")
        start_watchdog_btn.clicked.connect(self.start_watchdog)
        group_layout.addWidget(start_watchdog_btn, 1, 1)
        
        stop_watchdog_btn = QPushButton("Stop Watchdog")
        stop_watchdog_btn.clicked.connect(self.stop_watchdog)
        group_layout.addWidget(stop_watchdog_btn, 1, 2)
        
        # Check status button
        check_status_btn = QPushButton("Check Status")
        check_status_btn.clicked.connect(self.check_watchdog_status)
        group_layout.addWidget(check_status_btn, 2, 0)
        
        # View logs button
        view_logs_btn = QPushButton("View Watchdog Logs")
        view_logs_btn.clicked.connect(self.view_watchdog_logs)
        group_layout.addWidget(view_logs_btn, 2, 1)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
        
        # Check status on startup
        QTimer.singleShot(1000, self.check_watchdog_status)
        QTimer.singleShot(1000, self.check_management_status)
    
    def create_logging_section(self, layout):
        """Create logging configuration section"""
        group = QGroupBox("Logging Settings")
        group_layout = QGridLayout()
        
        # Logging enabled checkbox
        group_layout.addWidget(QLabel("Enable Verbose Logging:"), 0, 0)
        self.logging_enabled = QCheckBox()
        self.logging_enabled.setToolTip(
            "When enabled: Full logging (INFO, DEBUG, WARNING, ERROR)\n"
            "When disabled: Only errors logged (better performance)"
        )
        self.logging_enabled.toggled.connect(self.on_logging_toggled)
        group_layout.addWidget(self.logging_enabled, 0, 1)
        
        # Status indicator
        self.logging_status = QLabel("Status: Enabled")
        self.logging_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
        group_layout.addWidget(self.logging_status, 1, 0, 1, 2)
        
        # Performance note
        note = QLabel("💡 Disable logging to improve performance during normal operation")
        note.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        group_layout.addWidget(note, 2, 0, 1, 2)
        
        group.setLayout(group_layout)
        layout.addWidget(group)
    
    def create_buttons_section(self, layout):
        button_layout = QHBoxLayout()
        
        save_btn = QPushButton("Save Configuration")
        save_btn.clicked.connect(self.save_config)
        button_layout.addWidget(save_btn)
        
        apply_btn = QPushButton("Apply & Restart Services")
        apply_btn.clicked.connect(self.apply_config)
        button_layout.addWidget(apply_btn)
        
        layout.addLayout(button_layout)
    
    def load_current_settings(self):
        """Load current config values into UI"""
        # Email settings
        email_config = self.config.get('email', {})
        self.email_sender.setText(email_config.get('sender', ''))
        self.email_password.setText(email_config.get('password', ''))
        # Set email notification checkboxes
        email_notifications = email_config.get('enabled', False)
        self.email_notifications_enabled.setChecked(email_notifications)
        
        hourly_reports = email_config.get('hourly_reports', False)
        self.hourly_reports_enabled.setChecked(hourly_reports)
        
        # Storage settings
        storage_config = self.config.get('storage', {})
        self.storage_dir.setText(storage_config.get('save_dir', str(Path.home() / 'BirdPhotos')))
        self.storage_limit.setValue(storage_config.get('max_size_gb', 2))
        
        cleanup_time = storage_config.get('cleanup_time', '23:30')
        hour, minute = map(int, cleanup_time.split(':'))
        self.cleanup_time.setTime(QTime(hour, minute))
        self.cleanup_enabled.setChecked(storage_config.get('cleanup_enabled', False))
        
        # Drive settings
        drive_config = self.config.get('services', {}).get('drive_upload', {})
        self.drive_upload_enabled.setChecked(drive_config.get('enabled', False))
        self.drive_folder.setText(drive_config.get('folder_name', 'Bird Photos'))
        self.drive_limit.setValue(drive_config.get('max_size_gb', 2))
        cleanup_time_str = drive_config.get('cleanup_time', '23:30')
        cleanup_time = QTime.fromString(cleanup_time_str, 'HH:mm')
        self.drive_cleanup_time.setTime(cleanup_time)
        
        # OpenAI settings
        openai_config = self.config.get('openai', {})
        self.openai_enabled.setChecked(openai_config.get('enabled', False))
        self.openai_key.setText(openai_config.get('api_key', ''))
        self.openai_limit.setValue(openai_config.get('max_images_per_hour', 10))
        
        
        # Logging settings
        logging_config = self.config.get('logging', {})
        logging_enabled = logging_config.get('enabled', True)
        self.logging_enabled.setChecked(logging_enabled)
        self.update_logging_status(logging_enabled)
    
    def browse_storage_dir(self):
        """Browse for storage directory"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Storage Directory", self.storage_dir.text()
        )
        if dir_path:
            self.storage_dir.setText(dir_path)
    
    def open_openai_api_page(self):
        """Open OpenAI API key page in browser"""
        try:
            url = QUrl("https://platform.openai.com/api-keys")
            QDesktopServices.openUrl(url)
            logger.info("Opened OpenAI API keys page in browser")
        except Exception as e:
            logger.error(f"Failed to open OpenAI API page: {e}")
            QMessageBox.information(
                self,
                "OpenAI API Keys",
                "Please visit: https://platform.openai.com/api-keys\n\n"
                "Create an account and generate an API key to enable bird identification."
            )

    def _update_api_button_status(self, status, duration=2000):
        """Update API test button with status (GOOD/BAD) for a short time"""
        original_text = "Test API Connection"
        if status == "GOOD":
            self.test_api_btn.setText(f"Test API Connection - ✓ GOOD")
            self.test_api_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    padding: 5px;
                    border-radius: 3px;
                    font-weight: bold;
                }
            """)
        elif status == "BAD":
            self.test_api_btn.setText(f"Test API Connection - ✗ BAD")
            self.test_api_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f44336;
                    color: white;
                    border: none;
                    padding: 5px;
                    border-radius: 3px;
                    font-weight: bold;
                }
            """)

        # Reset after duration
        QTimer.singleShot(duration, lambda: self._reset_api_button())

    def _reset_api_button(self):
        """Reset API test button to original state"""
        self.test_api_btn.setText("Test API Connection")
        self.test_api_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)

    def test_openai_api(self):
        """Test OpenAI API connection with a simple request"""
        logger.info("=== TEST OPENAI API BUTTON CLICKED ===")
        import requests
        import base64
        from pathlib import Path

        api_key = self.openai_key.text().strip()
        logger.info(f"API key field value: {'[present]' if api_key else '[empty]'}")

        if not api_key:
            self._update_api_button_status("BAD")
            QMessageBox.warning(
                self,
                "No API Key",
                "Please enter your OpenAI API key before testing."
            )
            return

        # Show progress dialog
        progress = QMessageBox(self)
        progress.setWindowTitle("Testing API")
        progress.setText("Testing OpenAI API connection...\n\nPlease wait...")
        progress.setStandardButtons(QMessageBox.StandardButton.NoButton)
        progress.show()
        QApplication.processEvents()

        try:
            # Create a simple test image (1x1 pixel PNG)
            test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

            logger.info("Testing OpenAI API with test request...")

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            payload = {
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "This is a test. Please respond with 'API connection successful'."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{test_image_b64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 50
            }

            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )

            progress.close()

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']

                self._update_api_button_status("GOOD")
                QMessageBox.information(
                    self,
                    "API Test Successful",
                    f"✅ OpenAI API connection successful!\n\n"
                    f"Response: {content[:100]}...\n\n"
                    f"Your API key is valid and working.\n"
                    f"Model: {result.get('model', 'gpt-4o')}"
                )
                logger.info("OpenAI API test successful")

            elif response.status_code == 401:
                self._update_api_button_status("BAD")
                QMessageBox.critical(
                    self,
                    "Authentication Failed",
                    "❌ Invalid API key\n\n"
                    "The API key you entered is not valid.\n"
                    "Please check your API key and try again.\n\n"
                    "Get your API key at: https://platform.openai.com/api-keys"
                )
                logger.error("OpenAI API test failed: Invalid API key")

            elif response.status_code == 429:
                self._update_api_button_status("BAD")
                QMessageBox.warning(
                    self,
                    "Rate Limit Exceeded",
                    "⚠️ Rate limit exceeded\n\n"
                    "Your account has exceeded the rate limit.\n"
                    "Please wait a moment and try again.\n\n"
                    f"Error: {response.text[:200]}"
                )
                logger.error("OpenAI API test failed: Rate limit exceeded")

            elif response.status_code == 402:
                self._update_api_button_status("BAD")
                QMessageBox.critical(
                    self,
                    "Payment Required",
                    "❌ Payment required\n\n"
                    "Your OpenAI account requires payment setup.\n"
                    "Please add a payment method to your account.\n\n"
                    "Visit: https://platform.openai.com/account/billing"
                )
                logger.error("OpenAI API test failed: Payment required")

            else:
                self._update_api_button_status("BAD")
                QMessageBox.critical(
                    self,
                    "API Test Failed",
                    f"❌ API test failed\n\n"
                    f"Status code: {response.status_code}\n"
                    f"Error: {response.text[:200]}"
                )
                logger.error(f"OpenAI API test failed: {response.status_code} - {response.text[:200]}")

        except requests.exceptions.Timeout:
            progress.close()
            self._update_api_button_status("BAD")
            QMessageBox.critical(
                self,
                "Connection Timeout",
                "❌ Connection timeout\n\n"
                "The request to OpenAI API timed out.\n"
                "Please check your internet connection and try again."
            )
            logger.error("OpenAI API test failed: Timeout")

        except requests.exceptions.ConnectionError:
            progress.close()
            self._update_api_button_status("BAD")
            QMessageBox.critical(
                self,
                "Connection Error",
                "❌ Connection error\n\n"
                "Could not connect to OpenAI API.\n"
                "Please check your internet connection and try again."
            )
            logger.error("OpenAI API test failed: Connection error")

        except Exception as e:
            progress.close()
            self._update_api_button_status("BAD")
            QMessageBox.critical(
                self,
                "Test Failed",
                f"❌ API test failed\n\n"
                f"Error: {str(e)}"
            )
            logger.error(f"OpenAI API test failed: {e}")

    def setup_google_drive(self):
        """Launch Google Drive OAuth setup"""
        msg = QMessageBox()
        msg.setWindowTitle("Google Drive Setup")
        msg.setText("To setup Google Drive:\n\n"
                   "1. Place client_secret.json in the project directory\n"
                   "2. Click OK to start OAuth flow\n"
                   "3. Complete authorization in your browser\n\n"
                   "Need client_secret.json? See OAUTH_SETUP.md")
        
        if msg.exec() == QMessageBox.StandardButton.Ok:
            # Check if client_secret.json exists first
            client_secret_path = Path(__file__).parent / "client_secret.json"
            if not client_secret_path.exists():
                QMessageBox.critical(self, "Error", 
                                   f"client_secret.json not found!\n\n"
                                   f"Please download OAuth2 credentials from Google Cloud Console\n"
                                   f"and save as: {client_secret_path}")
                return
            
            # Run the external setup script
            setup_script = Path(__file__).parent / "setup_google_drive.py"
            
            QMessageBox.information(self, "Google Drive Setup", 
                                  "A terminal window will open for the OAuth setup.\n\n"
                                  "Follow the instructions in the terminal to authorize Google Drive access.")
            
            try:
                import subprocess
                # Run in terminal so user can see output and interact
                if sys.platform == "linux" or sys.platform == "linux2":
                    # Try to use x-terminal-emulator first (works on most Linux distros)
                    subprocess.Popen(["x-terminal-emulator", "-e", sys.executable, str(setup_script)])
                elif sys.platform == "darwin":
                    # macOS
                    subprocess.Popen(["open", "-a", "Terminal", str(setup_script)])
                else:
                    # Windows
                    subprocess.Popen(["start", "cmd", "/k", sys.executable, str(setup_script)], shell=True)
                    
            except Exception as e:
                # Fallback: try to run directly
                try:
                    subprocess.Popen([sys.executable, str(setup_script)])
                except Exception as e2:
                    QMessageBox.critical(self, "Error", 
                                       f"Failed to run setup script:\n\n{str(e2)}\n\n"
                                       f"Please run manually:\n"
                                       f"python3 {setup_script}")
    
    def run_cleanup_now(self):
        """Run storage cleanup manually"""
        try:
            from src.cleanup_manager import CleanupManager
            logger.info("Running manual storage cleanup...")
            cleanup_manager = CleanupManager(self.config)
            result = cleanup_manager.cleanup_old_files()
            
            if result['cleaned']:
                msg = f"Cleanup completed!\n\nDeleted {result['files_deleted']} files\nFreed {result['space_freed']/(1024*1024):.1f}MB\nCurrent size: {result['current_size']:.2f}GB"
                QMessageBox.information(self, "Cleanup Complete", msg)
            else:
                msg = f"No cleanup needed.\n\nCurrent size: {result['current_size']:.2f}GB\nLimit: {self.config['storage']['max_size_gb']}GB"
                QMessageBox.information(self, "Storage OK", msg)
                
        except Exception as e:
            logger.error(f"Manual cleanup failed: {e}")
            QMessageBox.critical(self, "Cleanup Failed", f"Storage cleanup failed:\n{str(e)}")
    
    def clear_local_images(self):
        """Clear all local images and related tracking files"""
        reply = QMessageBox.question(
            self, "Clear Local Images", 
            "Are you sure you want to delete all local images?\n\n"
            "This will also clear the Google Drive upload tracking.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                storage_path = Path(self.storage_dir.text())
                files_deleted = 0
                
                if storage_path.exists():
                    # Delete image files
                    for img_file in storage_path.glob("*.jpeg"):
                        img_file.unlink()
                        files_deleted += 1
                    for img_file in storage_path.glob("*.jpg"):
                        img_file.unlink()
                        files_deleted += 1
                    
                    # Delete Google Drive upload tracking file
                    drive_uploads_file = storage_path / "drive_uploads.json"
                    if drive_uploads_file.exists():
                        drive_uploads_file.unlink()
                        logger.info("Deleted drive_uploads.json tracking file")
                
                QMessageBox.information(self, "Success", 
                    f"Local images cleared!\n\n"
                    f"Deleted {files_deleted} image files and upload tracking.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear images: {str(e)}")
    
    def clear_drive_images(self):
        """Clear all Google Drive images and reset upload tracking"""
        reply = QMessageBox.question(
            self, "Clear Drive Images", 
            "Are you sure you want to delete all Google Drive images?\n\n"
            "This will also reset the upload tracking so files can be re-uploaded.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Reset the drive uploads tracking file
                storage_path = Path(self.storage_dir.text())
                drive_uploads_file = storage_path / "drive_uploads.json"
                
                # Create empty tracking file
                empty_tracking = {
                    "uploaded_files": [],
                    "last_updated": datetime.now().isoformat()
                }
                
                if drive_uploads_file.exists() or storage_path.exists():
                    storage_path.mkdir(exist_ok=True)
                    with open(drive_uploads_file, 'w') as f:
                        json.dump(empty_tracking, f, indent=2)
                    logger.info("Reset drive_uploads.json tracking file")
                
                # Note: Actual Google Drive deletion would require Drive API implementation
                QMessageBox.information(self, "Upload Tracking Reset", 
                    "Google Drive upload tracking has been reset.\n\n"
                    "Note: To delete files from Google Drive, please use the Google Drive web interface.\n"
                    "Local files will now be re-uploaded on next sync.")
                    
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to reset tracking: {str(e)}")
    
    def clear_species_database(self):
        """Clear all identified bird species"""
        reply = QMessageBox.question(
            self, "Clear Species Database", 
            "Are you sure you want to delete all identified bird species?\n\nThis will remove all AI identification history and IdentifiedSpecies photos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Clear the species database
                species_db_path = Path(__file__).parent / "species_database.json"
                if species_db_path.exists():
                    # Reset to empty database
                    empty_db = {"species": {}, "sightings": [], "daily_stats": {}}
                    with open(species_db_path, 'w') as f:
                        json.dump(empty_db, f, indent=2)
                
                # Clear IdentifiedSpecies folder
                import shutil
                identified_species_path = Path.home() / "BirdPhotos" / "IdentifiedSpecies"
                if identified_species_path.exists():
                    shutil.rmtree(identified_species_path)
                    identified_species_path.mkdir(parents=True, exist_ok=True)  # Recreate empty folder
                
                # Refresh species tab if it exists
                if hasattr(self, 'species_tab'):
                    self.species_tab.load_species()
                    # Force heatmap to clear by updating with empty bird identifier
                    if hasattr(self.species_tab, 'heatmap_widget'):
                        self.species_tab.heatmap_widget.update_data(None)
                
                QMessageBox.information(self, "Success", "Species database and IdentifiedSpecies folder cleared!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear species database: {str(e)}")
    
    def check_watchdog_status(self):
        """Check watchdog service status"""
        try:
            result = subprocess.run(['systemctl', 'is-active', 'bird-detection-watchdog.service'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                status = result.stdout.strip()
                if status == 'active':
                    self.watchdog_status.setText("🟢 Running")
                    self.watchdog_status.setStyleSheet("color: green")
                else:
                    self.watchdog_status.setText(f"🟡 {status}")
                    self.watchdog_status.setStyleSheet("color: orange")
            else:
                self.watchdog_status.setText("🔴 Not installed")
                self.watchdog_status.setStyleSheet("color: red")
        except Exception as e:
            self.watchdog_status.setText("🔴 Error")
            self.watchdog_status.setStyleSheet("color: red")
    
    def install_watchdog(self):
        """Install watchdog service"""
        msg = QMessageBox()
        msg.setWindowTitle("Install Watchdog Service")
        msg.setText("This will install the Bird Detection watchdog service.\n\n"
                   "The watchdog will:\n"
                   "• Automatically start the app on system boot\n"
                   "• Restart the app if it crashes\n"
                   "• Run in the background 24/7\n\n"
                   "This requires administrator privileges (sudo).")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        
        if msg.exec() == QMessageBox.StandardButton.Ok:
            try:
                install_script = Path(__file__).parent / "install_watchdog_dynamic.sh"
                if not install_script.exists():
                    QMessageBox.critical(self, "Error", f"Install script not found: {install_script}")
                    return
                
                # Run in terminal so user can see prompts and enter sudo password
                QMessageBox.information(self, "Running Installer", 
                                      "The installer will open in a terminal window.\n"
                                      "Follow the prompts to complete installation.")
                
                # Try different terminal emulators in order of preference
                terminals = [
                    ['gnome-terminal', '--', 'bash', str(install_script)],
                    ['x-terminal-emulator', '-e', f'bash {install_script}'],
                    ['xterm', '-e', f'bash {install_script}'],
                    ['konsole', '-e', f'bash {install_script}']
                ]

                success = False
                for terminal_cmd in terminals:
                    try:
                        subprocess.Popen(terminal_cmd)
                        success = True
                        break
                    except FileNotFoundError:
                        continue

                if not success:
                    QMessageBox.critical(self, "Error", "No terminal emulator found.\n\n"
                                                       "Please run the following command manually:\n\n"
                                                       f"bash {install_script}")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to run installer: {str(e)}")
    
    def force_shutdown_for_watchdog(self):
        """Force shutdown of the application for watchdog restart"""
        try:
            logger.info("Force shutdown requested for watchdog restart")
            
            # Immediately stop all timers to prevent new operations
            if hasattr(self, 'status_timer'):
                self.status_timer.stop()
            if hasattr(self, 'slow_timer'):
                self.slow_timer.stop()
            
            # Force stop services quickly
            try:
                self.email_handler.stop()
            except:
                pass
            try:
                self.uploader.stop() 
            except:
                pass
            try:
                self.service_monitor.stop()
            except:
                pass
            try:
                self.camera_controller.disconnect()
            except:
                pass
            
            # Force close camera thread
            if self.camera_thread:
                try:
                    self.camera_thread.stop()
                    self.camera_thread.wait(1000)  # Wait max 1 second
                except:
                    pass
            
            # Close web server immediately
            if hasattr(self, 'web_server_process') and self.web_server_process:
                try:
                    self.web_server_process.terminate()
                    self.web_server_process.wait(timeout=1)
                except:
                    try:
                        self.web_server_process.kill()
                    except:
                        pass
            
            # Force quit the application
            from PyQt6.QtWidgets import QApplication
            QApplication.instance().quit()
            
            # If that doesn't work, use os._exit as last resort
            import os
            import threading
            def delayed_exit():
                import time
                time.sleep(2)
                os._exit(0)
            
            threading.Thread(target=delayed_exit, daemon=True).start()
            
        except Exception as e:
            logger.error(f"Error during force shutdown: {e}")
            # Last resort - immediate exit
            import os
            os._exit(0)
    
    def start_watchdog(self):
        """Start watchdog service and close app for automatic restart"""
        reply = QMessageBox.question(
            self, "Start Watchdog Service",
            "This will start the 24/7 monitoring service.\n\n"
            "The app will close and automatically reopen within 60 seconds.\n\n"
            "You will be prompted for administrator password.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Use pkexec for graphical authentication
                result = subprocess.run(['pkexec', 'systemctl', 'start', 'bird-detection-watchdog.service'],
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    # Show brief notification
                    msg = QMessageBox(self)
                    msg.setIcon(QMessageBox.Icon.Information)
                    msg.setWindowTitle("Watchdog Started")
                    msg.setText("Watchdog service started successfully!\n\nThis app will now close and reopen automatically.")
                    msg.show()

                    # Use QTimer to delay shutdown so message shows briefly
                    QTimer.singleShot(2000, self.force_shutdown_for_watchdog)
                elif "dismissed" in result.stderr.lower() or result.returncode == 126:
                    # User cancelled authentication
                    logger.info("User cancelled watchdog start authentication")
                else:
                    QMessageBox.critical(self, "Error", f"Failed to start service:\n{result.stderr}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to start watchdog: {str(e)}")
    
    def stop_watchdog(self):
        """Stop watchdog service"""
        reply = QMessageBox.question(
            self, "Stop Watchdog Service", 
            "This will stop the 24/7 monitoring service.\n\n"
            "⚠️ If this app is managed by the watchdog, it will also close.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Try to stop the service using pkexec for graphical authentication
                result = subprocess.run(['pkexec', 'systemctl', 'stop', 'bird-detection-watchdog.service'],
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    # Check if we're running under watchdog
                    if self.is_managed_by_watchdog():
                        QMessageBox.information(self, "Stopping...",
                                              "Watchdog service stopped!\n\n"
                                              "This application will now close as it was managed by the watchdog.")
                        # Close application since watchdog will kill it anyway
                        QApplication.quit()
                    else:
                        QMessageBox.information(self, "Success", "Watchdog service stopped!")
                elif "dismissed" in result.stderr.lower() or result.returncode == 126:
                    # User cancelled authentication
                    logger.info("User cancelled watchdog stop authentication")
                else:
                    QMessageBox.critical(self, "Error", f"Failed to stop service:\n{result.stderr}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to stop watchdog: {str(e)}")
    
    def is_managed_by_watchdog(self):
        """Check if this process is managed by the watchdog"""
        try:
            # Check if our parent process is the watchdog
            parent_pid = os.getppid()
            with open(f'/proc/{parent_pid}/cmdline', 'r') as f:
                parent_cmd = f.read()
                return 'bird_watchdog.py' in parent_cmd
        except:
            return False
    
    def check_management_status(self):
        """Check and display if app is managed by watchdog"""
        if self.is_managed_by_watchdog():
            self.watchdog_status.setText("🟢 Running (Managing this app)")
            self.watchdog_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            # Keep existing status
            pass
    
    def view_watchdog_logs(self):
        """View watchdog logs"""
        try:
            subprocess.Popen(['x-terminal-emulator', '-e', 
                            'sudo journalctl -u bird-detection-watchdog.service -f'])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open logs: {str(e)}")
    
    def on_logging_toggled(self, enabled):
        """Handle logging toggle"""
        try:
            from src.logger import set_logging_enabled
            
            # Update configuration and re-setup logging
            config_path = self.config_manager.config_path
            set_logging_enabled(enabled, config_path)
            
            # Update UI
            self.update_logging_status(enabled)
            
            # Reload config
            self.config_manager.load_config()
            self.config = self.config_manager.config

            # Reload OpenAI settings in UI to reflect config file values
            self._reload_openai_settings()

            # Update status silently without popup
            status = "enabled" if enabled else "disabled"
            logger.info(f"Logging has been {status}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update logging: {str(e)}")
    
    def _reload_openai_settings(self):
        """Reload OpenAI settings from config into UI fields"""
        try:
            openai_config = self.config.get('openai', {})
            self.openai_enabled.setChecked(openai_config.get('enabled', False))
            self.openai_key.setText(openai_config.get('api_key', ''))
            self.openai_limit.setValue(openai_config.get('max_images_per_hour', 10))
            logger.debug("Reloaded OpenAI settings from config")
        except Exception as e:
            logger.error(f"Error reloading OpenAI settings: {e}")

    def update_logging_status(self, enabled):
        """Update the logging status display"""
        if enabled:
            self.logging_status.setText("Status: Enabled (Full Logging)")
            self.logging_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self.logging_status.setText("Status: Disabled (Errors Only)")
            self.logging_status.setStyleSheet("color: #FF9800; font-weight: bold;")
    
    
    def save_config(self):
        """Save configuration to file"""
        try:
            # Create local storage directory if it doesn't exist
            storage_path = Path(self.storage_dir.text())
            if not storage_path.exists():
                try:
                    storage_path.mkdir(parents=True, exist_ok=True)
                    QMessageBox.information(self, "Directory Created", f"Created storage directory: {storage_path}")
                except Exception as e:
                    QMessageBox.warning(self, "Warning", f"Could not create directory {storage_path}: {str(e)}")
            
            # Update config with UI values
            self.config['email'] = {
                'sender': self.email_sender.text().strip(),
                'password': self.email_password.text().strip(),
                'receivers': {'primary': self.email_sender.text().strip()},
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 465,
                'enabled': self.email_notifications_enabled.isChecked(),
                'hourly_reports': self.hourly_reports_enabled.isChecked(),
                'daily_email_time': '16:30',
                'quiet_hours': {'start': 23, 'end': 5}
            }
            
            self.config['storage'] = {
                'save_dir': self.storage_dir.text(),
                'max_size_gb': self.storage_limit.value(),
                'cleanup_time': self.cleanup_time.time().toString('HH:mm'),
                'cleanup_enabled': self.cleanup_enabled.isChecked()
            }
            
            if 'services' not in self.config:
                self.config['services'] = {}
            
            self.config['services']['drive_upload'] = {
                'enabled': self.drive_upload_enabled.isChecked(),
                'folder_name': self.drive_folder.text(),
                'upload_delay': 3,
                'max_size_gb': self.drive_limit.value(),
                'cleanup_time': self.drive_cleanup_time.time().toString('HH:mm'),
                'note': 'OAuth2 only - personal Google Drive folder'
            }
            
            self.config['openai'] = {
                'api_key': self.openai_key.text().strip(),
                'enabled': self.openai_enabled.isChecked(),
                'max_images_per_hour': self.openai_limit.value()
            }
            
            
            # Update the config_manager's config first
            self.config_manager.config = self.config
            
            # Save to file
            self.config_manager.save_config()
            
            # Update the EmailHandler with new configuration immediately
            main_window = self.window()
            if hasattr(main_window, 'email_handler') and main_window.email_handler:
                try:
                    # Reinitialize EmailHandler with updated config
                    main_window.email_handler = EmailHandler(self.config)
                    logger.info("EmailHandler updated with new configuration")
                    
                    # Update gallery tab's email handler reference
                    if hasattr(main_window, 'gallery_tab') and main_window.gallery_tab:
                        main_window.gallery_tab.email_handler = main_window.email_handler
                        
                except Exception as e:
                    logger.error(f"Failed to update EmailHandler: {e}")
                    
            QMessageBox.information(self, "Success", "Configuration saved and applied!")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config: {str(e)}")
    
    def apply_config(self):
        """Save and apply configuration changes"""
        self.save_config()
        
        reply = QMessageBox.question(
            self, "Restart Required", 
            "Configuration saved. Restart application to apply changes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            QApplication.quit()
    
    def on_test_email(self):
        """Send test email"""
        try:
            # First, update config with current UI values (but don't save to file yet)
            email_config = {
                'sender': self.email_sender.text().strip(),
                'password': self.email_password.text().strip(),
                'receivers': {'primary': self.email_sender.text().strip()},
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 465,
                'enabled': self.email_notifications_enabled.isChecked(),
                'hourly_reports': self.hourly_reports_enabled.isChecked(),
                'daily_email_time': '16:30',
                'quiet_hours': {'start': 23, 'end': 5}
            }

            # Validate email settings
            if not email_config['sender']:
                QMessageBox.warning(self, "Email Not Configured",
                                  "Please enter your sender email address.")
                return
            if not email_config['password']:
                QMessageBox.warning(self, "Email Not Configured",
                                  "Please enter your app password.")
                return

            # Create temporary email handler with current settings
            temp_config = self.config.copy()
            temp_config['email'] = email_config

            logger.info("Creating temporary EmailHandler for test email")
            test_handler = EmailHandler(temp_config)

            # Send test email
            test_info = {
                'hostname': 'test-system',
                'ip_address': '127.0.0.1',
                'uptime': '5 minutes'
            }
            result = test_handler.send_reboot_notification(test_info)
            if result:
                QMessageBox.information(self, "Test Email", "Test email sent successfully!")
            else:
                QMessageBox.warning(self, "Test Email",
                                  "Failed to send test email. Check logs for details.\n\n"
                                  "Common issues:\n"
                                  "- Incorrect app password\n"
                                  "- 2-factor authentication not enabled\n"
                                  "- App password needs to be generated at:\n"
                                  "  https://myaccount.google.com/apppasswords")
            logger.info("Test email sent")
        except Exception as e:
            logger.error(f"Error sending test email: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to send test email:\n\n{str(e)}")
