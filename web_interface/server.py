#!/usr/bin/env python3
"""
Mobile Web Interface for Bird Detection System
Optimized for iPhone 16 (2556 x 1179 px)
With WebSocket support for real-time updates
"""

import os
import sys
import json
import time
import psutil
import subprocess
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, send_file, request, Response, redirect
from functools import wraps
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import logging
from threading import Thread
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

from io import BytesIO
from PIL import Image


# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ============================================
# Authentication for public-facing pages
# ============================================
# Change these credentials!
GALLERY_USERNAME = 'birds'
GALLERY_PASSWORD = 'birdwatcher'

def check_auth(username, password):
    """Check if username/password combination is valid"""
    return username == GALLERY_USERNAME and password == GALLERY_PASSWORD

def authenticate():
    """Send 401 response that enables basic auth"""
    return Response(
        'Authentication required to view the bird gallery. Please provide valid credentials.',
        401,
        {'WWW-Authenticate': 'Basic realm="Bird Gallery"'}
    )

def requires_auth(f):
    """Decorator to require authentication for a route"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated
# ============================================

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config.json"
LOGS_DIR = BASE_DIR / "logs"
SPECIES_DB_PATH = BASE_DIR / "species_database.json"

def load_config():
    """Load configuration"""
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def get_images_dir():
    """Get images directory from config"""
    try:
        config = load_config()
        return Path(config.get('storage', {}).get('save_dir', str(Path.home() / 'BirdPhotos')))
    except:
        return Path.home() / 'BirdPhotos'

IMAGES_DIR = get_images_dir()
UPLOAD_LOG = IMAGES_DIR / "drive_uploads.json"
# Thumbnail settings
THUMBNAIL_SIZE = (300, 300)
THUMBNAIL_DIR = IMAGES_DIR / ".thumbnails"

def ensure_thumbnail_dir():
    if not THUMBNAIL_DIR.exists():
        THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    return THUMBNAIL_DIR

def get_or_create_thumbnail(image_path):
    ensure_thumbnail_dir()
    rel_path = image_path.relative_to(IMAGES_DIR)
    thumb_path = THUMBNAIL_DIR / rel_path
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    if thumb_path.exists():
        if thumb_path.stat().st_mtime >= image_path.stat().st_mtime:
            return thumb_path.read_bytes()
    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=85, optimize=True)
            thumb_bytes = buffer.getvalue()
            thumb_path.write_bytes(thumb_bytes)
            return thumb_bytes
    except Exception as e:
        logger.error(f"Error creating thumbnail for {image_path}: {e}")
        return image_path.read_bytes()


# Species lookup cache
_species_cache = {}
_species_cache_time = 0

def load_species_database():
    """Load and cache species database"""
    global _species_cache, _species_cache_time
    
    try:
        if SPECIES_DB_PATH.exists():
            mtime = SPECIES_DB_PATH.stat().st_mtime
            if mtime > _species_cache_time:
                with open(SPECIES_DB_PATH, 'r') as f:
                    data = json.load(f)
                    _species_cache = {}
                    # Build reverse lookup: photo path -> species info
                    for sci_name, species_info in data.get('species', {}).items():
                        common_name = species_info.get('common_name', 'Unknown')
                        for photo_path in species_info.get('photo_gallery', []):
                            photo_name = Path(photo_path).name
                            _species_cache[photo_name] = {
                                'common_name': common_name,
                                'scientific_name': sci_name
                            }
                    _species_cache_time = mtime
                    logger.info(f"Loaded species database with {len(_species_cache)} photo mappings")
    except Exception as e:
        logger.error(f"Error loading species database: {e}")
    
    return _species_cache

def get_species_for_photo(filename):
    """Look up species info for a photo filename"""
    cache = load_species_database()
    return cache.get(filename, None)

def get_all_image_files():
    """Get all image files from root and date folders"""
    all_images = []
    if IMAGES_DIR.exists():
        # Check root directory for backward compatibility
        all_images.extend(IMAGES_DIR.glob("motion_*.jpeg"))
        
        # Check date folders (YYYY-MM-DD format)
        for date_folder in IMAGES_DIR.iterdir():
            if date_folder.is_dir() and len(date_folder.name) == 10 and date_folder.name[4] == '-' and date_folder.name[7] == '-':
                all_images.extend(date_folder.glob("motion_*.jpeg"))
    
    return sorted(all_images, key=lambda x: x.stat().st_mtime, reverse=True)

def get_recent_images(limit=20):
    """Get recent captured images from date folders"""
    images = []
    jpeg_files = get_all_image_files()[:limit]
    
    for img in jpeg_files:
        # Get relative path from IMAGES_DIR for display
        rel_path = img.relative_to(IMAGES_DIR)
        species_info = get_species_for_photo(img.name)
        images.append({
            'filename': img.name,
            'path': str(img),
            'rel_path': str(rel_path),
            'timestamp': datetime.fromtimestamp(img.stat().st_mtime).isoformat(),
            'size': img.stat().st_size,
            'species': species_info
        })
    return images

def is_date_folder(path: Path) -> bool:
    """Return True if path name matches YYYY-MM-DD format."""
    if not path.is_dir():
        return False
    name = path.name
    return (
        len(name) == 10 and
        name[4] == '-' and
        name[7] == '-' and
        name.replace('-', '').isdigit()
    )


def get_date_folders() -> list[Path]:
    """Return date folders sorted newest first."""
    if not IMAGES_DIR.exists():
        return []
    folders = [p for p in IMAGES_DIR.iterdir() if is_date_folder(p)]
    # Sort by date descending (newest first). Names are ISO formatted so lexical works.
    folders.sort(key=lambda p: p.name, reverse=True)
    return folders


def get_images_for_date(date_folder: Path) -> list[Path]:
    """Return sorted image list (newest first) for a specific date folder."""
    if not date_folder.exists() or not date_folder.is_dir():
        return []

    image_files = []
    for pattern in ('*.jpeg', '*.jpg', '*.png'):
        image_files.extend(date_folder.glob(pattern))

    # Sort newest first using modification time, fallback to name
    image_files.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    return image_files

def get_system_stats():
    """Get system statistics"""
    # CPU and Memory
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    
    # Disk usage for images directory
    disk = psutil.disk_usage(str(IMAGES_DIR))
    
    # Count all images
    total_images = len(get_all_image_files())
    
    return {
        'cpu_percent': cpu_percent,
        'memory_percent': memory.percent,
        'memory_used_gb': memory.used / (1024**3),
        'memory_total_gb': memory.total / (1024**3),
        'disk_used_gb': disk.used / (1024**3),
        'disk_total_gb': disk.total / (1024**3),
        'disk_percent': disk.percent,
        'total_images': total_images
    }

def get_drive_stats():
    """Get Google Drive upload statistics"""
    try:
        # Try to get from the uploaded files log
        if UPLOAD_LOG.exists():
            with open(UPLOAD_LOG, 'r') as f:
                data = json.load(f)
                uploaded_count = len(data.get('uploaded_files', []))
        else:
            uploaded_count = 0
            
        # Get config for folder name
        config = load_config()
        folder_name = config['services']['drive_upload'].get('folder_name', 'Unknown')
        
        return {
            'uploaded_count': uploaded_count,
            'folder_name': folder_name,
            'enabled': config['services']['drive_upload'].get('enabled', False)
        }
    except Exception as e:
        logger.error(f"Error getting drive stats: {e}")
        return {
            'uploaded_count': 0,
            'folder_name': 'Unknown',
            'enabled': False
        }

def is_main_app_running():
    """Check if main.py is running"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline', [])
            cmdline_str = ' '.join(cmdline)
            # Look for main.py in the bird detection directory
            if cmdline and 'main.py' in cmdline_str and ('BirdBath' in cmdline_str or 'python' in cmdline_str):
                return True
        except:
            pass
    return False

def is_watchdog_service_active():
    """Check if the bird-detection-watchdog service is active"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'bird-detection-watchdog.service'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0 and result.stdout.strip() == 'active'
    except Exception as e:
        logger.error(f"Error checking watchdog service: {e}")
        return False


# WebSocket file watcher
class PhotoWatcher(FileSystemEventHandler):
    """Watch for new photos and notify connected clients"""
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        if event.src_path.endswith('.jpeg') or event.src_path.endswith('.jpg'):
            # Wait a moment for file to be fully written
            time.sleep(0.5)
            
            try:
                photo_path = Path(event.src_path)
                if not photo_path.exists():
                    return
                    
                rel_path = photo_path.relative_to(IMAGES_DIR)
                species_info = get_species_for_photo(photo_path.name)
                
                photo_data = {
                    'filename': photo_path.name,
                    'rel_path': str(rel_path),
                    'timestamp': datetime.fromtimestamp(photo_path.stat().st_mtime).isoformat(),
                    'size': photo_path.stat().st_size,
                    'species': species_info
                }
                
                logger.info(f"New photo detected: {photo_path.name}")
                socketio.emit('new_photo', photo_data)
                
            except Exception as e:
                logger.error(f"Error processing new photo: {e}")


# Start file watcher
def start_photo_watcher():
    """Start watching for new photos"""
    try:
        event_handler = PhotoWatcher()
        observer = Observer()
        observer.schedule(event_handler, str(IMAGES_DIR), recursive=True)
        observer.start()
        logger.info(f"Started watching {IMAGES_DIR} for new photos")
        return observer
    except Exception as e:
        logger.error(f"Error starting photo watcher: {e}")
        return None


@app.route('/')
@requires_auth
def index():
    """Main page"""
    return render_template('index.html')

@app.route("/gallery")
@requires_auth
def gallery_redirect():
    """Redirect to main page with gallery tab"""
    return redirect("/#gallery")

@app.route('/api/status')
def api_status():
    """Get system status"""
    return jsonify({
        'app_running': is_main_app_running(),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/stats')
def api_stats():
    """Get all statistics"""
    return jsonify({
        'system': get_system_stats(),
        'drive': get_drive_stats(),
        'app_running': is_main_app_running()
    })

@app.route('/api/images')
def api_images():
    """Get recent images"""
    limit = request.args.get('limit', 20, type=int)
    return jsonify(get_recent_images(limit))



@app.route('/api/thumbnail/<path:image_path>')
@requires_auth
def api_thumbnail(image_path):
    try:
        filepath = (IMAGES_DIR / image_path).resolve()
        if not filepath.is_relative_to(IMAGES_DIR.resolve()):
            return jsonify({'error': 'Invalid path'}), 403
    except Exception:
        return jsonify({'error': 'Invalid path'}), 403

    if not filepath.exists():
        if '/' not in image_path:
            for date_folder in IMAGES_DIR.iterdir():
                if date_folder.is_dir() and len(date_folder.name) == 10 and date_folder.name[4] == '-' and date_folder.name[7] == '-':
                    date_filepath = date_folder / image_path
                    if date_filepath.exists():
                        filepath = date_filepath
                        break

    if filepath.exists() and filepath.suffix.lower() in ['.jpeg', '.jpg']:
        thumb_bytes = get_or_create_thumbnail(filepath)
        return Response(thumb_bytes, mimetype='image/jpeg')

    return jsonify({'error': 'Image not found'}), 404

@app.route('/api/gallery')
@requires_auth
def api_gallery():
    """Paginated gallery view grouped by date."""
    try:
        limit = max(1, request.args.get('limit', 20, type=int))
        offset = max(0, request.args.get('offset', 0, type=int))
        requested_date = request.args.get('date')

        date_folders = get_date_folders()
        if not date_folders:
            return jsonify({
                'success': True,
                'date': None,
                'images': [],
                'offset': 0,
                'has_more': False,
                'next_date': None,
                'available_dates': [],
                'remaining_dates': []
            })

        # Determine active date folder
        active_folder = None
        if requested_date:
            for folder in date_folders:
                if folder.name == requested_date:
                    active_folder = folder
                    break
        if active_folder is None:
            active_folder = date_folders[0]

        images_for_date = get_images_for_date(active_folder)
        total_for_date = len(images_for_date)

        # Slice for pagination
        paginated = images_for_date[offset:offset + limit]

        def to_payload(image_path: Path):
            rel_path = image_path.relative_to(IMAGES_DIR)
            stat = image_path.stat()
            species_info = get_species_for_photo(image_path.name)
            return {
                'filename': image_path.name,
                'rel_path': str(rel_path),
                'timestamp': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'size': stat.st_size,
                'species': species_info
            }

        images_payload = [to_payload(path) for path in paginated]

        new_offset = offset + len(images_payload)
        has_more = new_offset < total_for_date

        # Determine next date when this one is exhausted
        next_date = None
        remaining_dates = []
        if not has_more:
            # Build list of remaining dates after the current one
            names = [folder.name for folder in date_folders]
            try:
                idx = names.index(active_folder.name)
            except ValueError:
                idx = -1

            if idx >= 0:
                remaining_dates = names[idx + 1:]
                if remaining_dates:
                    next_date = remaining_dates[0]

        return jsonify({
            'success': True,
            'date': active_folder.name,
            'images': images_payload,
            'offset': new_offset if has_more else 0,
            'has_more': has_more,
            'next_date': next_date,
            'available_dates': [folder.name for folder in date_folders],
            'remaining_dates': remaining_dates
        })

    except Exception as exc:
        logger.error(f"Error loading gallery: {exc}")
        return jsonify({
            'success': False,
            'error': str(exc)
        }), 500



@app.route('/api/photo-counts')
@requires_auth
def api_photo_counts():
    """Get photo counts per date for calendar."""
    try:
        date_folders = get_date_folders()
        counts = {}
        for folder in date_folders:
            images = list(folder.glob('*.jpg')) + list(folder.glob('*.jpeg')) + list(folder.glob('*.png'))
            counts[folder.name] = len(images)
        return jsonify({'success': True, 'counts': counts})
    except Exception as e:
        logger.error(f"Error getting photo counts: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/clear-thumbnail-cache', methods=['POST'])
@requires_auth
def api_clear_thumbnail_cache():
    """Clear the thumbnail cache directory."""
    try:
        cache_dir = Path.home() / '.thumbnails'
        if cache_dir.exists():
            import shutil
            count = len(list(cache_dir.glob('*')))
            shutil.rmtree(cache_dir)
            cache_dir.mkdir(exist_ok=True)
            logger.info(f"Cleared {count} cached thumbnails")
            return jsonify({'success': True, 'cleared': count})
        return jsonify({'success': True, 'cleared': 0})
    except Exception as e:
        logger.error(f"Error clearing thumbnail cache: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/image/<path:image_path>')
@requires_auth
def api_image(image_path):
    """Serve an image (handles both root and date folder paths)"""
    # Validate path to prevent directory traversal
    try:
        filepath = (IMAGES_DIR / image_path).resolve()
        if not filepath.is_relative_to(IMAGES_DIR.resolve()):
            return jsonify({'error': 'Invalid path'}), 403
    except Exception:
        return jsonify({'error': 'Invalid path'}), 403
    
    if filepath.exists() and filepath.suffix.lower() in ['.jpeg', '.jpg']:
        return send_file(filepath, mimetype='image/jpeg')
    
    # If not found and no date folder in path, search date folders
    if '/' not in image_path:
        # Search in date folders
        for date_folder in IMAGES_DIR.iterdir():
            if date_folder.is_dir() and len(date_folder.name) == 10 and date_folder.name[4] == '-' and date_folder.name[7] == '-':
                date_filepath = date_folder / image_path
                if date_filepath.exists() and date_filepath.suffix.lower() in ['.jpeg', '.jpg']:
                    return send_file(date_filepath, mimetype='image/jpeg')
    
    return jsonify({'error': 'Image not found'}), 404

@app.route('/api/restart', methods=['POST'])
def api_restart():
    """Restart the main application"""
    try:
        watchdog_active = is_watchdog_service_active()
        logger.info(f"Restart requested - watchdog active: {watchdog_active}")
        
        if watchdog_active:
            # If watchdog is active, just kill the app and let watchdog restart it
            logger.info("Watchdog is active - killing app and letting watchdog restart it")
            subprocess.run(['pkill', '-f', 'main.py'], check=False)
            
            # Wait a bit for the watchdog to detect and restart
            time.sleep(5)
            
            return jsonify({
                'success': True,
                'message': 'Application killed - watchdog will restart it',
                'running': is_main_app_running(),
                'watchdog_managed': True
            })
        else:
            # If no watchdog, do manual restart
            logger.info("No watchdog - performing manual restart")
            
            # Kill existing process
            subprocess.run(['pkill', '-f', 'main.py'], check=False)
            time.sleep(2)
            
            # Start new process
            subprocess.Popen([
                'python3', 
                str(BASE_DIR / 'main.py')
            ], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            cwd=str(BASE_DIR))
            
            time.sleep(3)
            
            return jsonify({
                'success': True,
                'message': 'Application manually restarted',
                'running': is_main_app_running(),
                'watchdog_managed': False
            })
            
    except Exception as e:
        logger.error(f"Error restarting app: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'watchdog_managed': is_watchdog_service_active()
        }), 500

@app.route('/api/logs')
def api_logs():
    """Get recent log entries"""
    try:
        log_file = LOGS_DIR / "bird_detection.log"
        if log_file.exists():
            with open(log_file, 'r') as f:
                lines = f.readlines()[-50:]  # Last 50 lines
            return jsonify({
                'logs': [line.strip() for line in lines],
                'success': True
            })
    except Exception as e:
        logger.error(f"Error reading logs: {e}")
    
    return jsonify({
        'logs': [],
        'success': False
    })

@app.route('/api/camera/settings')
def api_camera_settings():
    """Get current camera settings"""
    try:
        config = load_config()
        camera_settings = config.get('camera', {})
        
        return jsonify({
            'settings': camera_settings,
            'success': True
        })
    except Exception as e:
        logger.error(f"Error getting camera settings: {e}")
        return jsonify({
            'settings': {},
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/camera/settings', methods=['POST'])
def api_update_camera_settings():
    """Update camera settings"""
    try:
        # Get the settings to update
        new_settings = request.get_json()
        if not new_settings:
            return jsonify({'success': False, 'error': 'No settings provided'}), 400
        
        # Load current config
        config = load_config()
        
        # Update camera settings
        if 'camera' not in config:
            config['camera'] = {}
        
        # Update specific settings
        for key, value in new_settings.items():
            if key in ['brightness', 'contrast', 'saturation', 'sharpness', 'exposure_compensation', 
                      'iso', 'threshold', 'min_area']:
                config['camera'][key] = value
                logger.info(f"Updated camera setting {key} to {value}")
        
        # Save config
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': 'Camera settings updated successfully',
            'settings': config['camera']
        })
        
    except Exception as e:
        logger.error(f"Error updating camera settings: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/camera/roi', methods=['GET'])
def api_get_roi():
    """Get current ROI settings"""
    try:
        config = load_config()
        roi = config.get('roi', {})
        
        return jsonify({
            'roi': roi,
            'success': True
        })
    except Exception as e:
        logger.error(f"Error getting ROI: {e}")
        return jsonify({
            'roi': {},
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/camera/roi', methods=['POST'])
def api_update_roi():
    """Update ROI settings"""
    try:
        roi_data = request.get_json()
        if not roi_data:
            return jsonify({'success': False, 'error': 'No ROI data provided'}), 400
        
        config = load_config()
        
        # Update ROI
        if 'roi' not in config:
            config['roi'] = {}
        
        config['roi'] = roi_data
        
        # Save config
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': 'ROI updated successfully',
            'roi': roi_data
        })
        
    except Exception as e:
        logger.error(f"Error updating ROI: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/camera/preview')
def api_camera_preview():
    """Get latest camera preview image"""
    try:
        # Get the most recent image
        jpeg_files = get_all_image_files()
        
        if jpeg_files:
            latest_image = jpeg_files[0]
            return send_file(latest_image, mimetype='image/jpeg')
        
        # If no images found, return a placeholder
        return jsonify({'error': 'No preview available'}), 404
        
    except Exception as e:
        logger.error(f"Error getting camera preview: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/camera/capture', methods=['POST'])
def api_camera_capture():
    """Trigger a manual camera capture"""
    try:
        # This would ideally communicate with the main app to trigger a capture
        # For now, we'll just return the latest image info
        jpeg_files = get_all_image_files()
        
        if jpeg_files:
            latest_image = jpeg_files[0]
            return jsonify({
                'success': True,
                'filename': latest_image.name,
                'timestamp': datetime.fromtimestamp(latest_image.stat().st_mtime).isoformat(),
                'message': 'Latest capture available'
            })
        
        return jsonify({
            'success': False,
            'error': 'No images available'
        }), 404
        
    except Exception as e:
        logger.error(f"Error triggering capture: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/species')
def species_page():
    """Species gallery page"""
    return render_template('species.html')

@app.route('/api/species')
def api_species():
    """Get bird species data with IdentifiedSpecies folder photos"""
    try:
        species_db_path = BASE_DIR / "species_database.json"
        identified_species_dir = IMAGES_DIR / "IdentifiedSpecies"
        
        species_data = {}
        
        if species_db_path.exists():
            with open(species_db_path, 'r') as f:
                data = json.load(f)
                species_data = data.get('species', {})
        
        # Enhance species data with IdentifiedSpecies folder photos
        enhanced_species = {}
        
        for scientific_name, species_info in species_data.items():
            enhanced_info = species_info.copy()
            
            # Get photos from IdentifiedSpecies folder
            common_name = species_info.get('common_name', 'Unknown')
            folder_name = f"{common_name}_{scientific_name}".replace(' ', '_').replace('/', '_')
            folder_name = ''.join(c for c in folder_name if c.isalnum() or c in ['_', '-'])
            
            species_folder = identified_species_dir / folder_name
            identified_photos = []
            
            if species_folder.exists():
                # Get all JPEG files, sorted by modification time (newest first)
                photo_files = list(species_folder.glob('*.jpeg'))
                photo_files.extend(species_folder.glob('*.jpg'))
                photo_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                
                for photo_file in photo_files:
                    # Create relative path for web serving
                    rel_path = f"identified_species/{folder_name}/{photo_file.name}"
                    identified_photos.append({
                        'path': rel_path,
                        'timestamp': photo_file.stat().st_mtime,
                        'filename': photo_file.name
                    })
            
            enhanced_info['identified_photos'] = identified_photos
            enhanced_info['photo_count'] = len(identified_photos)
            enhanced_species[scientific_name] = enhanced_info
        
        # Calculate summary stats
        total_species = len(enhanced_species)
        total_sightings = 0
        if species_db_path.exists():
            with open(species_db_path, 'r') as f:
                data = json.load(f)
                total_sightings = len(data.get('sightings', []))
        
        return jsonify({
            'success': True,
            'total_species': total_species,
            'total_sightings': total_sightings,
            'species_list': enhanced_species,
            'recent_sightings': data.get('sightings', [])[-10:] if 'data' in locals() else []
        })
            
    except Exception as e:
        logger.error(f"Error getting species data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/identified_species/<species_folder>/<filename>')
def serve_identified_species_photo(species_folder, filename):
    """Serve photos from IdentifiedSpecies folder"""
    try:
        photo_path = IMAGES_DIR / "IdentifiedSpecies" / species_folder / filename
        if photo_path.exists():
            return send_file(photo_path)
        else:
            return "Photo not found", 404
    except Exception as e:
        logger.error(f"Error serving identified species photo: {e}")
        return "Error serving photo", 500

@app.route('/identified_species_thumb/<species_folder>/<filename>')
def serve_identified_species_thumbnail(species_folder, filename):
    """Serve thumbnail of photos from IdentifiedSpecies folder"""
    try:
        photo_path = IMAGES_DIR / "IdentifiedSpecies" / species_folder / filename
        if photo_path.exists():
            thumb_bytes = get_or_create_thumbnail(photo_path)
            return Response(thumb_bytes, mimetype='image/jpeg')
        else:
            return "Photo not found", 404
    except Exception as e:
        logger.error(f"Error serving identified species thumbnail: {e}")
        return "Error serving thumbnail", 500

def find_available_port(start_port=8080, max_attempts=10):
    """Find an available port starting from start_port"""
    import socket
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                return port
        except OSError:
            continue
    return None


@app.route('/api/email-image', methods=['POST'])
def api_email_image():
    """Email a specific image to the configured recipient"""
    try:
        data = request.get_json()
        image_path = data.get('image_path')

        if not image_path:
            return jsonify({'success': False, 'error': 'No image path provided'}), 400

        # Construct full path
        full_path = IMAGES_DIR / image_path
        if not full_path.exists():
            return jsonify({'success': False, 'error': 'Image not found'}), 404

        # Load email configuration
        config = load_config()
        email_config = config.get('email', {})

        if not email_config.get('sender') or not email_config.get('password'):
            return jsonify({'success': False, 'error': 'Email not configured'}), 400

        # Get recipient
        receivers = email_config.get('receivers', {})
        recipient = receivers.get('primary', email_config.get('sender'))

        # Get species info for the image
        species_info = get_species_for_photo(full_path.name)
        species_name = species_info.get('common_name', 'Bird') if species_info else 'Bird'

        # Send email directly without importing email_handler
        subject = f"Bird Photo: {species_name}"
        body = f"Photo captured: {full_path.name}\nSpecies: {species_name}"

        # Create message
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = email_config['sender']
        msg['To'] = recipient
        msg.attach(MIMEText(body, 'plain'))

        # Attach the image
        with open(full_path, 'rb') as f:
            img = MIMEImage(f.read())
            img.add_header('Content-Disposition', 'attachment', filename=full_path.name)
            msg.attach(img)

        # Send email via SMTP
        smtp_server = email_config.get('smtp_server', 'smtp.gmail.com')
        smtp_port = email_config.get('smtp_port', 465)

        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(email_config['sender'], email_config['password'])
            server.send_message(msg)

        logger.info(f"Email sent to {recipient}")
        return jsonify({'success': True, 'message': f'Email sent to {recipient}'})

    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/email-species-image', methods=['POST'])
@requires_auth
def api_email_species_image():
    """Email a species image with species name in subject"""
    try:
        data = request.get_json()
        image_path = data.get('image_path')
        species_name = data.get('species_name', 'Bird')

        if not image_path:
            return jsonify({'success': False, 'error': 'No image path provided'}), 400

        # Construct full path
        full_path = IMAGES_DIR / image_path
        if not full_path.exists():
            return jsonify({'success': False, 'error': 'Image not found'}), 404

        # Load email configuration
        config = load_config()
        email_config = config.get('email', {})

        if not email_config.get('sender') or not email_config.get('password'):
            return jsonify({'success': False, 'error': 'Email not configured'}), 400

        # Get recipient
        receivers = email_config.get('receivers', {})
        recipient = receivers.get('primary', email_config.get('sender'))

        # Create email with species name in subject
        subject = f"Bird Photo: {species_name}"
        body = f"Species: {species_name}\nPhoto: {full_path.name}"

        # Create message
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = email_config['sender']
        msg['To'] = recipient
        msg.attach(MIMEText(body, 'plain'))

        # Attach the image
        with open(full_path, 'rb') as f:
            img = MIMEImage(f.read())
            img.add_header('Content-Disposition', 'attachment', filename=full_path.name)
            msg.attach(img)

        # Send email via SMTP
        smtp_server = email_config.get('smtp_server', 'smtp.gmail.com')
        smtp_port = email_config.get('smtp_port', 465)

        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(email_config['sender'], email_config['password'])
            server.send_message(msg)

        logger.info(f"Species email sent to {recipient}: {species_name}")
        return jsonify({'success': True, 'message': f'Email sent to {recipient}'})

    except Exception as e:
        logger.error(f"Error sending species email: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/debug')
@requires_auth
def debug_gallery():
    return render_template('debug.html')

@app.route('/live')
@requires_auth
def live_gallery():
    """Live gallery page with auto-refresh"""
    return render_template('live_gallery.html')

@app.route('/api/latest')
@requires_auth
def api_latest():
    """Get the single most recent photo - for polling"""
    try:
        jpeg_files = get_all_image_files()
        if jpeg_files:
            latest = jpeg_files[0]
            rel_path = latest.relative_to(IMAGES_DIR)
            species_info = get_species_for_photo(latest.name)
            return jsonify({
                'success': True,
                'photo': {
                    'filename': latest.name,
                    'rel_path': str(rel_path),
                    'timestamp': datetime.fromtimestamp(latest.stat().st_mtime).isoformat(),
                    'species': species_info
                }
            })
        return jsonify({'success': True, 'photo': None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# WebSocket events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info('Client connected')
    emit('status', {'connected': True, 'message': 'Connected to bird gallery'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info('Client disconnected')


if __name__ == '__main__':
    # Start the photo watcher
    try:
        from watchdog.observers import Observer
        observer = start_photo_watcher()
    except ImportError:
        logger.warning("watchdog not installed, file watching disabled")
        observer = None
    
    # Find available port
    port = find_available_port(8080)
    if port is None:
        print("ERROR: No available ports found in range 8080-8089", file=sys.stderr)
        sys.exit(1)
    
    print(f"Starting server on port {port}")
    # Run with SocketIO
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
