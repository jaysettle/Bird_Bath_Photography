#!/usr/bin/env python3
"""
Standalone Google Drive OAuth Setup Script
Run this to authorize Google Drive access
"""

import os
import json
import sys
from pathlib import Path

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Error: Google API Python client not installed!")
    print("Please run: pip3 install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    sys.exit(1)

# If modifying these scopes, delete the file token.json
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def main():
    """Run the OAuth2 setup flow"""
    print("=== Google Drive OAuth Setup ===\n")
    
    # Paths
    script_dir = Path(__file__).parent
    client_secret_path = script_dir / "client_secret.json"
    token_path = script_dir / "token.json"
    
    # Check for client_secret.json
    if not client_secret_path.exists():
        print(f"ERROR: client_secret.json not found!")
        print(f"Expected location: {client_secret_path}")
        print("\nPlease follow these steps:")
        print("1. Go to https://console.cloud.google.com")
        print("2. Create a project and enable Google Drive API")
        print("3. Create OAuth2 credentials (Desktop application)")
        print("4. Download and save as client_secret.json in this directory")
        return False
        
    print(f"Found client_secret.json at: {client_secret_path}")
    
    # Check if already authorized
    if token_path.exists():
        print(f"\nFound existing token at: {token_path}")
        response = input("Do you want to re-authorize? (y/N): ")
        if response.lower() != 'y':
            print("Using existing authorization.")
            return True
            
    print("\nStarting OAuth2 authorization flow...")
    print("A browser window will open for you to authorize access.")
    print("If the browser doesn't open automatically, copy the URL shown.")
    
    try:
        # Create flow and run
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_path), SCOPES)
        
        # This will open the browser
        creds = flow.run_local_server(
            port=0,
            success_message='Authorization successful! You can close this window.'
        )
        
        # Save the credentials
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
            
        print("\n✓ Authorization successful!")
        print(f"✓ Token saved to: {token_path}")
        print("\nYou can now use Google Drive upload in the Bird Detection app!")
        return True
        
    except Exception as e:
        print(f"\nERROR during authorization: {e}")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)