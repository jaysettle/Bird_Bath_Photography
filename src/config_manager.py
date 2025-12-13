#!/usr/bin/env python3
"""Configuration manager for Bird Detection System"""

import os
import json
from pathlib import Path


class ConfigManager:
    """Manages configuration loading and saving"""

    def __init__(self, config_path=None):
        if config_path is None:
            # Default to config.json in parent directory (main app dir)
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
        self.config_path = config_path
        self.config = {}
        self.load_config()

    def load_config(self):
        """Load configuration from file"""
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            # Convert any ~ paths to absolute paths
            self._expand_paths()
        except FileNotFoundError:
            # config.json doesn't exist - create it from config.example.json or defaults
            print("INFO: config.json not found, creating from template...")

            # Try to load from config.example.json as template
            example_path = self.config_path.replace('config.json', 'config.example.json')
            try:
                with open(example_path, 'r') as f:
                    self.config = json.load(f)
                    print("INFO: Loaded configuration template from config.example.json")

                    # Clear sensitive fields for new users
                    if 'email' in self.config:
                        self.config['email']['sender'] = ''
                        self.config['email']['password'] = ''
                    if 'openai' in self.config:
                        self.config['openai']['api_key'] = ''

            except FileNotFoundError:
                # No example file either - use hardcoded defaults
                print("INFO: No config.example.json found, using hardcoded defaults")
                self.config = self._get_default_config()

            # Expand paths for the loaded config
            self._expand_paths()

            # Automatically save as config.json for future use
            try:
                with open(self.config_path, 'w') as f:
                    json.dump(self.config, f, indent=4)
                print("INFO: Created config.json with default configuration")
                print("INFO: Please configure your API keys in the Configuration tab")
            except Exception as e:
                print(f"ERROR: Failed to create config.json: {e}")
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = self._get_default_config()
            self._expand_paths()

    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            raise Exception(f"Failed to save config: {e}")

    def _expand_paths(self):
        """Expand ~ and environment variables in paths"""
        if 'storage' in self.config and 'save_dir' in self.config['storage']:
            # Handle ~ for home directory
            path = self.config['storage']['save_dir']
            if path.startswith('~'):
                self.config['storage']['save_dir'] = str(Path(path).expanduser())
            # Handle relative paths by making them absolute
            elif not os.path.isabs(path):
                self.config['storage']['save_dir'] = str(Path(path).absolute())

    def _get_default_config(self):
        """Get default configuration"""
        return {
            "camera": {
                "resolution": "4k",
                "socket": "rgb",
                "preview_width": 600,
                "preview_height": 400,
                "orientation": "rotate_180",
                "focus": 132,
                "exposure_ms": 20,
                "iso_min": 100,
                "iso_max": 800,
                "white_balance": 6208,
                "threshold": 37,
                "min_area": 500
            },
            "motion_detection": {
                "threshold": 50,
                "min_area": 500,
                "debounce_time": 4.0,
                "default_roi": {
                    "enabled": True,
                    "x": 43,
                    "y": 177,
                    "width": 699,
                    "height": 287
                }
            },
            "storage": {
                "save_dir": "~/BirdPhotos",
                "max_size_gb": 2,
                "cleanup_time": "23:30"
            },
            "email": {
                "sender": "",
                "password": "",
                "receivers": {"primary": ""},
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 465,
                "hourly_report": True,
                "daily_email_time": "16:30",
                "quiet_hours": {"start": 23, "end": 5}
            },
            "services": {
                "drive_upload": {
                    "enabled": False,
                    "folder_name": "Bird Photos",
                    "upload_delay": 3
                },
                "cleanup": {
                    "enabled": True,
                    "schedule": "daily"
                }
            },
            "logging": {
                "level": "INFO",
                "max_log_size": "10MB",
                "backup_count": 5,
                "journal_integration": True
            },
            "ui": {
                "window_title": "Bird Detection System",
                "tabs": ["Camera", "Services", "Configuration", "Logs"],
                "refresh_rate": 30
            },
            "openai": {
                "api_key": "",
                "enabled": False,
                "max_images_per_hour": 10
            }
        }
