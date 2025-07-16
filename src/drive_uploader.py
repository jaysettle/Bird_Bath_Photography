#!/usr/bin/env python3
"""
Combined Google Drive and Google Photos Uploader
"""

import os
import json
import time
import threading
import hashlib
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

# Google Photos imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials as OAuth2Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    import requests
    PHOTOS_AVAILABLE = True
except ImportError:
    PHOTOS_AVAILABLE = False

from .logger import get_logger

logger = get_logger(__name__)

class DriveUploader:
    """Google Drive uploader using service account"""
    
    def __init__(self, config):
        self.config = config['services']['drive_upload']
        self.storage_config = config['storage']
        self.enabled = self.config.get('enabled', False) and DRIVE_AVAILABLE
        
        if not self.enabled:
            logger.warning("Google Drive upload disabled or dependencies missing")
            return
        
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

class PhotosUploader:
    """Google Photos uploader using OAuth2"""
    
    def __init__(self, config):
        self.config = config['services']['photos_upload']
        self.storage_config = config['storage']
        self.enabled = self.config.get('enabled', False) and PHOTOS_AVAILABLE
        
        if not self.enabled:
            logger.warning("Google Photos upload disabled or dependencies missing")
            return
        
        # OAuth2 credentials
        self.credentials_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'client_secret.json'
        )
        self.token_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'token.pickle'
        )
        
        # Photos API
        self.credentials = None
        self.album_id = None
        
        # Upload queue
        self.upload_queue = Queue()
        self.upload_thread = None
        self.running = False
        
        # Tracking
        self.uploaded_files = set()
        self.upload_log = os.path.join(self.storage_config['save_dir'], 'photos_uploads.json')
        
        logger.info("Photos uploader initialized")
    
    def start(self):
        """Start the photos upload service"""
        if not self.enabled:
            return False
        
        if not self._authenticate():
            return False
        
        if not self._setup_album():
            return False
        
        self._load_upload_log()
        
        self.running = True
        self.upload_thread = threading.Thread(target=self._upload_worker, daemon=True)
        self.upload_thread.start()
        
        logger.info("Photos upload service started")
        return True
    
    def stop(self):
        """Stop the photos upload service"""
        self.running = False
        if self.upload_thread:
            self.upload_thread.join(timeout=5)
        logger.info("Photos upload service stopped")
    
    def _authenticate(self):
        """Authenticate with Google Photos API"""
        try:
            scopes = ['https://www.googleapis.com/auth/photoslibrary']
            
            # Load existing credentials
            if os.path.exists(self.token_path):
                import pickle
                with open(self.token_path, 'rb') as token:
                    self.credentials = pickle.load(token)
            
            # Refresh or get new credentials
            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    self.credentials.refresh(Request())
                else:
                    if not os.path.exists(self.credentials_path):
                        logger.error(f"Client secret not found: {self.credentials_path}")
                        return False
                    
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, scopes)
                    self.credentials = flow.run_local_server(port=0)
                
                # Save credentials
                import pickle
                with open(self.token_path, 'wb') as token:
                    pickle.dump(self.credentials, token)
            
            logger.info("Google Photos authentication successful")
            return True
            
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Photos: {e}")
            return False
    
    def _setup_album(self):
        """Setup or find the upload album"""
        try:
            album_name = self.config['album_name']
            
            # Search for existing album
            url = 'https://photoslibrary.googleapis.com/v1/albums'
            headers = {'Authorization': f'Bearer {self.credentials.token}'}
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                albums = response.json().get('albums', [])
                
                for album in albums:
                    if album.get('title') == album_name:
                        self.album_id = album.get('id')
                        logger.info(f"Found existing album: {album_name}")
                        return True
                
                # Create new album
                create_url = url
                create_data = {
                    'album': {
                        'title': album_name
                    }
                }
                
                response = requests.post(create_url, headers=headers, json=create_data)
                
                if response.status_code == 200:
                    self.album_id = response.json().get('id')
                    logger.info(f"Created new album: {album_name}")
                    return True
                else:
                    logger.error(f"Failed to create album: {response.text}")
                    return False
            else:
                logger.error(f"Failed to list albums: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to setup Photos album: {e}")
            return False
    
    def _upload_worker(self):
        """Background worker for uploading photos"""
        while self.running:
            try:
                file_path = self.upload_queue.get(timeout=1)
                if file_path is None:
                    break
                
                if self._upload_photo(file_path):
                    self.uploaded_files.add(file_path)
                    self._save_upload_log()
                
                # Rate limiting
                time.sleep(self.config.get('upload_delay', 3))
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error in photos upload worker: {e}")
    
    def _upload_photo(self, file_path):
        """Upload a single photo to Google Photos"""
        try:
            if not os.path.exists(file_path):
                logger.warning(f"Photo not found for upload: {file_path}")
                return False
            
            filename = os.path.basename(file_path)
            
            # Check if already uploaded
            if file_path in self.uploaded_files:
                logger.debug(f"Photo already uploaded: {filename}")
                return True
            
            # Upload photo
            headers = {
                'Authorization': f'Bearer {self.credentials.token}',
                'Content-type': 'application/octet-stream',
                'X-Goog-Upload-File-Name': filename,
                'X-Goog-Upload-Protocol': 'raw',
            }
            
            with open(file_path, 'rb') as photo_file:
                photo_data = photo_file.read()
            
            upload_url = 'https://photoslibrary.googleapis.com/v1/uploads'
            response = requests.post(upload_url, headers=headers, data=photo_data)
            
            if response.status_code == 200:
                upload_token = response.text
                
                # Create media item
                create_url = 'https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate'
                create_headers = {
                    'Authorization': f'Bearer {self.credentials.token}',
                    'Content-type': 'application/json',
                }
                
                create_data = {
                    'albumId': self.album_id,
                    'newMediaItems': [
                        {
                            'description': f'Bird detection capture - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                            'simpleMediaItem': {
                                'uploadToken': upload_token,
                                'fileName': filename
                            }
                        }
                    ]
                }
                
                response = requests.post(create_url, headers=create_headers, json=create_data)
                
                if response.status_code == 200:
                    logger.info(f"Uploaded to Photos: {filename}")
                    return True
                else:
                    logger.error(f"Failed to create media item: {response.text}")
                    return False
            else:
                logger.error(f"Failed to upload photo: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to upload photo {file_path}: {e}")
            return False
    
    def queue_photo(self, file_path):
        """Queue a photo for upload"""
        if self.enabled and self.running:
            self.upload_queue.put(file_path)
            logger.debug(f"Queued for Photos upload: {os.path.basename(file_path)}")
    
    def _load_upload_log(self):
        """Load upload log"""
        try:
            if os.path.exists(self.upload_log):
                with open(self.upload_log, 'r') as f:
                    data = json.load(f)
                    self.uploaded_files = set(data.get('uploaded_files', []))
                logger.info(f"Loaded {len(self.uploaded_files)} uploaded photos from log")
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

class FileWatcher(FileSystemEventHandler):
    """Watch for new image files"""
    
    def __init__(self, drive_uploader, photos_uploader):
        self.drive_uploader = drive_uploader
        self.photos_uploader = photos_uploader
        
    def on_created(self, event):
        """Handle new file creation"""
        if event.is_directory:
            return
        
        file_path = event.src_path
        
        # Check if it's an image file
        if file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
            logger.info(f"New image detected: {os.path.basename(file_path)}")
            
            # Queue for both services
            if self.drive_uploader:
                self.drive_uploader.queue_file(file_path)
            if self.photos_uploader:
                self.photos_uploader.queue_photo(file_path)

class CombinedUploader:
    """Combined uploader service"""
    
    def __init__(self, config):
        self.config = config
        self.storage_config = config['storage']
        
        # Create uploaders
        self.drive_uploader = DriveUploader(config) if DRIVE_AVAILABLE else None
        self.photos_uploader = PhotosUploader(config) if PHOTOS_AVAILABLE else None
        
        # File watcher
        self.observer = None
        self.file_watcher = FileWatcher(self.drive_uploader, self.photos_uploader)
        
        logger.info("Combined uploader initialized")
    
    def start(self):
        """Start all upload services"""
        success = True
        
        # Start Drive uploader
        if self.drive_uploader:
            success &= self.drive_uploader.start()
        
        # Start Photos uploader
        if self.photos_uploader:
            success &= self.photos_uploader.start()
        
        # Start file watcher
        if success and (self.drive_uploader or self.photos_uploader):
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
        """Stop all upload services"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
        
        if self.drive_uploader:
            self.drive_uploader.stop()
        
        if self.photos_uploader:
            self.photos_uploader.stop()
        
        logger.info("Combined uploader stopped")
    
    def queue_file(self, file_path):
        """Queue file for upload to both services"""
        if self.drive_uploader:
            self.drive_uploader.queue_file(file_path)
        if self.photos_uploader:
            self.photos_uploader.queue_photo(file_path)
    
    def get_status(self):
        """Get status of all upload services"""
        status = {
            'drive': {
                'enabled': self.drive_uploader is not None,
                'queue_size': self.drive_uploader.get_queue_size() if self.drive_uploader else 0
            },
            'photos': {
                'enabled': self.photos_uploader is not None,
                'queue_size': self.photos_uploader.get_queue_size() if self.photos_uploader else 0
            }
        }
        return status