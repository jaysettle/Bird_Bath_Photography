#!/usr/bin/env python3
"""Photo gallery tab for viewing captured images"""

from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                            QLabel, QPushButton, QCheckBox, QScrollArea,
                            QProgressBar, QMessageBox, QFrame, QApplication)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QPixmap

from src.logger import get_logger
from src.threads import GalleryLoader
from src.ui.dialogs import ImageViewerDialog

logger = get_logger(__name__)


class GalleryTab(QWidget):
    """Photo gallery tab for viewing all captured images"""
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.selected_items = set()
        self.current_full_image = None
        self.email_handler = None  # Will be set from main window
        self.loader_thread = None
        self.images_by_date = {}
        self.date_widgets = {}
        self.gallery_items = []
        self.loaded_dates = set()  # Track which dates have been loaded
        self.today_date = datetime.now().strftime('%Y-%m-%d')
        self.current_focus_index = -1  # Track currently focused item for arrow navigation
        self.initial_batch_size = 200  # Images to load for the newest day
        self.scroll_batch_size = 200   # Images to load per scroll batch
        self.scroll_trigger_percent = 80  # Threshold percentage to trigger lazy load
        self.setup_ui()
        
        # Mark that gallery hasn't been loaded yet (lazy loading)
        self.gallery_loaded = False
        
        # Log configuration details
        storage_config = self.config.get('storage', {})
        save_dir = storage_config.get('save_dir', str(Path.home() / 'BirdPhotos'))
        logger.info(f"Gallery initialized - Storage config: {storage_config}")
        logger.info(f"Gallery will look for photos in: {save_dir}")
        logger.info(f"Today's date for gallery: {self.today_date}")
        
        # Setup timer to check for new images in today's folder only
        self.new_image_timer = QTimer()
        self.new_image_timer.timeout.connect(self.check_for_new_images)
        self.new_image_timer.start(10000)  # Check every 10 seconds
    
    def closeEvent(self, event):
        """Clean up when gallery tab is closed"""
        if self.loader_thread and self.loader_thread.isRunning():
            self.loader_thread.stop()
            self.loader_thread.wait(1000)  # Wait up to 1 second
        if hasattr(self, 'new_image_timer'):
            self.new_image_timer.stop()
        super().closeEvent(event)
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        # Refresh button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_gallery)
        toolbar_layout.addWidget(self.refresh_btn)
        
        # Selection info
        self.selection_label = QLabel("0 selected")
        toolbar_layout.addWidget(self.selection_label)
        
        # Email button
        self.email_btn = QPushButton("Email Selected")
        self.email_btn.clicked.connect(self.email_selected)
        self.email_btn.setEnabled(False)
        toolbar_layout.addWidget(self.email_btn)
        
        # Delete button
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.clicked.connect(self.delete_selected)
        self.delete_btn.setEnabled(False)
        toolbar_layout.addWidget(self.delete_btn)
        
        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)
        
        # Progress bar for loading
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        
        # Gallery scroll area
        self.scroll_area = QScrollArea()
        self.scroll_widget = QWidget()
        self.gallery_layout = QGridLayout(self.scroll_widget)
        self.gallery_layout.setSpacing(10)
        
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area)
        
        # Connect scroll event for lazy loading
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.on_scroll_changed)
        
        # Status label at bottom
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("QLabel { color: #666; padding: 5px; }")
        layout.addWidget(self.status_label)
        
        # Enable keyboard shortcuts
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def set_status_message(self, message, color=None):
        """Set status message with optional color"""
        self.status_label.setText(message)
        if color:
            self.status_label.setStyleSheet(f"QLabel {{ color: {color}; padding: 5px; }}")
        else:
            # Reset to default gray
            self.status_label.setStyleSheet("QLabel { color: #666; padding: 5px; }")
        
    def keyPressEvent(self, event):
        """Handle keyboard events"""
        if event.key() == Qt.Key.Key_Delete and self.selected_items:
            self.delete_selected()
        elif event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Select all
            self.select_all()
        elif event.key() == Qt.Key.Key_Escape:
            # Clear selection
            self.clear_selection()
        elif event.key() == Qt.Key.Key_Left:
            # Navigate to previous image
            self.navigate_image(-1)
        elif event.key() == Qt.Key.Key_Right:
            # Navigate to next image
            self.navigate_image(1)
        else:
            # Call parent implementation for other keys
            super().keyPressEvent(event)
    
    def navigate_image(self, direction):
        """Navigate through gallery images with arrow keys"""
        if not self.gallery_items:
            return
        
        # If no current focus, start with first item
        if self.current_focus_index == -1:
            self.current_focus_index = 0
        else:
            # Move focus in the specified direction
            new_index = self.current_focus_index + direction
            # Wrap around at boundaries
            if new_index < 0:
                new_index = len(self.gallery_items) - 1
            elif new_index >= len(self.gallery_items):
                new_index = 0
            self.current_focus_index = new_index
        
        # Update visual focus and scroll to item
        self.update_focus_highlight()
        self.scroll_to_focused_item()
        
        logger.debug(f"Navigated to image {self.current_focus_index + 1} of {len(self.gallery_items)}")
    
    def update_focus_highlight(self):
        """Update the visual highlight for the currently focused item"""
        # Remove highlight from all items
        for i, (path, widget) in enumerate(self.gallery_items):
            if i == self.current_focus_index:
                # Add highlight to focused item
                widget.setStyleSheet("""
                    QWidget {
                        border: 3px solid #4CAF50;
                        border-radius: 8px;
                        background-color: rgba(76, 175, 80, 0.1);
                    }
                """)
            else:
                # Remove highlight from non-focused items
                widget.setStyleSheet("""
                    QWidget {
                        border: 1px solid #444;
                        border-radius: 8px;
                        background-color: #2b2b2b;
                    }
                """)
    
    def scroll_to_focused_item(self):
        """Scroll the gallery to show the currently focused item"""
        if self.current_focus_index >= 0 and self.current_focus_index < len(self.gallery_items):
            path, widget = self.gallery_items[self.current_focus_index]
            # Ensure the widget is visible in the scroll area
            self.scroll_area.ensureWidgetVisible(widget)
    
    def on_image_clicked(self, image_path):
        """Handle image click - set focus and show full image"""
        # Find the index of the clicked image
        for i, (path, widget) in enumerate(self.gallery_items):
            if path == image_path:
                self.current_focus_index = i
                break
        
        # Update visual focus
        self.update_focus_highlight()
        
        # Set focus to the gallery tab for keyboard navigation
        self.setFocus()
        
        # Show full image
        self.show_full_image(image_path)
        
        logger.debug(f"Image clicked: {image_path}, focus set to index {self.current_focus_index}")
            
    
    def refresh_gallery(self):
        """Refresh the gallery - reload all loaded dates"""
        try:
            logger.info("Gallery refresh button clicked")
            self.set_status_message("Refreshing gallery...", "#ffcc00")
            
            # Show progress bar
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Refreshing gallery...")
            
            # Count images before refresh
            old_total_images = sum(len(images) for images in self.images_by_date.values())
            logger.info(f"Images before refresh: {old_total_images}")
            
            # If gallery was never loaded, just load today's photos
            if not self.gallery_loaded:
                logger.info("Gallery never loaded, loading today's photos")
                self.load_today_photos()
                self.gallery_loaded = True
                return
            
            # Save dates to reload before clearing
            loaded_dates_copy = self.loaded_dates.copy() if self.loaded_dates else {self.today_date}
            
            # Clear current display
            self.clear_gallery()
            self.images_by_date.clear()
            self.date_widgets.clear()
            self.gallery_items.clear()
            self.selected_items.clear()
            # Don't clear loaded_dates yet - we need it for reload
            self.current_focus_index = -1  # Reset focus
            # Clear loaded image tracking so images can be reloaded
            if hasattr(self, 'loaded_image_paths'):
                self.loaded_image_paths.clear()
            if hasattr(self, 'date_load_info'):
                self.date_load_info.clear()
            self.update_selection_label()
            logger.info(f"Reloading dates: {loaded_dates_copy}")
            
            storage_dir = Path(self.config.get('storage', {}).get('save_dir', 
                                               str(Path.home() / 'BirdPhotos')))
            
            # Clear loaded_dates now that we have the copy
            self.loaded_dates.clear()
            
            if storage_dir.exists():
                # Reload each date that was previously loaded
                for date_str in sorted(loaded_dates_copy, reverse=True):
                    date_folder = storage_dir / date_str
                    if date_folder.exists() and date_folder.is_dir():
                        logger.info(f"Reloading date: {date_str}")
                        self.load_date_folder(date_str, date_folder, limit=self.initial_batch_size)
                        self.loaded_dates.add(date_str)
                    else:
                        logger.warning(f"Date folder no longer exists: {date_folder}")
            
            # Check if we should auto-load yesterday (if today has < 16 photos)
            today_count = len(self.images_by_date.get(self.today_date, []))
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
            logger.info(f"Refresh auto-load check: today_count={today_count}, yesterday='{yesterday}', loaded_dates={self.loaded_dates}")
            
            if today_count > 0 and today_count < 16 and yesterday not in self.loaded_dates:
                yesterday_folder = storage_dir / yesterday
                logger.info(f"Checking yesterday folder: {yesterday_folder}, exists={yesterday_folder.exists()}")
                if yesterday_folder.exists() and yesterday_folder.is_dir():
                    logger.info(f"Auto-loading yesterday's photos (today has only {today_count})...")
                    self.set_status_message(f"Loading more photos (today has only {today_count})...", "#ffcc00")
                    self.progress_bar.setFormat("Loading yesterday's photos...")
                    QApplication.processEvents()  # Force UI update
                    
                    # Load yesterday's photos
                    self.load_date_folder(yesterday, yesterday_folder, limit=self.initial_batch_size)
                    self.loaded_dates.add(yesterday)
                    logger.info(f"Yesterday photos loaded via refresh, loaded_dates now: {self.loaded_dates}")
            
            # Count images after potential yesterday load
            new_total_images = sum(len(images) for images in self.images_by_date.values())
            logger.info(f"Images after refresh: {new_total_images}")
            
            # Update status
            if new_total_images == 0:
                # No images found at all
                self.status_label.setText("No images found in gallery")
                self.set_status_message("No images found - gallery may be empty", "#ff9800")
                # Show empty message in gallery
                empty_label = QLabel("No bird photos found.\nPhotos will appear here after motion detection captures.")
                empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                empty_label.setStyleSheet("color: #999; font-size: 14px; padding: 50px;")
                self.gallery_layout.addWidget(empty_label)
            elif new_total_images == old_total_images and old_total_images > 0 and today_count >= 16:
                # No new images found, show "up to date" message temporarily
                self.status_label.setText("Gallery is up to date")
                QTimer.singleShot(2000, lambda: self.status_label.setText(f"{new_total_images} images from {len(self.images_by_date)} days"))
            else:
                self.status_label.setText(f"{new_total_images} images from {len(self.images_by_date)} days")
            
            # Hide progress bar
            self.progress_bar.setVisible(False)
            
        except Exception as e:
            logger.error(f"Error refreshing gallery: {e}")
            self.set_status_message("Error refreshing gallery", "#ff6464")
    
    def load_today_photos(self):
        """Load only today's photos on startup"""
        try:
            # Show loading status immediately
            self.set_status_message("Loading gallery...", "#ffcc00")
            QApplication.processEvents()  # Force UI update
            
            # Show progress bar
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Scanning for photos...")
            
            storage_dir = Path(self.config.get('storage', {}).get('save_dir', 
                                               str(Path.home() / 'BirdPhotos')))
            
            logger.info(f"Gallery looking for photos in: {storage_dir}")
            
            if not storage_dir.exists():
                logger.warning(f"Photos directory does not exist: {storage_dir}")
                self.status_label.setText("No photos directory found")
                # Hide progress bar
                self.progress_bar.setVisible(False)
                return
            
            # Load only today's folder
            today_folder = storage_dir / self.today_date
            logger.info(f"Looking for today's folder: {today_folder}")
            
            if today_folder.exists() and today_folder.is_dir():
                logger.info(f"Loading photos from: {today_folder}")
                self.set_status_message("Loading today's photos...", "#ffcc00")
                QApplication.processEvents()  # Force UI update
                
                self.load_date_folder(self.today_date, today_folder, limit=self.initial_batch_size)
                self.loaded_dates.add(self.today_date)
                
                # Check if we should load yesterday too (if today has < 16 photos)
                today_count = len(self.images_by_date.get(self.today_date, []))
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                
                logger.info(f"Auto-load check: today_count={today_count}, yesterday='{yesterday}', loaded_dates={self.loaded_dates}")
                
                if today_count < 16 and yesterday not in self.loaded_dates:
                    yesterday_folder = storage_dir / yesterday
                    logger.info(f"Checking yesterday folder: {yesterday_folder}, exists={yesterday_folder.exists()}")
                    if yesterday_folder.exists() and yesterday_folder.is_dir():
                        logger.info(f"Today only has {today_count} photos, loading yesterday's photos too...")
                        self.set_status_message(f"Loading more photos (today has only {today_count})...", "#ffcc00")
                        self.progress_bar.setFormat("Loading yesterday's photos...")
                        QApplication.processEvents()  # Force UI update
                        
                        # Load yesterday's photos (first batch)
                        has_more = self.load_date_folder(
                            yesterday,
                            yesterday_folder,
                            limit=self.initial_batch_size,
                            offset=0
                        )
                        self.loaded_dates.add(yesterday)
                        logger.info(
                            f"Yesterday photos loaded ({self.initial_batch_size} images), has_more={has_more}"
                        )
                else:
                    logger.info(f"Not loading yesterday: count check={today_count < 16}, not in loaded={yesterday not in self.loaded_dates}")
                
                # Update status with final count
                total_images = sum(len(images) for images in self.images_by_date.values())
                self.status_label.setText(f"Loaded {total_images} images from {len(self.images_by_date)} days")
                # Hide progress bar
                self.progress_bar.setVisible(False)
            else:
                logger.info(f"No photos folder for today: {today_folder}")
                
                # Try to load yesterday's photos instead
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                yesterday_folder = storage_dir / yesterday
                
                if yesterday_folder.exists() and yesterday_folder.is_dir():
                    logger.info(f"Loading yesterday's photos from: {yesterday_folder}")
                    self.set_status_message("No photos today - loading yesterday's photos...", "#ffcc00")
                    self.progress_bar.setFormat("Loading yesterday's photos...")
                    
                    # Create and start loader thread for yesterday
                    self.loader_thread = GalleryLoaderThread(yesterday_folder)
                    self.loader_thread.image_loaded.connect(self.on_image_loaded)
                    self.loader_thread.progress.connect(self.on_loader_progress)
                    self.loader_thread.finished_loading.connect(self.on_loading_finished)
                    self.loader_thread.start()
                else:
                    self.status_label.setText("No photos for today or yesterday")
                    # Hide progress bar
                    self.progress_bar.setVisible(False)
                
        except Exception as e:
            logger.error(f"Error loading today's photos: {e}")
            self.set_status_message("Error loading photos", "#ff6464")
    
    def load_date_folder(self, date_str, folder_path, limit=None, offset=0):
        """Load photos from a specific date folder with pagination
        
        Args:
            date_str: Date string (YYYY-MM-DD)
            folder_path: Path to the folder
            limit: Maximum number of images to load (defaults to scroll batch size)
            offset: Starting offset for loading (default 0)
        """
        try:
            if limit is None:
                limit = self.scroll_batch_size

            logger.info(f"Loading date folder: {date_str} from path: {folder_path} (limit={limit}, offset={offset})")
            
            # Create date section if it doesn't exist
            if date_str not in self.date_widgets:
                logger.info(f"Creating new date section for: {date_str}")
                self.create_date_section(date_str)
                self.images_by_date[date_str] = []
            
            # Track loaded image paths per date
            if not hasattr(self, 'loaded_image_paths'):
                self.loaded_image_paths = {}
            if date_str not in self.loaded_image_paths:
                self.loaded_image_paths[date_str] = set()
            
            # Get existing images for this date
            existing_paths = self.loaded_image_paths[date_str]
            logger.info(f"Already loaded images for {date_str}: {len(existing_paths)}")
            
            # Search for image files with multiple extensions
            image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp']
            all_images = []
            
            for ext in image_extensions:
                found_images = list(folder_path.glob(f'**/{ext}'))
                all_images.extend(found_images)
                logger.info(f"Found {len(found_images)} {ext} files in {folder_path}")
            
            logger.info(f"Total image files found in {folder_path}: {len(all_images)}")
            
            # Sort images by modification time (newest first)
            sorted_images = sorted(all_images, key=lambda p: p.stat().st_mtime, reverse=True)
            
            # Get the batch to load based on offset and limit
            batch_images = sorted_images[offset:offset + limit]
            logger.info(f"Loading batch: {len(batch_images)} images from offset {offset}")

            # Load new images with memory management
            import time
            batch_start_time = time.time()
            new_images = 0

            logger.info(f"[GALLERY-LOAD] Starting batch load of {len(batch_images)} images")

            for idx, image_path in enumerate(batch_images):

                logger.debug(f"Processing image: {image_path}")
                if str(image_path) not in existing_paths:
                    try:
                        # Load and add image with explicit memory management
                        img_start = time.time()
                        pixmap = QPixmap(str(image_path))
                        pixmap_time = time.time() - img_start

                        if not pixmap.isNull():
                            # Create smaller thumbnail to save memory
                            scale_start = time.time()
                            scaled_pixmap = pixmap.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio,
                                                        Qt.TransformationMode.FastTransformation)
                            scale_time = time.time() - scale_start

                            # Explicitly delete the original large pixmap
                            del pixmap

                            add_start = time.time()
                            self.add_image_to_gallery(date_str, image_path, scaled_pixmap)
                            add_time = time.time() - add_start

                            self.loaded_image_paths[date_str].add(str(image_path))
                            new_images += 1

                            total_img_time = time.time() - img_start
                            if total_img_time > 0.1:  # Log slow image loads
                                logger.warning(f"[GALLERY-LOAD] Slow image {idx}/{len(batch_images)}: {total_img_time:.3f}s (pixmap:{pixmap_time:.3f}s, scale:{scale_time:.3f}s, add:{add_time:.3f}s)")

                            logger.debug(f"Added image to gallery: {image_path}")

                            # Periodic garbage collection every 12 images
                            if new_images % 12 == 0:
                                gc_start = time.time()
                                import gc
                                gc.collect()
                                QApplication.processEvents()  # Keep UI responsive
                                gc_time = time.time() - gc_start
                                logger.info(f"[GALLERY-LOAD] Progress: {new_images}/{len(batch_images)} loaded, GC+processEvents took {gc_time:.3f}s")
                        else:
                            logger.warning(f"Failed to load pixmap for: {image_path}")
                    except Exception as e:
                        logger.error(f"Error loading image {image_path}: {e}")
                else:
                    logger.debug(f"Image already loaded: {image_path}")
            
            batch_total_time = time.time() - batch_start_time
            logger.info(f"[GALLERY-LOAD] Batch complete: {new_images} images loaded in {batch_total_time:.3f}s ({batch_total_time/max(1, new_images):.3f}s per image)")
            logger.info(f"Added {new_images} new images for date {date_str}")

            # Update status
            total_images = sum(len(images) for images in self.images_by_date.values())
            self.status_label.setText(f"{total_images} images from {len(self.images_by_date)} days")
            logger.info(f"Gallery now has {total_images} total images from {len(self.images_by_date)} days")
            
            # Store info about remaining images for this date
            if not hasattr(self, 'date_load_info'):
                self.date_load_info = {}
            self.date_load_info[date_str] = {
                'total': len(sorted_images),
                'loaded': len(self.loaded_image_paths[date_str]),
                'has_more': (offset + limit) < len(sorted_images)
            }
            
            # Return whether there are more images to load
            has_more = (offset + limit) < len(sorted_images)
            logger.info(f"Date {date_str}: loaded {len(self.loaded_image_paths[date_str])}/{len(sorted_images)} images, has_more={has_more}")
            return has_more
            
        except Exception as e:
            logger.error(f"Error loading date folder {date_str}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def add_image_to_gallery(self, date_str, image_path, scaled_pixmap):
        """Add a single image to the gallery"""
        logger.debug(f"Adding image to gallery UI: {image_path} for date {date_str}")
        
        # Get the date section info
        if date_str not in self.date_widgets:
            logger.error(f"Date section {date_str} not found in date_widgets")
            return
            
        date_info = self.date_widgets[date_str]
        if not isinstance(date_info, dict) or 'widget' not in date_info:
            logger.error(f"Invalid date_info structure for {date_str}: {type(date_info)} - {date_info}")
            return
            
        grid_widget = date_info['widget']
        if not hasattr(grid_widget, 'layout'):
            logger.error(f"Grid widget for {date_str} has no layout method: {type(grid_widget)}")
            return
            
        grid_layout = grid_widget.layout()
        
        # Get current number of images for this date
        images_in_date = len(self.images_by_date[date_str])
        
        # Calculate position in the grid (4 columns)
        col = images_in_date % 4
        row = images_in_date // 4
        
        logger.debug(f"Adding image to date {date_str} grid at row {row}, col {col}")
        
        # Create gallery item
        item_widget = self.create_gallery_item(str(image_path), scaled_pixmap)
        grid_layout.addWidget(item_widget, row, col)
        
        # Update tracking
        self.images_by_date[date_str].append(str(image_path))
        self.gallery_items.append((str(image_path), item_widget))
        
        logger.debug(f"Gallery now has {len(self.gallery_items)} total items")
    
    def check_for_new_images(self):
        """Check for new images in today's folder only"""
        try:
            # Skip auto-refresh until initial gallery load has occurred
            if not getattr(self, 'gallery_loaded', False):
                return

            storage_dir = Path(self.config.get('storage', {}).get('save_dir', 
                                               str(Path.home() / 'BirdPhotos')))
            
            if not storage_dir.exists():
                return
            
            # Update today's date in case we crossed midnight
            self.today_date = datetime.now().strftime('%Y-%m-%d')
            
            # Check today's folder
            today_folder = storage_dir / self.today_date
            if today_folder.exists() and today_folder.is_dir():
                # Count current images on disk (match supported extensions)
                image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp']
                images_on_disk = 0
                for ext in image_extensions:
                    images_on_disk += len(list(today_folder.glob(f'**/{ext}')))

                current_loaded = len(self.images_by_date.get(self.today_date, []))
                date_info = getattr(self, 'date_load_info', {}).get(self.today_date, {})
                known_total = date_info.get('total', current_loaded)

                # Only load when new captures increase total files beyond what we've already catalogued
                if images_on_disk > known_total:
                    new_images = images_on_disk - known_total
                    logger.info(f"Detected {new_images} new files for today")
                    load_limit = min(self.scroll_batch_size, new_images)
                    self.load_date_folder(
                        self.today_date,
                        today_folder,
                        limit=load_limit,
                        offset=0
                    )

        except Exception as e:
            logger.error(f"Error checking for new images: {e}")
    
    def add_new_image_immediately(self, image_path):
        """Add a new image immediately when captured"""
        try:
            path = Path(image_path)
            if not path.exists():
                return
            
            # Get the date from the image path
            date_str = path.parent.name
            # Check if this looks like a date folder (YYYY-MM-DD format)
            if not date_str or len(date_str) != 10 or date_str.count('-') != 2:
                date_str = self.today_date
            
            logger.debug(f"Adding new image {path.name} to date section: {date_str}")
            
            # Load image
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio, 
                                            Qt.TransformationMode.SmoothTransformation)
                
                # Create date section if needed
                if date_str not in self.date_widgets:
                    self.create_date_section(date_str)
                    self.images_by_date[date_str] = []
                    self.loaded_dates.add(date_str)
                
                # Add to gallery
                self.add_image_to_gallery(date_str, path, scaled_pixmap)
                logger.info(f"Added new image to gallery: {path.name}")
                
        except Exception as e:
            logger.error(f"Error adding new image immediately: {e}")
    
    def on_scroll_changed(self, value):
        """Handle scroll changes for lazy loading"""
        try:
            # Check if we're near the bottom
            scrollbar = self.scroll_area.verticalScrollBar()
            if scrollbar.maximum() > 0:
                scroll_percentage = (value / scrollbar.maximum()) * 100

                # If scrolled past threshold, try to load more dates
                if scroll_percentage > self.scroll_trigger_percent:
                    self.load_previous_dates()
                    
        except Exception as e:
            logger.error(f"Error in scroll handler: {e}")
    
    def load_previous_dates(self):
        """Load more photos (20 at a time) when scrolling down"""
        try:
            # Prevent concurrent loading
            if hasattr(self, 'is_loading_more') and self.is_loading_more:
                return
            self.is_loading_more = True
            
            # Show loading status
            old_status = self.status_label.text()
            self.set_status_message("Loading more photos...", "#ffcc00")
            QApplication.processEvents()  # Force UI update
            
            storage_dir = Path(self.config.get('storage', {}).get('save_dir', 
                                               str(Path.home() / 'BirdPhotos')))
            
            if not storage_dir.exists():
                self.set_status_message("No storage directory found", "#ff6464")
                self.is_loading_more = False
                return
            
            # First check if current dates have more images to load
            if hasattr(self, 'date_load_info'):
                for date_str in sorted(self.date_load_info.keys(), reverse=True):
                    info = self.date_load_info[date_str]
                    if info.get('has_more', False):
                        # Load next batch from this date
                        date_folder = storage_dir / date_str
                        offset = info['loaded']
                        logger.info(f"Loading more from {date_str}, offset={offset}")
                        
                        has_more = self.load_date_folder(
                            date_str,
                            date_folder,
                            limit=self.scroll_batch_size,
                            offset=offset
                        )

                        # Update status to show completion
                        total_images = sum(len(images) for images in self.images_by_date.values())
                        self.set_status_message(f"Loaded {total_images} images from {len(self.images_by_date)} days")

                        # Reset loading flag AFTER status update
                        self.is_loading_more = False
                        return
            
            # If no existing dates have more, load from a new date
            all_dates = []
            for folder in storage_dir.iterdir():
                if folder.is_dir() and folder.name.count('-') == 2:  # Basic date format check
                    try:
                        # Validate it's a proper date
                        datetime.strptime(folder.name, '%Y-%m-%d')
                        all_dates.append(folder.name)
                    except ValueError:
                        continue
            
            all_dates.sort(reverse=True)
            
            # Find the next date to load
            for date_str in all_dates:
                if date_str not in self.loaded_dates:
                    # Load first batch from this new date
                    date_folder = storage_dir / date_str
                    logger.info(f"Loading new date: {date_str}")
                    self.set_status_message(f"Loading photos from {date_str}...", "#ffcc00")
                    QApplication.processEvents()  # Force UI update
                    
                    # Load first batch (24 images) from new date
                    has_more = self.load_date_folder(
                        date_str,
                        date_folder,
                        limit=self.initial_batch_size,
                        offset=0
                    )
                    self.loaded_dates.add(date_str)

                    # Update status to show completion
                    total_images = sum(len(images) for images in self.images_by_date.values())
                    self.set_status_message(f"Loaded {total_images} images from {len(self.images_by_date)} days")

                    # Reset loading flag AFTER status update
                    self.is_loading_more = False
                    return
            
            # No more dates to load
            total_images = sum(len(images) for images in self.images_by_date.values())
            self.set_status_message(f"Loaded {total_images} images from {len(self.images_by_date)} days")
            self.is_loading_more = False
                    
        except Exception as e:
            logger.error(f"Error loading previous dates: {e}")
            self.set_status_message("Error loading photos", "#ff6464")
            self.is_loading_more = False
    
    def check_scroll_position(self):
        """Check if we need to load more images based on scroll position"""
        try:
            # Don't check if already loading
            if hasattr(self, 'is_loading_more') and self.is_loading_more:
                return

            scrollbar = self.scroll_area.verticalScrollBar()
            if scrollbar.maximum() > 0:
                scroll_percentage = (scrollbar.value() / scrollbar.maximum()) * 100
                if scroll_percentage > self.scroll_trigger_percent:
                    # Still near bottom, load more
                    self.load_previous_dates()
        except Exception as e:
            logger.debug(f"Error checking scroll position: {e}")
    
    def create_date_section(self, date_str, prepend=False):
        """Create a date section in the gallery"""
        # Date header - format the date nicely
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%A, %B %d, %Y')  # e.g., "Sunday, August 04, 2024"
        except:
            formatted_date = date_str
            
        date_label = QLabel(formatted_date)
        date_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #ffffff;
                background-color: #404040;
                padding: 10px 15px;
                border-radius: 5px;
                margin: 10px 0px;
            }
        """)
        
        # Grid for this date's images
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setSpacing(10)
        
        # Add to main gallery layout
        if prepend and self.gallery_layout.count() > 0:
            # Insert at the top
            self.gallery_layout.insertWidget(0, date_label)
            self.gallery_layout.insertWidget(1, grid_widget)
        else:
            # Add at the end
            row = self.gallery_layout.rowCount()
            self.gallery_layout.addWidget(date_label, row, 0, 1, 4)
            self.gallery_layout.addWidget(grid_widget, row + 1, 0, 1, 4)
        
        # Store both widget and row information for compatibility
        row = self.gallery_layout.rowCount() - 1  # Row where the grid was added
        self.date_widgets[date_str] = {
            'widget': grid_widget,
            'label': date_label,
            'row': row
        }
    
    def load_photos(self):
        """Load all photos from the storage directory - non-blocking"""
        # Stop any existing loader
        if self.loader_thread and self.loader_thread.isRunning():
            self.loader_thread.stop()
            self.loader_thread.wait()
        
        # Clear existing items
        self.clear_gallery()
        
        # Reset data structures
        self.images_by_date.clear()
        self.date_widgets.clear()
        self.gallery_items.clear()
        self.selected_items.clear()
        self.loaded_dates.clear()
        self.current_focus_index = -1  # Reset focus
        # Clear loaded image tracking
        if hasattr(self, 'loaded_image_paths'):
            self.loaded_image_paths.clear()
        if hasattr(self, 'date_load_info'):
            self.date_load_info.clear()
        self.update_selection_label()
        
        # Get storage directory
        storage_dir = Path(self.config.get('storage', {}).get('save_dir', 
                                           str(Path.home() / 'BirdPhotos')))
        
        if not storage_dir.exists():
            self.status_label.setText("No photos directory found")
            return
        
        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.refresh_btn.setEnabled(False)
        self.set_status_message("Loading photos...", "#ffcc00")
        
        # Start background loader
        self.loader_thread = GalleryLoader(storage_dir)
        self.loader_thread.progress.connect(self.on_load_progress)
        self.loader_thread.image_loaded.connect(self.on_image_loaded)
        self.loader_thread.finished_loading.connect(self.on_loading_finished)
        self.loader_thread.start()
    
    def clear_gallery(self):
        """Clear all gallery widgets with aggressive memory cleanup"""
        logger.info("Clearing gallery with memory cleanup...")
        
        # Clear layout and explicitly delete widgets
        while self.gallery_layout.count():
            item = self.gallery_layout.takeAt(0)
            if item.widget():
                widget = item.widget()
                
                # Find and delete any pixmaps in child widgets
                for child in widget.findChildren(QLabel):
                    if child.pixmap():
                        child.clear()
                
                widget.deleteLater()
        
        # Clear tracking collections
        if hasattr(self, 'gallery_items'):
            self.gallery_items.clear()
        if hasattr(self, 'selected_items'):
            self.selected_items.clear()
        if hasattr(self, 'images_by_date'):
            self.images_by_date.clear()
        if hasattr(self, 'date_widgets'):
            self.date_widgets.clear()
        # Note: loaded_dates is NOT cleared here - managed by refresh logic
        if hasattr(self, 'current_focus_index'):
            self.current_focus_index = -1
        
        # Force garbage collection
        import gc
        gc.collect()
        
        logger.info("Gallery cleared and memory cleaned up")
    
    @pyqtSlot(int, int, str)
    def on_load_progress(self, current, total, message):
        """Update progress bar"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"{current}/{total} - {message}")
    
    @pyqtSlot(object, str, float)
    def on_image_loaded(self, widget_data, date_str, mtime):
        """Add loaded image to gallery"""
        
        # Group by date
        if date_str not in self.images_by_date:
            self.images_by_date[date_str] = []
            
            # Create date header
            date_label = QLabel(datetime.fromtimestamp(mtime).strftime('%A, %B %d, %Y'))
            date_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
            
            row = len(self.date_widgets) * 100  # Space for images
            self.gallery_layout.addWidget(date_label, row, 0, 1, 4)
            self.date_widgets[date_str] = {'label': date_label, 'row': row + 1}
        
        # Add image to date group
        date_info = self.date_widgets[date_str]
        images_in_date = len(self.images_by_date[date_str])
        col = images_in_date % 4
        row = date_info['row'] + (images_in_date // 4)
        
        # Create thumbnail widget
        item_widget = self.create_gallery_item(widget_data['path'], widget_data['pixmap'])
        self.gallery_layout.addWidget(item_widget, row, col)
        
        self.images_by_date[date_str].append(widget_data['path'])
        self.gallery_items.append((widget_data['path'], item_widget))
    
    @pyqtSlot()
    def on_loading_finished(self):
        """Handle loading completion"""
        self.progress_bar.setVisible(False)
        self.refresh_btn.setEnabled(True)
        
        # Check if we loaded today's photos and if count is less than 16
        today_count = len(self.images_by_date.get(self.today_date, []))
        total_images = sum(len(images) for images in self.images_by_date.values())
        
        # If today has less than 16 photos and we haven't loaded yesterday yet, load it
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        if today_count > 0 and today_count < 16 and yesterday not in self.images_by_date:
            storage_dir = Path(self.config.get('storage', {}).get('save_dir', 
                                               str(Path.home() / 'BirdPhotos')))
            yesterday_folder = storage_dir / yesterday
            
            if yesterday_folder.exists() and yesterday_folder.is_dir():
                logger.info(f"Today only has {today_count} photos, loading yesterday's photos too...")
                self.set_status_message(f"Loading more photos (today has only {today_count})...", "#ffcc00")
                
                # Show progress bar again
                self.progress_bar.setVisible(True)
                self.progress_bar.setFormat("Loading yesterday's photos...")
                
                # Load yesterday's photos
                self.loader_thread = GalleryLoaderThread(yesterday_folder)
                self.loader_thread.image_loaded.connect(self.on_image_loaded)
                self.loader_thread.progress.connect(self.on_loader_progress)
                self.loader_thread.finished_loading.connect(self.on_loading_finished)
                self.loader_thread.start()
                return
        
        # Normal completion - reset to normal color
        self.set_status_message(f"Loaded {total_images} images from {len(self.images_by_date)} days")
    
    
    def create_gallery_item(self, image_path, scaled_pixmap):
        """Create a gallery item widget"""
        container = QWidget()
        container.setFixedSize(200, 200)
        container.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border: 2px solid transparent;
                border-radius: 5px;
            }
            QWidget:hover {
                border-color: #555;
            }
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Checkbox for selection
        checkbox = QCheckBox()
        checkbox.stateChanged.connect(lambda state: self.on_item_selected(image_path, state))
        layout.addWidget(checkbox, alignment=Qt.AlignmentFlag.AlignRight)
        
        # Thumbnail
        thumb_label = QLabel()
        thumb_label.setPixmap(scaled_pixmap)
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setStyleSheet("QLabel { background-color: #000; }")
        thumb_label.mousePressEvent = lambda e: self.on_image_clicked(image_path) if e.button() == Qt.MouseButton.LeftButton else None
        thumb_label.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(thumb_label)
        
        # Filename
        name_label = QLabel(Path(image_path).name)
        name_label.setStyleSheet("color: #ccc; font-size: 10px;")
        name_label.setWordWrap(True)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)
        
        # Time ago label
        time_ago = self.get_time_ago_text(image_path)
        time_label = QLabel(time_ago)
        time_label.setStyleSheet("color: #999; font-size: 9px; font-style: italic;")
        time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(time_label)
        
        return container
    
    def get_time_ago_text(self, image_path):
        """Extract timestamp from filename and return human-readable time ago text"""
        try:
            import re
            
            # Extract timestamp from filename (motion_1754413128.jpeg -> 1754413128)
            filename = Path(image_path).name
            match = re.search(r'motion_(\d+)\.jpeg', filename)
            
            if match:
                timestamp = int(match.group(1))
                # Convert timestamp to datetime
                image_time = datetime.fromtimestamp(timestamp)
                now = datetime.now()
                
                # Calculate time difference
                diff = now - image_time
                
                # Format as human-readable text
                if diff.days > 0:
                    if diff.days == 1:
                        return "1 day ago"
                    else:
                        return f"{diff.days} days ago"
                elif diff.seconds > 3600:  # More than 1 hour
                    hours = diff.seconds // 3600
                    if hours == 1:
                        return "1 hour ago"
                    else:
                        return f"{hours} hours ago"
                elif diff.seconds > 60:  # More than 1 minute
                    minutes = diff.seconds // 60
                    if minutes == 1:
                        return "1 minute ago"
                    else:
                        return f"{minutes} minutes ago"
                else:
                    return "Just now"
            else:
                # Fallback: use file modification time
                stat = Path(image_path).stat()
                image_time = datetime.fromtimestamp(stat.st_mtime)
                now = datetime.now()
                diff = now - image_time
                
                if diff.days > 0:
                    return f"{diff.days} days ago"
                elif diff.seconds > 3600:
                    hours = diff.seconds // 3600
                    return f"{hours} hours ago"
                elif diff.seconds > 60:
                    minutes = diff.seconds // 60
                    return f"{minutes} minutes ago"
                else:
                    return "Just now"
                    
        except Exception as e:
            logger.debug(f"Error getting time ago for {image_path}: {e}")
            return ""
    
    def on_item_selected(self, path, state):
        """Handle item selection"""
        if state == 2:  # Checked
            self.selected_items.add(path)
        else:
            self.selected_items.discard(path)
        self.update_selection_label()
    
    def update_selection_label(self):
        """Update selection count and button states"""
        count = len(self.selected_items)
        self.selection_label.setText(f"{count} selected")
        self.email_btn.setEnabled(count > 0)
        self.delete_btn.setEnabled(count > 0)
    
    def select_all(self):
        """Select all images"""
        for path, widget in self.gallery_items:
            checkbox = widget.findChild(QCheckBox)
            if checkbox:
                checkbox.setChecked(True)
    
    def clear_selection(self):
        """Clear all selections"""
        for path, widget in self.gallery_items:
            checkbox = widget.findChild(QCheckBox)
            if checkbox:
                checkbox.setChecked(False)
    
    def get_all_image_paths(self):
        """Get all image paths in the current gallery view"""
        all_paths = []
        # Collect paths in date order
        for date_str in sorted(self.images_by_date.keys(), reverse=True):
            all_paths.extend(self.images_by_date[date_str])
        return all_paths
                
    def show_full_image(self, image_path):
        """Show full-size image in a dialog with keyboard navigation"""
        # Convert to Path object if it's a string
        if isinstance(image_path, str):
            image_path = Path(image_path)
        
        # Create custom dialog for keyboard handling
        self.current_full_image = str(image_path)
        dialog = ImageViewerDialog(self, image_path, self.get_all_image_paths())
        dialog.exec()
        
    def delete_selected(self):
        """Delete selected images"""
        if not self.selected_items:
            return
            
        # Confirm deletion
        reply = QMessageBox.question(
            self, 
            "Confirm Deletion",
            f"Delete {len(self.selected_items)} selected image(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            for image_path in self.selected_items.copy():  # Copy to avoid modification during iteration
                try:
                    # Ensure image_path is a Path object
                    if isinstance(image_path, str):
                        image_path = Path(image_path)
                    
                    if image_path.exists():
                        image_path.unlink()
                        deleted_count += 1
                        logger.info(f"Deleted {image_path}")
                    else:
                        logger.warning(f"File not found: {image_path}")
                        
                except Exception as e:
                    logger.error(f"Failed to delete {image_path}: {e}")
                    QMessageBox.warning(self, "Delete Error", f"Failed to delete {image_path.name}: {str(e)}")
            
            # Clear selection
            self.selected_items.clear()
            self.update_selection_label()
            
            # Reload gallery
            if deleted_count > 0:
                self.load_photos()
                QMessageBox.information(self, "Delete Complete", f"Successfully deleted {deleted_count} image(s).")
            
    def email_selected(self):
        """Email selected images"""
        if not self.selected_items or not self.email_handler:
            return
            
        try:
            # Get email config
            email_config = self.config.get('email', {})
            recipient = email_config.get('recipient', email_config.get('sender', ''))
            
            if not recipient:
                QMessageBox.warning(self, "No Email", 
                                  "No email recipient configured")
                return
                
            # Send email with attachments
            subject = f"Bird Photos - {len(self.selected_items)} images"
            body = f"Attached are {len(self.selected_items)} bird photos from your collection."
            
            success = self.email_handler.send_email_with_attachments(
                recipient, 
                subject, 
                body,
                list(self.selected_items)
            )
            
            if success:
                QMessageBox.information(self, "Email Sent", 
                                      f"Successfully sent {len(self.selected_items)} images")
                
                # Clear selection after successful email
                self.clear_selection()
            else:
                QMessageBox.warning(self, "Email Failed", 
                                  "Failed to send email")
                
        except Exception as e:
            logger.error(f"Email error: {e}")
            QMessageBox.critical(self, "Error", f"Email error: {str(e)}")
