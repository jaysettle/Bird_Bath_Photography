#!/usr/bin/env python3
"""
Mobile Web Interface for Bird Detection System
Optimized for iPhone 16 (2556 x 1179 px)
"""

import os
import sys
import json
import time
import psutil
import subprocess
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, send_file, request
from flask_cors import CORS
import logging

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config.json"
LOGS_DIR = BASE_DIR / "logs"

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

def get_recent_images(limit=20):
    """Get recent captured images"""
    images = []
    if IMAGES_DIR.exists():
        jpeg_files = sorted(IMAGES_DIR.glob("motion_*.jpeg"), 
                          key=lambda x: x.stat().st_mtime, 
                          reverse=True)[:limit]
        
        for img in jpeg_files:
            images.append({
                'filename': img.name,
                'path': str(img),
                'timestamp': datetime.fromtimestamp(img.stat().st_mtime).isoformat(),
                'size': img.stat().st_size
            })
    return images

def get_system_stats():
    """Get system statistics"""
    # CPU and Memory
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    
    # Disk usage for images directory
    disk = psutil.disk_usage(str(IMAGES_DIR))
    
    # Count images
    total_images = len(list(IMAGES_DIR.glob("motion_*.jpeg"))) if IMAGES_DIR.exists() else 0
    
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

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

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

@app.route('/api/image/<filename>')
def api_image(filename):
    """Serve an image"""
    filepath = IMAGES_DIR / filename
    if filepath.exists() and filepath.suffix == '.jpeg':
        return send_file(filepath, mimetype='image/jpeg')
    return jsonify({'error': 'Image not found'}), 404

@app.route('/api/restart', methods=['POST'])
def api_restart():
    """Restart the main application"""
    try:
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
            'message': 'Application restarted',
            'running': is_main_app_running()
        })
    except Exception as e:
        logger.error(f"Error restarting app: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
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
        if IMAGES_DIR.exists():
            jpeg_files = sorted(IMAGES_DIR.glob("motion_*.jpeg"), 
                              key=lambda x: x.stat().st_mtime, 
                              reverse=True)
            
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
        if IMAGES_DIR.exists():
            jpeg_files = sorted(IMAGES_DIR.glob("motion_*.jpeg"), 
                              key=lambda x: x.stat().st_mtime, 
                              reverse=True)
            
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
    """Get bird species data"""
    try:
        species_db_path = BASE_DIR / "species_database.json"
        if species_db_path.exists():
            with open(species_db_path, 'r') as f:
                data = json.load(f)
                
            # Calculate summary stats
            total_species = len(data.get('species', {}))
            total_sightings = len(data.get('sightings', []))
            
            return jsonify({
                'success': True,
                'total_species': total_species,
                'total_sightings': total_sightings,
                'species_list': data.get('species', {}),
                'recent_sightings': data.get('sightings', [])[-10:]  # Last 10 sightings
            })
        else:
            return jsonify({
                'success': True,
                'total_species': 0,
                'total_sightings': 0,
                'species_list': {},
                'recent_sightings': []
            })
            
    except Exception as e:
        logger.error(f"Error getting species data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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

if __name__ == '__main__':
    # Find available port
    port = find_available_port(8080)
    if port is None:
        print("ERROR: No available ports found in range 8080-8089", file=sys.stderr)
        sys.exit(1)
    
    print(f"Starting server on port {port}")
    # Run on all interfaces so it's accessible from iPhone
    app.run(host='0.0.0.0', port=port, debug=False)