#!/usr/bin/env python3
"""
Storage Cleanup Manager
"""

import os
import shutil
import glob
import json
from datetime import datetime, timedelta
from pathlib import Path
from .logger import get_logger

logger = get_logger(__name__)

class CleanupManager:
    """Manages storage cleanup and maintenance"""
    
    def __init__(self, config):
        self.config = config['storage']
        self.max_size_gb = self.config.get('max_size_gb', 5)
        self.save_dir = self.config['save_dir']
        
        logger.info(f"Cleanup manager initialized - max size: {self.max_size_gb}GB")
    
    def get_directory_size(self):
        """Get total size of save directory in GB"""
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(self.save_dir):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except (OSError, IOError):
                        continue
            
            return total_size / (1024 * 1024 * 1024)  # Convert to GB
            
        except Exception as e:
            logger.error(f"Error calculating directory size: {e}")
            return 0
    
    def get_file_count(self):
        """Get total number of image files in save directory (including subdirectories)"""
        try:
            total_count = 0
            for dirpath, dirnames, filenames in os.walk(self.save_dir):
                # Skip IdentifiedSpecies folder to preserve species gallery
                if 'IdentifiedSpecies' in dirpath:
                    continue
                for filename in filenames:
                    if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                        total_count += 1
            return total_count
        except Exception as e:
            logger.error(f"Error counting files: {e}")
            return 0
    
    def get_oldest_files(self, count=None):
        """Get oldest files sorted by creation time (including date subdirectories)"""
        try:
            all_files = []

            # Walk through all subdirectories to find image files
            for dirpath, dirnames, filenames in os.walk(self.save_dir):
                # Skip IdentifiedSpecies folder to preserve species gallery
                if 'IdentifiedSpecies' in dirpath:
                    continue

                for filename in filenames:
                    if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                        filepath = os.path.join(dirpath, filename)
                        all_files.append(filepath)
            
            # Sort by creation time (oldest first)
            all_files.sort(key=lambda x: os.path.getctime(x))
            
            if count:
                return all_files[:count]
            return all_files
            
        except Exception as e:
            logger.error(f"Error getting oldest files: {e}")
            return []
    
    def cleanup_old_files(self):
        """Clean up old files to stay within size limit"""
        try:
            current_size = self.get_directory_size()
            
            if current_size <= self.max_size_gb:
                logger.info(f"Storage within limit: {current_size:.2f}GB / {self.max_size_gb}GB")
                return {
                    'cleaned': False,
                    'files_deleted': 0,
                    'space_freed': 0,
                    'current_size': current_size
                }
            
            logger.info(f"Storage over limit: {current_size:.2f}GB / {self.max_size_gb}GB - starting cleanup")
            
            # Get all files sorted by age
            all_files = self.get_oldest_files()
            
            files_deleted = 0
            space_freed = 0
            
            # Delete oldest files until we're under the limit
            for file_path in all_files:
                if self.get_directory_size() <= self.max_size_gb * 0.9:  # Leave 10% buffer
                    break
                
                try:
                    file_size = os.path.getsize(file_path)
                    os.remove(file_path)
                    files_deleted += 1
                    space_freed += file_size
                    
                    logger.info(f"Deleted old file: {os.path.basename(file_path)}")
                    
                except Exception as e:
                    logger.error(f"Error deleting file {file_path}: {e}")
            
            # Clear system trash
            self._empty_trash()
            
            final_size = self.get_directory_size()
            
            logger.info(f"Cleanup completed - deleted {files_deleted} files, "
                       f"freed {space_freed / (1024*1024):.1f}MB, "
                       f"final size: {final_size:.2f}GB")
            
            return {
                'cleaned': True,
                'files_deleted': files_deleted,
                'space_freed': space_freed,
                'current_size': final_size
            }
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return {
                'cleaned': False,
                'files_deleted': 0,
                'space_freed': 0,
                'current_size': self.get_directory_size()
            }
    
    def _empty_trash(self):
        """Empty system trash"""
        try:
            trash_dirs = [
                os.path.expanduser("~/.local/share/Trash/files"),
                os.path.expanduser("~/.Trash"),
                "/tmp"
            ]
            
            for trash_dir in trash_dirs:
                if os.path.exists(trash_dir):
                    for item in os.listdir(trash_dir):
                        item_path = os.path.join(trash_dir, item)
                        try:
                            if os.path.isfile(item_path):
                                os.remove(item_path)
                            elif os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                        except Exception as e:
                            logger.debug(f"Could not remove trash item {item_path}: {e}")
            
            logger.info("System trash emptied")
            
        except Exception as e:
            logger.error(f"Error emptying trash: {e}")
    
    def cleanup_by_age(self, days_old=7):
        """Clean up files older than specified days (including date subdirectories)"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)

            all_files = []
            # Walk through all subdirectories to find image files
            for dirpath, dirnames, filenames in os.walk(self.save_dir):
                # Skip IdentifiedSpecies folder to preserve species gallery
                if 'IdentifiedSpecies' in dirpath:
                    continue

                for filename in filenames:
                    if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                        filepath = os.path.join(dirpath, filename)
                        all_files.append(filepath)
            
            files_deleted = 0
            space_freed = 0
            empty_dirs = set()
            
            for file_path in all_files:
                try:
                    file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                    
                    if file_time < cutoff_date:
                        file_size = os.path.getsize(file_path)
                        parent_dir = os.path.dirname(file_path)
                        os.remove(file_path)
                        files_deleted += 1
                        space_freed += file_size
                        
                        # Track potentially empty directories
                        empty_dirs.add(parent_dir)
                        
                        logger.info(f"Deleted old file: {os.path.basename(file_path)}")
                        
                except Exception as e:
                    logger.error(f"Error deleting old file {file_path}: {e}")
            
            # Clean up empty date directories
            for dir_path in empty_dirs:
                try:
                    if dir_path != self.save_dir and os.path.isdir(dir_path):
                        # Check if directory is empty (only contains non-image files like .json)
                        remaining_images = [f for f in os.listdir(dir_path) 
                                         if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp'))]
                        if not remaining_images:
                            logger.info(f"Removing empty date directory: {os.path.basename(dir_path)}")
                            import shutil
                            shutil.rmtree(dir_path)
                except Exception as e:
                    logger.error(f"Error removing empty directory {dir_path}: {e}")
            
            logger.info(f"Age cleanup completed - deleted {files_deleted} files older than {days_old} days")
            
            return {
                'files_deleted': files_deleted,
                'space_freed': space_freed
            }
            
        except Exception as e:
            logger.error(f"Error during age cleanup: {e}")
            return {
                'files_deleted': 0,
                'space_freed': 0
            }
    
    def get_storage_stats(self):
        """Get storage statistics"""
        try:
            stats = {
                'total_size_gb': self.get_directory_size(),
                'max_size_gb': self.max_size_gb,
                'file_count': self.get_file_count(),
                'usage_percent': (self.get_directory_size() / self.max_size_gb) * 100,
                'save_directory': self.save_dir
            }
            
            # Get oldest and newest files
            files = self.get_oldest_files()
            if files:
                stats['oldest_file'] = {
                    'name': os.path.basename(files[0]),
                    'date': datetime.fromtimestamp(os.path.getctime(files[0])).isoformat()
                }
                stats['newest_file'] = {
                    'name': os.path.basename(files[-1]),
                    'date': datetime.fromtimestamp(os.path.getctime(files[-1])).isoformat()
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting storage stats: {e}")
            return {
                'total_size_gb': 0,
                'max_size_gb': self.max_size_gb,
                'file_count': 0,
                'usage_percent': 0,
                'save_directory': self.save_dir
            }
    
    def run_daily_cleanup(self):
        """Run daily cleanup routine"""
        logger.info("Starting daily cleanup routine")
        
        try:
            # Get initial stats
            initial_stats = self.get_storage_stats()
            
            # Run cleanup
            cleanup_result = self.cleanup_old_files()
            
            # Run age-based cleanup (remove files older than 30 days)
            age_cleanup_result = self.cleanup_by_age(days_old=30)
            
            # Get final stats
            final_stats = self.get_storage_stats()
            
            # Create summary
            summary = {
                'timestamp': datetime.now().isoformat(),
                'initial_stats': initial_stats,
                'final_stats': final_stats,
                'cleanup_result': cleanup_result,
                'age_cleanup_result': age_cleanup_result
            }
            
            # Save summary
            summary_path = os.path.join(self.save_dir, 'cleanup_summary.json')
            with open(summary_path, 'w') as f:
                json.dump(summary, f, indent=2)
            
            logger.info("Daily cleanup routine completed")
            return summary
            
        except Exception as e:
            logger.error(f"Error during daily cleanup: {e}")
            return None

def run_cleanup_service():
    """Standalone cleanup service"""
    import json
    
    # Load config
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return
    
    # Run cleanup
    cleanup_manager = CleanupManager(config)
    result = cleanup_manager.run_daily_cleanup()
    
    if result:
        logger.info("Cleanup service completed successfully")
    else:
        logger.error("Cleanup service failed")

if __name__ == "__main__":
    # Setup logging for standalone mode
    from .logger import setup_logging
    setup_logging()
    
    run_cleanup_service()