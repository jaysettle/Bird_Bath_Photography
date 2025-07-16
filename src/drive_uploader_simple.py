#!/usr/bin/env python3
"""
Google Drive Only Uploader - Simplified
"""

import os
import json
import time
import threading
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Google Drive imports
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.service_account import Credentials
    DRIVE_AVAILABLE = True
except ImportError:
    DRIVE_AVAILABLE = False

from .logger import get_logger

logger = get_logger(__name__)

class DriveUploader:
    """Google Drive uploader using service account"""
    
    def __init__(self, config):
        self.config = config['services']['drive_upload']
        self.storage_config = config['storage']
        self.enabled = self.config.get('enabled', False) and DRIVE_AVAILABLE
        
        # Service account credentials
        self.credentials_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'service_account.json'
        )
        
        # Drive service
        self.drive_service = None
        self.folder_id = None
        
        # Upload queue
        self.upload_queue = Queue()
        self.upload_thread = None
        self.running = False
        
        # Tracking
        self.uploaded_files = set()
        self.upload_log = os.path.join(self.storage_config['save_dir'], 'drive_uploads.json')
        
        if not self.enabled:
            logger.warning("Google Drive upload disabled or dependencies missing")
            return
        
        logger.info("Drive uploader initialized")
    
    def start(self):
        """Start the drive upload service"""
        if not self.enabled:
            return False
        
        if not self._authenticate():
            return False
        
        if not self._setup_folder():
            return False
        
        self._load_upload_log()
        
        self.running = True
        self.upload_thread = threading.Thread(target=self._upload_worker, daemon=True)
        self.upload_thread.start()
        
        logger.info("Drive upload service started")
        return True
    
    def stop(self):
        """Stop the drive upload service"""
        self.running = False
        if self.upload_thread:
            self.upload_thread.join(timeout=5)
        logger.info("Drive upload service stopped")
    
    def _authenticate(self):
        """Authenticate with Google Drive API"""
        try:
            if not os.path.exists(self.credentials_path):
                logger.error(f"Service account credentials not found: {self.credentials_path}")
                return False
            
            credentials = Credentials.from_service_account_file(
                self.credentials_path,
                scopes=['https://www.googleapis.com/auth/drive.file']
            )
            
            self.drive_service = build('drive', 'v3', credentials=credentials)
            logger.info("Google Drive authentication successful")
            return True
            
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Drive: {e}")
            return False
    
    def _setup_folder(self):
        """Setup or find the upload folder"""
        try:
            folder_name = self.config['folder_name']
            
            # Search for existing folder
            results = self.drive_service.files().list(
                q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'",
                spaces='drive'
            ).execute()
            
            folders = results.get('files', [])
            
            if folders:
                self.folder_id = folders[0]['id']
                logger.info(f"Found existing folder: {folder_name}")
            else:
                # Create new folder
                folder_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                
                folder = self.drive_service.files().create(
                    body=folder_metadata,
                    fields='id'
                ).execute()
                
                self.folder_id = folder.get('id')
                logger.info(f"Created new folder: {folder_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup Drive folder: {e}")
            return False
    
    def _upload_worker(self):
        """Background worker for uploading files"""
        while self.running:
            try:
                file_path = self.upload_queue.get(timeout=1)
                if file_path is None:
                    break
                
                if self._upload_file(file_path):
                    self.uploaded_files.add(file_path)
                    self._save_upload_log()
                
                # Rate limiting
                time.sleep(self.config.get('upload_delay', 3))
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error in drive upload worker: {e}")
    
    def _upload_file(self, file_path):
        """Upload a single file to Google Drive"""
        try:
            if not os.path.exists(file_path):
                logger.warning(f"File not found for upload: {file_path}")
                return False
            
            filename = os.path.basename(file_path)
            
            # Check if already uploaded
            if file_path in self.uploaded_files:
                logger.debug(f"File already uploaded: {filename}")
                return True
            
            # Check if file exists in Drive
            results = self.drive_service.files().list(
                q=f"name='{filename}' and parents in '{self.folder_id}'",
                spaces='drive'
            ).execute()
            
            if results.get('files', []):
                logger.debug(f"File already exists in Drive: {filename}")
                return True
            
            # Upload file
            file_metadata = {
                'name': filename,
                'parents': [self.folder_id]
            }
            
            media = MediaFileUpload(file_path, resumable=True)
            
            file = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            
            logger.info(f"Uploaded to Drive: {filename}")
            return True
            
        except Exception as e:
            error_str = str(e)
            
            # Handle quota exceeded error specifically
            if "storageQuotaExceeded" in error_str:
                logger.error("Google Drive storage quota exceeded! Disabling Drive upload.")
                self.enabled = False
                self.running = False
                return False
            
            logger.error(f"Failed to upload {file_path}: {e}")
            return False
    
    def queue_file(self, file_path):
        """Queue a file for upload"""
        if self.enabled and self.running:
            self.upload_queue.put(file_path)
            logger.debug(f"Queued for Drive upload: {os.path.basename(file_path)}")
    
    def _load_upload_log(self):
        """Load upload log"""
        try:
            if os.path.exists(self.upload_log):
                with open(self.upload_log, 'r') as f:
                    data = json.load(f)
                    self.uploaded_files = set(data.get('uploaded_files', []))
                logger.info(f"Loaded {len(self.uploaded_files)} uploaded files from log")
        except Exception as e:
            logger.error(f"Error loading upload log: {e}")
    
    def _save_upload_log(self):
        """Save upload log"""
        try:
            data = {
                'uploaded_files': list(self.uploaded_files),
                'last_updated': datetime.now().isoformat()
            }
            with open(self.upload_log, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving upload log: {e}")
    
    def get_queue_size(self):
        """Get current upload queue size"""
        return self.upload_queue.qsize()
    
    def check_drive_quota(self):
        """Check Drive storage quota"""
        try:
            about = self.drive_service.about().get(fields='storageQuota').execute()
            quota = about.get('storageQuota', {})
            
            usage = int(quota.get('usage', 0))
            limit = int(quota.get('limit', 0))
            
            if limit > 0:
                usage_percent = (usage / limit) * 100
                logger.info(f"Drive storage: {usage_percent:.1f}% used ({usage / (1024**3):.1f}GB / {limit / (1024**3):.1f}GB)")
                
                if usage_percent > 95:
                    logger.warning("Drive storage nearly full - uploads may fail")
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"Failed to check Drive quota: {e}")
            return True  # Assume OK if we can't check

class FileWatcher(FileSystemEventHandler):
    """Watch for new image files"""
    
    def __init__(self, drive_uploader):
        self.drive_uploader = drive_uploader
        
    def on_created(self, event):
        """Handle new file creation"""
        if event.is_directory:
            return
        
        file_path = event.src_path
        
        # Check if it's an image file
        if file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
            logger.info(f"New image detected: {os.path.basename(file_path)}")
            
            # Queue for Drive upload
            if self.drive_uploader:
                self.drive_uploader.queue_file(file_path)

class CombinedUploader:
    """Drive uploader service"""
    
    def __init__(self, config):
        self.config = config
        self.storage_config = config['storage']
        
        # Create uploader
        self.drive_uploader = DriveUploader(config) if DRIVE_AVAILABLE else None
        
        # File watcher
        self.observer = None
        self.file_watcher = FileWatcher(self.drive_uploader)
        
        logger.info("Drive uploader initialized")
    
    def start(self):
        """Start upload service"""
        success = True
        
        # Start Drive uploader
        if self.drive_uploader:
            drive_success = self.drive_uploader.start()
            if not drive_success:
                logger.warning("Drive uploader failed to start")
        
        # Start file watcher if Drive uploader is working
        if self.drive_uploader:
            try:
                self.observer = Observer()
                self.observer.schedule(
                    self.file_watcher,
                    self.storage_config['save_dir'],
                    recursive=False
                )
                self.observer.start()
                logger.info("File watcher started")
            except Exception as e:
                logger.error(f"Failed to start file watcher: {e}")
                success = False
        
        return success
    
    def stop(self):
        """Stop upload service"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
        
        if self.drive_uploader:
            self.drive_uploader.stop()
        
        logger.info("Drive uploader stopped")
    
    def queue_file(self, file_path):
        """Queue file for upload"""
        if self.drive_uploader:
            self.drive_uploader.queue_file(file_path)
    
    def get_status(self):
        """Get status of upload service"""
        status = {
            'drive': {
                'enabled': self.drive_uploader is not None and self.drive_uploader.enabled,
                'queue_size': self.drive_uploader.get_queue_size() if self.drive_uploader else 0
            }
        }
        return status