#!/usr/bin/env python3
"""
Google Drive Only Uploader - Simplified
"""

import os
import json
import time
import threading
import socket
import ssl
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Fix SSL issues
try:
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
except ImportError:
    pass  # certifi not available

# Disable SSL warnings if needed (for debugging)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Google Drive imports
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    import httplib2
    DRIVE_AVAILABLE = True
except ImportError:
    DRIVE_AVAILABLE = False

from .logger import get_logger

logger = get_logger(__name__)

class DriveUploader:
    """Google Drive uploader supporting both service account and OAuth2"""
    
    def __init__(self, config):
        self.config = config['services']['drive_upload']
        self.storage_config = config['storage']
        self.enabled = self.config.get('enabled', False) and DRIVE_AVAILABLE
        
        # Only support OAuth2 authentication now
        self.auth_type = 'oauth2'
        
        # OAuth2 credential paths only
        self.client_secret_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'client_secret.json'
        )
        self.token_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'token.json'
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
        
        try:
            # Try to authenticate but don't fail if it doesn't work
            if not self._authenticate():
                logger.warning("Drive authentication failed - service will run in offline mode")
                self.enabled = False
                return False
            
            if not self._setup_folder():
                logger.warning("Drive folder setup failed - service will run in offline mode")
                self.enabled = False
                return False
            
            self._load_upload_log()
            
            self.running = True
            self.upload_thread = threading.Thread(target=self._upload_worker, daemon=True)
            self.upload_thread.start()
            
            logger.info("Drive upload service started")
            return True
            
        except Exception as e:
            logger.error(f"Drive service start failed (non-fatal): {e}")
            self.enabled = False
            # Return False but don't crash the app
            return False
    
    def stop(self):
        """Stop the drive upload service"""
        self.running = False
        if self.upload_thread:
            self.upload_thread.join(timeout=5)
        logger.info("Drive upload service stopped")
    
    def _authenticate(self):
        """Authenticate with Google Drive API using OAuth2 only"""
        try:
            return self._authenticate_oauth2()
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Drive: {e}")
            return False
    
    def _authenticate_oauth2(self):
        """Authenticate using OAuth2 for personal account"""
        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        creds = None
        
        # Token file stores the user's access and refresh tokens
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.client_secret_path):
                    logger.error(f"OAuth2 client credentials not found: {self.client_secret_path}")
                    logger.error("Please download OAuth2 credentials from Google Cloud Console")
                    return False
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secret_path, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())
        
        # Create httplib2 instance with timeout and SSL fixes
        http = httplib2.Http(
            timeout=10,  # 10 second timeout
            disable_ssl_certificate_validation=False,  # Keep SSL validation
            ca_certs=certifi.where() if 'certifi' in globals() else None
        )
        authorized_http = creds.authorize(http) if hasattr(creds, 'authorize') else http
        
        # For newer credentials, we pass them directly
        if hasattr(creds, 'authorize'):
            self.drive_service = build('drive', 'v3', http=authorized_http)
        else:
            self.drive_service = build('drive', 'v3', credentials=creds)
        logger.info("Google Drive OAuth2 authentication successful")
        return True
    
    def _setup_folder(self):
        """Setup or find the upload folder in personal Drive"""
        try:
            folder_name = self.config['folder_name']
            
            # Search for existing folder in user's personal Drive
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and 'me' in owners and trashed=false"
            
            results = self.drive_service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            folders = results.get('files', [])
            
            if folders:
                self.folder_id = folders[0]['id']
                logger.info(f"Found existing folder in personal Drive: {folder_name}")
            else:
                # Create new folder in personal Drive
                folder_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                
                folder = self.drive_service.files().create(
                    body=folder_metadata,
                    fields='id'
                ).execute()
                
                self.folder_id = folder.get('id')
                logger.info(f"Created new folder in personal Drive: {folder_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup Drive folder: {e}")
            return False
    
    def _upload_worker(self):
        """Background worker for uploading files"""
        last_reenable_check = 0
        consecutive_failures = 0
        max_backoff = 60  # Maximum backoff time in seconds
        
        while self.running:
            try:
                file_path = self.upload_queue.get(timeout=1)
                if file_path is None:
                    break
                
                # Try to re-enable service if disabled (check every 5 minutes)
                current_time = time.time()
                if not self.enabled and current_time - last_reenable_check > 300:
                    self.test_and_reenable()
                    last_reenable_check = current_time
                
                if self.enabled:
                    success = self._upload_file(file_path)
                    if success:
                        self.uploaded_files.add(file_path)
                        self._save_upload_log()
                        consecutive_failures = 0  # Reset on success
                    else:
                        consecutive_failures += 1
                        # Exponential backoff: 2^failures seconds, capped at max_backoff
                        backoff_time = min(2 ** consecutive_failures, max_backoff)
                        logger.info(f"Upload failed, backing off for {backoff_time}s")
                        time.sleep(backoff_time)
                        # Re-queue the file for retry
                        self.upload_queue.put(file_path)
                
                # Rate limiting
                time.sleep(self.config.get('upload_delay', 3))
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error in drive upload worker: {e}")
                consecutive_failures += 1
    
    def _upload_file(self, file_path):
        """Upload a single file to Google Drive with timeout"""
        try:
            if not os.path.exists(file_path):
                logger.warning(f"File not found for upload: {file_path}")
                return False
            
            filename = os.path.basename(file_path)
            
            # Check if already uploaded
            if file_path in self.uploaded_files:
                logger.debug(f"File already uploaded: {filename}")
                return True
            
            # Use ThreadPoolExecutor for timeout control
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._do_upload, file_path, filename)
                try:
                    # Wait maximum 30 seconds for upload
                    result = future.result(timeout=30)
                    if result:
                        logger.info(f"Uploaded to Drive: {filename}")
                    return result
                except TimeoutError:
                    logger.error(f"Upload timed out for {filename}")
                    return False
                except Exception as e:
                    raise  # Re-raise to be handled by outer exception handler
            
        except Exception as e:
            error_str = str(e)
            
            # Handle quota exceeded error specifically
            if "storageQuotaExceeded" in error_str:
                logger.error("Google Drive storage quota exceeded! Upload failed, but service remains enabled.")
                # Don't disable the service - just report the error
                # The service will try again with the next file
                return False
            
            # Handle SSL/network errors
            if "SSL" in error_str or "DECRYPTION_FAILED" in error_str:
                logger.warning(f"Network/SSL error uploading {file_path}: {e}")
                # These are usually temporary - retry on next file
                return False
            
            # Handle other network errors
            if "ConnectionError" in error_str or "TimeoutError" in error_str:
                logger.warning(f"Network timeout uploading {file_path}: {e}")
                return False
            
            logger.error(f"Failed to upload {file_path}: {e}")
            return False
    
    def _do_upload(self, file_path, filename):
        """Internal method to do the actual upload (called in thread)"""
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
        
        return True
    
    def queue_file(self, file_path):
        """Queue a file for upload"""
        try:
            if self.enabled and self.running:
                self.upload_queue.put(file_path)
                logger.debug(f"Queued for Drive upload: {os.path.basename(file_path)}")
        except Exception as e:
            logger.error(f"Failed to queue file (non-fatal): {e}")
            # Don't crash - just skip the upload
    
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
                free_gb = (limit - usage) / (1024**3)
                logger.info(f"Drive storage: {usage_percent:.1f}% used ({usage / (1024**3):.1f}GB / {limit / (1024**3):.1f}GB), {free_gb:.1f}GB free")
                
                # Allow uploads if we have at least 100MB free space
                if free_gb < 0.1:
                    logger.warning(f"Drive storage nearly full - only {free_gb:.1f}GB free")
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"Failed to check Drive quota: {e}")
            return True  # Assume OK if we can't check
    
    def test_and_reenable(self):
        """Test Drive access and re-enable if quota is available"""
        if not self.enabled:
            logger.info("Drive upload is disabled, checking if it can be re-enabled...")
            if self.check_drive_quota():
                self.enabled = True
                logger.info("Drive upload re-enabled - quota available")
                return True
            else:
                logger.warning("Drive upload remains disabled - quota still exceeded")
                return False
        return True
    
    def get_drive_folder_stats(self):
        """Get statistics about the Google Drive folder with timeout"""
        try:
            if not self.drive_service or not self.folder_id:
                logger.debug(f"Cannot get stats - service: {self.drive_service is not None}, folder_id: {self.folder_id}")
                return {
                    'file_count': 0,
                    'total_size': 0,
                    'latest_file': None,
                    'latest_upload_time': None
                }
            
            # Use ThreadPoolExecutor for timeout control
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._fetch_drive_stats)
                try:
                    # Wait maximum 5 seconds for the API call
                    return future.result(timeout=5)
                except TimeoutError:
                    logger.warning("Drive stats request timed out")
                    return self._get_cached_stats()
                except Exception as e:
                    logger.error(f"Error fetching drive stats: {e}")
                    return self._get_cached_stats()
                    
        except Exception as e:
            logger.error(f"Failed to get Drive folder stats: {e}")
            return self._get_cached_stats()
    
    def _fetch_drive_stats(self):
        """Internal method to fetch drive stats (called in thread)"""
        try:
            # Get all files in the folder
            results = self.drive_service.files().list(
                q=f"parents in '{self.folder_id}' and trashed=false",
                fields="files(id,name,size,createdTime,modifiedTime)",
                pageSize=1000
            ).execute()
        except Exception as e:
            # Return cached stats on error
            logger.debug(f"Error fetching drive stats, using cache: {str(e)}")
            return self._get_cached_stats()
        
        files = results.get('files', [])
        
        if not files:
            stats = {
                'file_count': 0,
                'total_size': 0,
                'latest_file': None,
                'latest_upload_time': None
            }
        else:
            # Calculate total size
            total_size = 0
            latest_file = None
            latest_time = None
            
            for file in files:
                # Add file size
                if 'size' in file:
                    total_size += int(file['size'])
                
                # Track latest file
                file_time = file.get('modifiedTime', file.get('createdTime'))
                if file_time and (latest_time is None or file_time > latest_time):
                    latest_time = file_time
                    latest_file = file['name']
            
            stats = {
                'file_count': len(files),
                'total_size': total_size,
                'latest_file': latest_file,
                'latest_upload_time': latest_time
            }
        
        # Cache the stats
        self._cached_stats = stats
        self._cache_time = time.time()
        logger.debug(f"Fetched Drive stats: {stats['file_count']} files, {stats['total_size'] / (1024**2):.1f} MB")
        return stats
    
    def _get_cached_stats(self):
        """Return cached stats if available, otherwise empty stats"""
        if hasattr(self, '_cached_stats') and hasattr(self, '_cache_time'):
            # Use cache if less than 30 seconds old
            if time.time() - self._cache_time < 30:
                return self._cached_stats
        
        return {
            'file_count': 0,
            'total_size': 0,
            'latest_file': None,
            'latest_upload_time': None
        }
    
    def get_drive_folder_url(self):
        """Get the URL to the Google Drive folder"""
        if self.folder_id:
            return f"https://drive.google.com/drive/folders/{self.folder_id}"
        return None
    
    def clear_drive_folder(self):
        """Clear all files from the Google Drive folder"""
        try:
            if not self.drive_service or not self.folder_id:
                return False
                
            # Get all files in the folder
            results = self.drive_service.files().list(
                q=f"parents in '{self.folder_id}' and trashed=false",
                fields="files(id,name)"
            ).execute()
            
            files = results.get('files', [])
            
            if not files:
                logger.info("No files to delete from Drive folder")
                return True
            
            # Delete all files
            deleted_count = 0
            for file in files:
                try:
                    self.drive_service.files().delete(fileId=file['id']).execute()
                    deleted_count += 1
                    logger.info(f"Deleted from Drive: {file['name']}")
                except Exception as e:
                    logger.error(f"Failed to delete {file['name']}: {e}")
            
            logger.info(f"Cleared {deleted_count} files from Drive folder")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear Drive folder: {e}")
            return False

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