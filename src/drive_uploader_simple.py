#!/usr/bin/env python3
"""
Google Drive Multi-Process Uploader
Uses worker pool to prevent GUI freezing
"""

import os
import json
import time
import multiprocessing
import queue
import threading
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import logging

# Fix SSL issues
try:
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
except ImportError:
    pass

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

# Constants
WORKER_POOL_SIZE = 2  # Max 2 workers to stay under rate limits
MIN_UPLOAD_DELAY = 0.4  # 400ms between uploads
MAX_RETRIES = 3
BACKOFF_BASE = 2
RATE_LIMIT_COOLDOWN = 60  # seconds to wait after rate limit
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Configure multiprocessing logging
multiprocessing.log_to_stderr(logging.INFO)

@dataclass
class UploadTask:
    """Represents a file upload task"""
    file_path: str
    task_id: str
    retry_count: int = 0
    
@dataclass
class UploadResult:
    """Result of an upload attempt"""
    task_id: str
    success: bool
    file_path: str
    error: Optional[str] = None
    file_id: Optional[str] = None

def worker_process(
    task_queue: multiprocessing.Queue,
    result_queue: multiprocessing.Queue,
    status_queue: multiprocessing.Queue,
    config: Dict[str, Any],
    worker_id: int,
    stop_event: multiprocessing.Event
):
    """Worker process that handles file uploads"""
    # Create logger for this process
    logger = get_logger(f"DriveWorker-{worker_id}")
    logger.info(f"Worker {worker_id} starting...")
    
    # Initialize Drive service
    drive_service = None
    folder_id = None
    last_upload_time = 0
    
    try:
        # Authenticate and setup
        logger.info(f"Worker {worker_id}: Authenticating with Google Drive...")
        drive_service, folder_id = setup_drive_service(config, logger)
        if not drive_service:
            logger.error(f"Worker {worker_id}: Failed to setup Drive service")
            status_queue.put({"worker_id": worker_id, "status": "failed", "error": "Authentication failed"})
            return
            
        logger.info(f"Worker {worker_id}: Ready to process uploads")
        status_queue.put({"worker_id": worker_id, "status": "ready"})
        
        # Process tasks
        while not stop_event.is_set():
            try:
                # Get task with timeout
                task = task_queue.get(timeout=1)
                
                # Rate limiting
                time_since_last = time.time() - last_upload_time
                if time_since_last < MIN_UPLOAD_DELAY:
                    sleep_time = MIN_UPLOAD_DELAY - time_since_last
                    logger.debug(f"Worker {worker_id}: Rate limiting, sleeping {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                
                # Upload file
                logger.info(f"Worker {worker_id}: Uploading {task.file_path}")
                status_queue.put({
                    "worker_id": worker_id, 
                    "status": "uploading", 
                    "file": os.path.basename(task.file_path)
                })
                
                result = upload_file(drive_service, folder_id, task, logger)
                last_upload_time = time.time()
                
                # Send result
                result_queue.put(result)
                
                if result.success:
                    logger.info(f"Worker {worker_id}: Successfully uploaded {task.file_path}")
                    status_queue.put({
                        "worker_id": worker_id,
                        "status": "completed",
                        "file": os.path.basename(task.file_path)
                    })
                else:
                    logger.error(f"Worker {worker_id}: Failed to upload {task.file_path}: {result.error}")
                    
                    # Check for rate limit
                    if "rate limit" in str(result.error).lower() or "429" in str(result.error):
                        logger.warning(f"Worker {worker_id}: Rate limit hit, cooling down for {RATE_LIMIT_COOLDOWN}s")
                        status_queue.put({
                            "worker_id": worker_id,
                            "status": "rate_limited"
                        })
                        time.sleep(RATE_LIMIT_COOLDOWN)
                        
                        # Re-queue the task
                        if task.retry_count < MAX_RETRIES:
                            task.retry_count += 1
                            task_queue.put(task)
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker {worker_id}: Unexpected error: {e}")
                status_queue.put({
                    "worker_id": worker_id,
                    "status": "error",
                    "error": str(e)
                })
                
    except Exception as e:
        logger.error(f"Worker {worker_id}: Fatal error: {e}")
        status_queue.put({
            "worker_id": worker_id,
            "status": "crashed",
            "error": str(e)
        })
    finally:
        logger.info(f"Worker {worker_id} shutting down")

def setup_drive_service(config: Dict[str, Any], logger):
    """Setup Google Drive service with OAuth2"""
    try:
        # Paths
        token_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'token.json'
        )
        client_secret_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'client_secret.json'
        )
        
        # Load credentials
        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            
        # Refresh if needed
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired credentials")
            creds.refresh(Request())
            
        if not creds or not creds.valid:
            logger.error("No valid credentials available")
            return None, None
            
        # Build service
        service = build('drive', 'v3', credentials=creds)
        
        # Get or create folder
        folder_name = config['services']['drive_upload']['folder_name']
        folder_id = get_or_create_folder(service, folder_name, logger)
        
        return service, folder_id
        
    except Exception as e:
        logger.error(f"Failed to setup Drive service: {e}")
        return None, None

def get_or_create_folder(service, folder_name: str, logger):
    """Get existing folder or create new one"""
    try:
        # Search for existing folder
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and 'me' in owners and trashed=false"
        results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        folders = results.get('files', [])
        
        if folders:
            folder_id = folders[0]['id']
            logger.info(f"Found existing folder: {folder_name} (ID: {folder_id})")
            return folder_id
        else:
            # Create new folder
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = service.files().create(body=folder_metadata, fields='id').execute()
            folder_id = folder.get('id')
            logger.info(f"Created new folder: {folder_name} (ID: {folder_id})")
            return folder_id
            
    except Exception as e:
        logger.error(f"Failed to get/create folder: {e}")
        return None

def upload_file(service, folder_id: str, task: UploadTask, logger) -> UploadResult:
    """Upload a single file to Drive"""
    try:
        if not os.path.exists(task.file_path):
            return UploadResult(
                task_id=task.task_id,
                success=False,
                file_path=task.file_path,
                error="File not found"
            )
            
        filename = os.path.basename(task.file_path)
        
        # Check if file already exists
        query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
        results = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
        existing = results.get('files', [])
        
        if existing:
            logger.debug(f"File already exists in Drive: {filename}")
            return UploadResult(
                task_id=task.task_id,
                success=True,
                file_path=task.file_path,
                file_id=existing[0]['id']
            )
        
        # Upload file
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        
        media = MediaFileUpload(task.file_path, resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        return UploadResult(
            task_id=task.task_id,
            success=True,
            file_path=task.file_path,
            file_id=file.get('id')
        )
        
    except Exception as e:
        error_str = str(e)
        logger.error(f"Upload failed for {task.file_path}: {error_str}")
        
        return UploadResult(
            task_id=task.task_id,
            success=False,
            file_path=task.file_path,
            error=error_str
        )

class DriveUploader:
    """Multi-process Google Drive uploader"""
    
    def __init__(self, config):
        self.config = config
        self.enabled = config['services']['drive_upload'].get('enabled', False) and DRIVE_AVAILABLE
        self.logger = get_logger(__name__)
        
        # Multiprocessing components
        self.manager = multiprocessing.Manager()
        self.task_queue = self.manager.Queue()
        self.result_queue = self.manager.Queue()
        self.status_queue = self.manager.Queue()
        self.stop_event = self.manager.Event()
        
        # Worker pool
        self.workers = []
        self.monitor_thread = None
        self.scanner_thread = None
        self.running = False
        
        # Periodic scan settings
        self.scan_interval = 600  # 10 minutes
        self.scan_stop_event = threading.Event()
        
        # Cleanup settings
        self.cleanup_time = config['services']['drive_upload'].get('cleanup_time', '23:30')
        self.max_size_gb = config['services']['drive_upload'].get('max_size_gb', 2)
        self.cleanup_thread = None
        self.cleanup_stop_event = threading.Event()
        
        # Upload tracking
        self.upload_log = os.path.join(
            config['storage']['save_dir'], 
            'drive_uploads.json'
        )
        self.uploaded_files = set()
        self._load_upload_log()
        
        # Task tracking
        self.pending_tasks = {}
        self.task_counter = 0
        
        # Stats
        self.stats = {
            'queued': 0,
            'uploading': 0,
            'completed': 0,
            'failed': 0,
            'rate_limited': 0
        }
        
        if not self.enabled:
            self.logger.warning("Google Drive upload disabled or dependencies missing")
            
        self.logger.info("Multi-process Drive uploader initialized")
    
    def start(self):
        """Start the upload service"""
        if not self.enabled:
            return False
            
        try:
            self.logger.info("Starting Drive upload service...")
            self.running = True
            self.stop_event.clear()
            
            # Start worker processes
            for i in range(WORKER_POOL_SIZE):
                worker = multiprocessing.Process(
                    target=worker_process,
                    args=(
                        self.task_queue,
                        self.result_queue,
                        self.status_queue,
                        self.config,
                        i,
                        self.stop_event
                    )
                )
                worker.start()
                self.workers.append(worker)
                self.logger.info(f"Started worker process {i} (PID: {worker.pid})")
            
            # Start monitor thread
            self.monitor_thread = threading.Thread(target=self._monitor_workers, daemon=True)
            self.monitor_thread.start()
            
            # Start scanner thread
            self.scan_stop_event.clear()
            self.scanner_thread = threading.Thread(target=self._periodic_scanner, daemon=True)
            self.scanner_thread.start()
            
            # Start cleanup scheduler thread
            self.cleanup_stop_event.clear()
            self.cleanup_thread = threading.Thread(target=self._cleanup_scheduler, daemon=True)
            self.cleanup_thread.start()
            
            # Do initial scan
            threading.Thread(target=self.scan_now, daemon=True).start()
            
            self.logger.info("Drive upload service started successfully with periodic scanning and cleanup")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start Drive service: {e}")
            self.enabled = False
            return False
    
    def stop(self):
        """Stop the upload service"""
        self.logger.info("Stopping Drive upload service...")
        self.running = False
        self.stop_event.set()
        self.scan_stop_event.set()
        self.cleanup_stop_event.set()
        
        # Wait for scanner thread to finish
        if self.scanner_thread and self.scanner_thread.is_alive():
            self.scanner_thread.join(timeout=2)
        
        # Wait for cleanup thread to finish
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            self.cleanup_thread.join(timeout=2)
        
        # Wait for workers to finish
        for worker in self.workers:
            worker.join(timeout=5)
            if worker.is_alive():
                self.logger.warning(f"Force terminating worker {worker.pid}")
                worker.terminate()
                
        self.workers.clear()
        
        # Save upload log
        self._save_upload_log()
        
        self.logger.info("Drive upload service stopped")
    
    def queue_file(self, file_path: str):
        """Queue a file for upload"""
        if not self.enabled or not self.running:
            return
            
        # Check if already uploaded
        if file_path in self.uploaded_files:
            self.logger.debug(f"File already uploaded: {file_path}")
            return
            
        # Create task
        self.task_counter += 1
        task = UploadTask(
            file_path=file_path,
            task_id=f"task_{self.task_counter}"
        )
        
        # Add to queue
        self.task_queue.put(task)
        self.pending_tasks[task.task_id] = task
        self.stats['queued'] += 1
        
        self.logger.info(f"Queued file for upload: {os.path.basename(file_path)}")
    
    def _monitor_workers(self):
        """Monitor worker status and results"""
        while self.running:
            try:
                # Check results
                try:
                    result = self.result_queue.get_nowait()
                    self._handle_result(result)
                except queue.Empty:
                    pass
                
                # Check status updates
                try:
                    status = self.status_queue.get_nowait()
                    self._handle_status(status)
                except queue.Empty:
                    pass
                
                time.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"Monitor thread error: {e}")
    
    def _handle_result(self, result: UploadResult):
        """Handle upload result"""
        if result.task_id in self.pending_tasks:
            del self.pending_tasks[result.task_id]
            
        if result.success:
            self.uploaded_files.add(result.file_path)
            self.stats['completed'] += 1
            self.logger.info(f"Upload completed: {os.path.basename(result.file_path)}")
        else:
            self.stats['failed'] += 1
            self.logger.error(f"Upload failed: {os.path.basename(result.file_path)} - {result.error}")
    
    def _handle_status(self, status: Dict[str, Any]):
        """Handle worker status update"""
        worker_id = status.get('worker_id', -1)
        status_type = status.get('status', 'unknown')
        
        self.logger.debug(f"Worker {worker_id} status: {status_type}")
        
        if status_type == 'uploading':
            self.stats['uploading'] += 1
        elif status_type == 'rate_limited':
            self.stats['rate_limited'] += 1
        elif status_type == 'error':
            self.logger.error(f"Worker {worker_id} error: {status.get('error', 'Unknown')}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        return {
            'enabled': self.enabled,
            'running': self.running,
            'workers': len(self.workers),
            'queue_size': self.task_queue.qsize() if self.running else 0,
            'stats': self.stats.copy(),
            'uploaded_count': len(self.uploaded_files)
        }
    
    def _load_upload_log(self):
        """Load previously uploaded files"""
        try:
            if os.path.exists(self.upload_log):
                with open(self.upload_log, 'r') as f:
                    data = json.load(f)
                    self.uploaded_files = set(data.get('uploaded_files', []))
                    self.logger.info(f"Loaded {len(self.uploaded_files)} uploaded files from log")
        except Exception as e:
            self.logger.error(f"Error loading upload log: {e}")
    
    def _save_upload_log(self):
        """Save uploaded files list"""
        try:
            with open(self.upload_log, 'w') as f:
                json.dump({
                    'uploaded_files': list(self.uploaded_files),
                    'last_saved': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving upload log: {e}")
    
    def _periodic_scanner(self):
        """Periodically scan for new files to upload"""
        self.logger.info(f"Starting periodic file scanner (every {self.scan_interval/60:.0f} minutes)")
        
        while self.running and not self.scan_stop_event.is_set():
            try:
                # Wait for scan interval (10 minutes) but check stop event frequently
                for _ in range(self.scan_interval):
                    if self.scan_stop_event.wait(1):  # Check every second
                        return
                    if not self.running:
                        return
                
                if not self.enabled:
                    continue
                
                self.logger.info("Periodic scan: checking for new files...")
                self.scan_now()
                
            except Exception as e:
                self.logger.error(f"Error in periodic scanner: {e}")
    
    def scan_now(self):
        """Scan for new files to upload"""
        if not self.enabled or not self.running:
            return
            
        self.logger.info("Scanning for new files...")
        
        try:
            save_dir = Path(self.config['storage']['save_dir'])
            image_extensions = ('.jpg', '.jpeg', '.png')
            
            new_count = 0
            for ext in image_extensions:
                for file_path in save_dir.glob(f'*{ext}'):
                    if str(file_path) not in self.uploaded_files:
                        self.queue_file(str(file_path))
                        new_count += 1
                        
                for file_path in save_dir.glob(f'*{ext.upper()}'):
                    if str(file_path) not in self.uploaded_files:
                        self.queue_file(str(file_path))
                        new_count += 1
                        
            self.logger.info(f"Found {new_count} new files to upload")
            
        except Exception as e:
            self.logger.error(f"Error scanning for files: {e}")
    
    def _cleanup_scheduler(self):
        """Daily cleanup scheduler"""
        self.logger.info(f"Starting Google Drive cleanup scheduler (daily at {self.cleanup_time})")
        
        while self.running and not self.cleanup_stop_event.is_set():
            try:
                # Parse cleanup time
                hour, minute = map(int, self.cleanup_time.split(':'))
                
                # Wait until cleanup time each day
                import datetime
                now = datetime.datetime.now()
                cleanup_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                # If cleanup time has passed today, schedule for tomorrow
                if now >= cleanup_today:
                    cleanup_today += datetime.timedelta(days=1)
                
                # Calculate seconds until cleanup
                seconds_until_cleanup = (cleanup_today - now).total_seconds()
                
                self.logger.info(f"Next Google Drive cleanup scheduled for {cleanup_today.strftime('%Y-%m-%d %H:%M')}")
                
                # Wait until cleanup time (check every minute for stop signal)
                for _ in range(int(seconds_until_cleanup // 60)):
                    if self.cleanup_stop_event.wait(60):  # Check every minute
                        return
                    if not self.running:
                        return
                
                # Wait remaining seconds
                remaining_seconds = seconds_until_cleanup % 60
                if remaining_seconds > 0:
                    if self.cleanup_stop_event.wait(remaining_seconds):
                        return
                    if not self.running:
                        return
                
                # Execute cleanup
                if self.enabled:
                    self.logger.info("Starting Google Drive cleanup...")
                    self._cleanup_drive_folder()
                
            except Exception as e:
                self.logger.error(f"Error in cleanup scheduler: {e}")
                # Wait 1 hour before retrying
                if self.cleanup_stop_event.wait(3600):
                    return
    
    def _cleanup_drive_folder(self):
        """Clean up Google Drive folder to respect max size limit"""
        try:
            # Get folder stats
            stats = self._fetch_drive_stats()
            current_size_gb = stats['total_size'] / (1024**3)
            
            self.logger.info(f"Current Drive folder size: {current_size_gb:.2f} GB, limit: {self.max_size_gb} GB")
            
            if current_size_gb <= self.max_size_gb:
                self.logger.info("Drive folder within size limit - no cleanup needed")
                return
            
            # Need to cleanup - delete oldest files first
            self.logger.info(f"Drive folder exceeds limit by {current_size_gb - self.max_size_gb:.2f} GB - starting cleanup")
            
            # Get all files sorted by creation time (oldest first)
            files = self._get_drive_files_sorted_by_date()
            
            if not files:
                self.logger.warning("No files found in Drive folder for cleanup")
                return
            
            # Calculate target size to clean up to 90% of limit to avoid frequent cleanups
            target_size_gb = self.max_size_gb * 0.9
            size_to_delete_gb = current_size_gb - target_size_gb
            
            deleted_count = 0
            deleted_size = 0
            
            for file_info in files:
                if deleted_size >= size_to_delete_gb * (1024**3):
                    break
                
                try:
                    # Delete file from Drive
                    self._delete_drive_file(file_info['id'], file_info['name'])
                    
                    # Remove from upload tracking
                    local_path = self._find_local_file_path(file_info['name'])
                    if local_path and local_path in self.uploaded_files:
                        self.uploaded_files.remove(local_path)
                    
                    deleted_size += int(file_info.get('size', 0))
                    deleted_count += 1
                    
                    self.logger.info(f"Deleted from Drive: {file_info['name']} ({file_info.get('size', 0)} bytes)")
                    
                except Exception as e:
                    self.logger.error(f"Failed to delete {file_info['name']}: {e}")
            
            # Save updated upload log
            self._save_upload_log()
            
            self.logger.info(f"Cleanup completed: deleted {deleted_count} files ({deleted_size / (1024**3):.2f} GB)")
            
        except Exception as e:
            self.logger.error(f"Error during Drive cleanup: {e}")
    
    def _get_drive_files_sorted_by_date(self):
        """Get all files in Drive folder sorted by creation date (oldest first)"""
        try:
            # Get folder ID
            drive_service, folder_id = setup_drive_service(self.config, self.logger)
            if not drive_service or not folder_id:
                return []
            
            # Get all files in the folder
            results = drive_service.files().list(
                q=f"parents in '{folder_id}' and trashed=false",
                fields="files(id,name,size,createdTime,modifiedTime)",
                orderBy="createdTime",
                pageSize=1000
            ).execute()
            
            files = results.get('files', [])
            return files
            
        except Exception as e:
            self.logger.error(f"Error getting Drive files for cleanup: {e}")
            return []
    
    def _delete_drive_file(self, file_id, filename):
        """Delete a file from Google Drive"""
        try:
            drive_service, _ = setup_drive_service(self.config, self.logger)
            if not drive_service:
                raise Exception("Could not get Drive service")
            
            drive_service.files().delete(fileId=file_id).execute()
            self.logger.debug(f"Successfully deleted {filename} from Drive")
            
        except Exception as e:
            self.logger.error(f"Failed to delete {filename} from Drive: {e}")
            raise
    
    def _find_local_file_path(self, filename):
        """Find the local path for a filename"""
        try:
            save_dir = Path(self.config['storage']['save_dir'])
            for file_path in save_dir.glob(filename):
                return str(file_path)
            return None
        except Exception:
            return None
    
    def _fetch_drive_stats(self):
        """Fetch Drive folder statistics"""
        try:
            # Get folder ID
            drive_service, folder_id = setup_drive_service(self.config, self.logger)
            if not drive_service or not folder_id:
                return {
                    'file_count': 0,
                    'total_size': 0,
                    'latest_file': None,
                    'latest_upload_time': None
                }
            
            # Get all files in the folder
            results = drive_service.files().list(
                q=f"parents in '{folder_id}' and trashed=false",
                fields="files(id,name,size,createdTime,modifiedTime)",
                pageSize=1000
            ).execute()
        
            files = results.get('files', [])
            
            if not files:
                return {
                    'file_count': 0,
                    'total_size': 0,
                    'latest_file': None,
                    'latest_upload_time': None
                }
            
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
            
            return {
                'file_count': len(files),
                'total_size': total_size,
                'latest_file': latest_file,
                'latest_upload_time': latest_time
            }
            
        except Exception as e:
            self.logger.error(f"Error fetching Drive stats: {e}")
            return {
                'file_count': 0,
                'total_size': 0,
                'latest_file': None,
                'latest_upload_time': None
            }
    
    # Stub methods for compatibility
    def get_drive_folder_stats(self):
        """Get folder statistics"""
        try:
            if not self.enabled or not self.running:
                return {
                    'file_count': 0,
                    'total_size': 0,
                    'latest_file': None,
                    'latest_upload_time': None
                }
            
            # Use the existing fetch method
            return self._fetch_drive_stats()
            
        except Exception as e:
            self.logger.error(f"Error getting Drive folder stats: {e}")
            return {
                'file_count': 0,
                'total_size': 0,
                'latest_file': None,
                'latest_upload_time': None
            }
    
    def get_queue_size(self):
        """Get current queue size"""
        return self.task_queue.qsize() if self.running else 0
    
    def clear_drive_folder(self):
        """Clear drive folder (not implemented in multiprocess version)"""
        self.logger.warning("Clear drive folder not implemented in multiprocess version")
        return False
    
    def get_drive_folder_url(self):
        """Get drive folder URL (stub)"""
        return "https://drive.google.com"

class CombinedUploader:
    """Combined uploader for compatibility"""
    
    def __init__(self, config):
        self.config = config
        self.drive_uploader = DriveUploader(config) if DRIVE_AVAILABLE else None
        self.logger = get_logger(__name__)
        
    def start(self):
        """Start upload service"""
        if self.drive_uploader:
            return self.drive_uploader.start()
        return False
    
    def stop(self):
        """Stop upload service"""
        if self.drive_uploader:
            self.drive_uploader.stop()
    
    def queue_file(self, file_path):
        """Queue file for upload"""
        if self.drive_uploader:
            self.drive_uploader.queue_file(file_path)
    
    def get_status(self):
        """Get current status"""
        if self.drive_uploader:
            stats = self.drive_uploader.get_stats()
            # Format for compatibility with main.py expectations
            return {
                'drive': {
                    'enabled': stats['enabled'],
                    'queue_size': stats['queue_size']
                }
            }
        return {
            'drive': {
                'enabled': False,
                'queue_size': 0
            }
        }