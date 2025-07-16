#!/usr/bin/env python3
"""
Script to clean up Google Drive to free up space
"""

import os
import sys
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from googleapiclient.discovery import build
    from google.oauth2.service_account import Credentials
    DRIVE_AVAILABLE = True
except ImportError:
    print("Google API libraries not available")
    DRIVE_AVAILABLE = False

def authenticate():
    """Authenticate with Google Drive"""
    try:
        credentials_path = 'service_account.json'
        if not os.path.exists(credentials_path):
            print(f"Service account credentials not found: {credentials_path}")
            return None
        
        credentials = Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        
        service = build('drive', 'v3', credentials=credentials)
        print("✓ Google Drive authentication successful")
        return service
        
    except Exception as e:
        print(f"✗ Failed to authenticate with Google Drive: {e}")
        return None

def get_drive_usage(service):
    """Get Drive storage usage"""
    try:
        about = service.about().get(fields='storageQuota').execute()
        quota = about.get('storageQuota', {})
        
        usage = int(quota.get('usage', 0))
        limit = int(quota.get('limit', 0))
        
        if limit > 0:
            usage_percent = (usage / limit) * 100
            print(f"Drive storage: {usage_percent:.1f}% used ({usage / (1024**3):.1f}GB / {limit / (1024**3):.1f}GB)")
            return usage, limit, usage_percent
        else:
            print("Could not get storage quota information")
            return 0, 0, 0
            
    except Exception as e:
        print(f"Failed to get Drive usage: {e}")
        return 0, 0, 0

def find_bird_folder(service):
    """Find the Bird Detection Images folder"""
    try:
        results = service.files().list(
            q="name='Bird Detection Images' and mimeType='application/vnd.google-apps.folder'",
            spaces='drive'
        ).execute()
        
        folders = results.get('files', [])
        if folders:
            folder_id = folders[0]['id']
            print(f"✓ Found Bird Detection Images folder: {folder_id}")
            return folder_id
        else:
            print("✗ Bird Detection Images folder not found")
            return None
            
    except Exception as e:
        print(f"Error finding folder: {e}")
        return None

def list_old_files(service, folder_id, days_old=30):
    """List files older than specified days"""
    try:
        cutoff_date = datetime.now() - timedelta(days=days_old)
        cutoff_str = cutoff_date.strftime('%Y-%m-%dT%H:%M:%S')
        
        results = service.files().list(
            q=f"parents in '{folder_id}' and createdTime < '{cutoff_str}'",
            orderBy='createdTime',
            fields='files(id, name, createdTime, size)',
            pageSize=100
        ).execute()
        
        files = results.get('files', [])
        print(f"Found {len(files)} files older than {days_old} days")
        
        return files
        
    except Exception as e:
        print(f"Error listing old files: {e}")
        return []

def delete_files(service, files, max_delete=50):
    """Delete specified files"""
    deleted_count = 0
    total_size = 0
    
    for file in files[:max_delete]:
        try:
            service.files().delete(fileId=file['id']).execute()
            
            file_size = int(file.get('size', 0))
            total_size += file_size
            deleted_count += 1
            
            print(f"✓ Deleted: {file['name']} ({file_size / (1024*1024):.1f}MB)")
            
        except Exception as e:
            print(f"✗ Failed to delete {file['name']}: {e}")
    
    print(f"\nSummary:")
    print(f"  Deleted: {deleted_count} files")
    print(f"  Space freed: {total_size / (1024*1024):.1f}MB")
    
    return deleted_count, total_size

def main():
    """Main cleanup function"""
    if not DRIVE_AVAILABLE:
        print("Google Drive API not available")
        return
    
    print("Google Drive Cleanup Tool")
    print("=" * 30)
    
    # Authenticate
    service = authenticate()
    if not service:
        return
    
    # Get current usage
    usage, limit, usage_percent = get_drive_usage(service)
    
    if usage_percent < 90:
        print("Drive storage is not critically full. No cleanup needed.")
        return
    
    # Find bird folder
    folder_id = find_bird_folder(service)
    if not folder_id:
        return
    
    # List old files
    print(f"\nLooking for files older than 30 days...")
    old_files = list_old_files(service, folder_id, days_old=30)
    
    if not old_files:
        print("No old files found to delete")
        return
    
    # Ask for confirmation
    print(f"\nFound {len(old_files)} old files to delete")
    response = input("Delete these files? (y/N): ").lower()
    
    if response != 'y':
        print("Cleanup cancelled")
        return
    
    # Delete files
    print("\nDeleting old files...")
    deleted_count, total_size = delete_files(service, old_files, max_delete=100)
    
    # Check final usage
    print(f"\nChecking final usage...")
    final_usage, final_limit, final_percent = get_drive_usage(service)
    
    if final_percent < 95:
        print("✓ Drive cleanup successful! You can re-enable uploads in config.json")
    else:
        print("⚠ Drive is still nearly full. Consider deleting more files manually.")

if __name__ == "__main__":
    main()