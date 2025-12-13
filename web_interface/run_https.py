#!/usr/bin/env python3
"""
HTTPS wrapper for Bird Gallery server using Tailscale certs
"""

import ssl
import os
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import app, socketio, start_photo_watcher

CERT_DIR = Path('/home/jaysettle/BirdApp/certs')
CERT_FILE = CERT_DIR / 'raspberry5.crt'
KEY_FILE = CERT_DIR / 'raspberry5.key'

def main():
    # Start the photo watcher
    try:
        from watchdog.observers import Observer
        observer = start_photo_watcher()
        print('Photo watcher started')
    except ImportError:
        print('watchdog not installed, file watching disabled')
        observer = None
    
    # Check for certs
    if CERT_FILE.exists() and KEY_FILE.exists():
        print(f'Starting HTTPS server with Tailscale certs on port 8443')
        print(f'Access at: https://raspberry5.tail23d264.ts.net:8443')
        
        # Run with SSL on port 8443 (no root required)
        socketio.run(
            app, 
            host='0.0.0.0', 
            port=8443,
            debug=False, 
            allow_unsafe_werkzeug=True,
            ssl_context=(str(CERT_FILE), str(KEY_FILE))
        )
    else:
        print(f'Certs not found at {CERT_DIR}, falling back to HTTP')
        socketio.run(
            app, 
            host='0.0.0.0', 
            port=8080,
            debug=False, 
            allow_unsafe_werkzeug=True
        )

if __name__ == '__main__':
    main()
