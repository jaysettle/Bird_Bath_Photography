#!/usr/bin/env python3
"""
Experimental Bird Filter App
Uses the pre-filter model to scan local images and delete non-bird images
"""

import sys
import os
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path to import our modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QLabel, QPushButton, QProgressBar,
                           QTextEdit, QFileDialog, QMessageBox, QGroupBox,
                           QGridLayout, QCheckBox, QSlider, QTabWidget,
                           QScrollArea, QFrame, QDialog, QSizePolicy)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QPixmap

from src.bird_prefilter import BirdPreFilter
from src.bird_classifier import BirdClassifier
from src.logger import get_logger

logger = get_logger(__name__)

class ImageThumbnail(QLabel):
    """Clickable thumbnail widget"""
    clicked = pyqtSignal(str)
    
    def __init__(self, image_path, is_bird, confidence, species=""):
        super().__init__()
        self.image_path = image_path
        self.is_bird = is_bird
        self.confidence = confidence
        self.species = species
        
        # Load and scale image
        try:
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, 
                                            Qt.TransformationMode.SmoothTransformation)
                self.setPixmap(scaled_pixmap)
            else:
                self.setText("Error loading image")
        except Exception:
            self.setText("Error loading image")
            
        # Style the thumbnail
        border_color = "#4CAF50" if is_bird else "#f44336"
        self.setStyleSheet(f"""
            QLabel {{
                border: 3px solid {border_color};
                padding: 2px;
                background: white;
            }}
            QLabel:hover {{
                border: 3px solid #2196F3;
                background: #f0f8ff;
            }}
        """)
        
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(156, 156)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Add tooltip
        if is_bird and self.species:
            bird_text = self.species
        else:
            bird_text = "No Bird"
        filename = Path(image_path).name
        self.setToolTip(f"{filename}\n{bird_text} (confidence: {confidence:.2f})")
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.image_path)

class ImageDialog(QDialog):
    """Dialog to show full-size image"""
    def __init__(self, image_path, is_bird, confidence, species=""):
        super().__init__()
        self.setWindowTitle(f"Image Viewer - {Path(image_path).name}")
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        # Image info
        if is_bird and species:
            bird_text = f"{species} Detected"
        elif is_bird:
            bird_text = "Bird Detected"
        else:
            bird_text = "No Bird Detected"
        info_label = QLabel(f"{bird_text} (Confidence: {confidence:.2f})")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("font-weight: bold; font-size: 14px; margin: 10px;")
        layout.addWidget(info_label)
        
        # Image
        image_label = QLabel()
        try:
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                # Scale to fit screen (max 800x600)
                scaled_pixmap = pixmap.scaled(800, 600, Qt.AspectRatioMode.KeepAspectRatio, 
                                            Qt.TransformationMode.SmoothTransformation)
                image_label.setPixmap(scaled_pixmap)
                image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                image_label.setText("Error loading image")
        except Exception as e:
            image_label.setText(f"Error loading image: {e}")
            
        layout.addWidget(image_label)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        self.adjustSize()

class ImageFilterWorker(QThread):
    """Worker thread to process images"""
    progress_updated = pyqtSignal(int, int)  # current, total
    image_processed = pyqtSignal(str, bool, float, str)  # path, is_bird, confidence, species
    finished_processing = pyqtSignal(dict)  # final stats
    log_message = pyqtSignal(str)
    
    def __init__(self, folder_path, prefilter, delete_non_birds=False, confidence_threshold=0.1):
        super().__init__()
        self.folder_path = Path(folder_path)
        self.prefilter = prefilter
        self.delete_non_birds = delete_non_birds
        self.confidence_threshold = confidence_threshold
        self.running = True
        
    def run(self):
        """Process all images in the folder"""
        stats = {
            'total_images': 0,
            'birds_found': 0,
            'non_birds_found': 0,
            'deleted_images': 0,
            'errors': 0,
            'processing_time': 0
        }
        
        # Get all image files
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
        image_files = []
        
        for ext in image_extensions:
            image_files.extend(self.folder_path.glob(f'*{ext}'))
            image_files.extend(self.folder_path.glob(f'*{ext.upper()}'))
            
        stats['total_images'] = len(image_files)
        self.log_message.emit(f"Found {stats['total_images']} images to process")
        
        if stats['total_images'] == 0:
            self.finished_processing.emit(stats)
            return
            
        start_time = time.time()
        
        for i, image_path in enumerate(image_files):
            if not self.running:
                break
                
            try:
                self.log_message.emit(f"Processing: {image_path.name}")
                
                # Set confidence threshold
                original_threshold = self.prefilter.confidence_threshold
                self.prefilter.set_confidence_threshold(self.confidence_threshold)
                
                # Process image with prefilter
                result = self.prefilter.process_image(str(image_path), timeout=5.0)
                
                # Restore original threshold
                self.prefilter.set_confidence_threshold(original_threshold)
                
                if result['processed']:
                    is_bird = result['bird_detected']
                    confidence = result['confidence']
                    species = "Bird" if is_bird else "No bird detected"
                
                if result['processed']:
                    self.image_processed.emit(str(image_path), is_bird, confidence, species)
                    
                    if is_bird:
                        stats['birds_found'] += 1
                        self.log_message.emit(f"✅ {species} detected (confidence: {confidence:.2f})")
                    else:
                        stats['non_birds_found'] += 1
                        self.log_message.emit(f"❌ No bird detected")
                        
                        # Delete non-bird image if requested
                        if self.delete_non_birds:
                            try:
                                image_path.unlink()
                                stats['deleted_images'] += 1
                                self.log_message.emit(f"🗑️ Deleted: {image_path.name}")
                            except Exception as e:
                                self.log_message.emit(f"Error deleting {image_path.name}: {e}")
                                stats['errors'] += 1
                else:
                    self.log_message.emit(f"⚠️ Processing failed: {result.get('reason', 'Unknown')}")
                    stats['errors'] += 1
                    
            except Exception as e:
                self.log_message.emit(f"Error processing {image_path.name}: {e}")
                stats['errors'] += 1
                
            self.progress_updated.emit(i + 1, stats['total_images'])
            
        stats['processing_time'] = time.time() - start_time
        self.finished_processing.emit(stats)
        
    def stop(self):
        """Stop processing"""
        self.running = False

class BirdFilterApp(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.prefilter = None
        self.worker = None
        self.folder_path = ""
        self.processed_images = []  # Store results for gallery
        self.setup_ui()
        self.initialize_models()
        
    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("Bird Filter - Experimental Tool")
        self.setGeometry(100, 100, 1000, 700)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Create tabs
        self.setup_scanner_tab()
        self.setup_gallery_tab()
        
    def setup_scanner_tab(self):
        """Setup the main scanner tab"""
        scanner_widget = QWidget()
        layout = QVBoxLayout(scanner_widget)
        
        # Title
        title = QLabel("🦅 Bird Image Filter")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Description  
        desc = QLabel("Use AI model to detect if birds are present in images and optionally delete non-bird photos")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #666; margin: 10px;")
        layout.addWidget(desc)
        
        # Model status
        self.model_status = QLabel("🔄 Loading model...")
        self.model_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.model_status)
        
        # Folder selection
        folder_group = QGroupBox("Folder Selection")
        folder_layout = QHBoxLayout()
        
        self.folder_label = QLabel("No folder selected")
        self.folder_label.setStyleSheet("padding: 5px; border: 1px solid #ccc; background: #f9f9f9;")
        folder_layout.addWidget(self.folder_label, 1)
        
        self.browse_btn = QPushButton("Browse Folder")
        self.browse_btn.clicked.connect(self.browse_folder)
        folder_layout.addWidget(self.browse_btn)
        
        folder_group.setLayout(folder_layout)
        layout.addWidget(folder_group)
        
        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout()
        
        # Confidence threshold slider
        confidence_layout = QHBoxLayout()
        confidence_layout.addWidget(QLabel("Confidence Threshold:"))
        
        self.confidence_slider = QSlider(Qt.Orientation.Horizontal)
        self.confidence_slider.setMinimum(1)  # 0.01
        self.confidence_slider.setMaximum(100)  # 1.0
        self.confidence_slider.setValue(10)  # 0.1 default
        self.confidence_slider.valueChanged.connect(self.update_confidence_label)
        confidence_layout.addWidget(self.confidence_slider)
        
        self.confidence_label = QLabel("0.10")
        self.confidence_label.setStyleSheet("font-weight: bold; color: #2196F3; min-width: 40px;")
        confidence_layout.addWidget(self.confidence_label)
        
        options_layout.addLayout(confidence_layout)
        
        self.delete_checkbox = QCheckBox("Delete non-bird images (PERMANENT)")
        self.delete_checkbox.setStyleSheet("color: #d32f2f; font-weight: bold;")
        options_layout.addWidget(self.delete_checkbox)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.scan_btn = QPushButton("🔍 Scan Images")
        self.scan_btn.clicked.connect(self.start_scanning)
        self.scan_btn.setEnabled(False)
        self.scan_btn.setStyleSheet("padding: 10px; font-size: 14px;")
        button_layout.addWidget(self.scan_btn)
        
        self.stop_btn = QPushButton("⏹️ Stop")
        self.stop_btn.clicked.connect(self.stop_scanning)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.stop_btn)
        
        layout.addLayout(button_layout)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Statistics
        stats_group = QGroupBox("Statistics")
        self.stats_layout = QGridLayout()
        
        # Initialize stat labels
        self.stat_labels = {}
        stats = [
            ('total_images', 'Total Images', '0'),
            ('birds_found', 'Birds Found', '0'),
            ('non_birds_found', 'Non-Birds Found', '0'),
            ('deleted_images', 'Images Deleted', '0'),
            ('errors', 'Errors', '0'),
            ('processing_time', 'Processing Time', '0s')
        ]
        
        for i, (key, label, value) in enumerate(stats):
            row = i // 2
            col = (i % 2) * 2
            
            self.stats_layout.addWidget(QLabel(f"{label}:"), row, col)
            self.stat_labels[key] = QLabel(value)
            self.stat_labels[key].setStyleSheet("font-weight: bold; color: #2196F3;")
            self.stats_layout.addWidget(self.stat_labels[key], row, col + 1)
            
        stats_group.setLayout(self.stats_layout)
        layout.addWidget(stats_group)
        
        # Log output
        log_group = QGroupBox("Processing Log")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(200)
        self.log_text.setFont(QFont("Consolas", 9))
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        self.tab_widget.addTab(scanner_widget, "🔍 Scanner")
        
    def setup_gallery_tab(self):
        """Setup the image gallery tab"""
        gallery_widget = QWidget()
        layout = QVBoxLayout(gallery_widget)
        
        # Header
        header_layout = QHBoxLayout()
        
        gallery_title = QLabel("📸 Image Gallery")
        gallery_title.setFont(QFont("", 16, QFont.Weight.Bold))
        header_layout.addWidget(gallery_title)
        
        header_layout.addStretch()
        
        # Filter buttons
        self.show_all_btn = QPushButton("All Images")
        self.show_all_btn.clicked.connect(lambda: self.filter_gallery('all'))
        self.show_all_btn.setStyleSheet("background: #2196F3; color: white; padding: 5px 15px;")
        header_layout.addWidget(self.show_all_btn)
        
        self.show_birds_btn = QPushButton("Birds Only")
        self.show_birds_btn.clicked.connect(lambda: self.filter_gallery('birds'))
        self.show_birds_btn.setStyleSheet("background: #4CAF50; color: white; padding: 5px 15px;")
        header_layout.addWidget(self.show_birds_btn)
        
        self.show_no_birds_btn = QPushButton("No Birds Only")
        self.show_no_birds_btn.clicked.connect(lambda: self.filter_gallery('no_birds'))
        self.show_no_birds_btn.setStyleSheet("background: #f44336; color: white; padding: 5px 15px;")
        header_layout.addWidget(self.show_no_birds_btn)
        
        layout.addLayout(header_layout)
        
        # Gallery stats
        self.gallery_stats = QLabel("No images processed yet")
        self.gallery_stats.setStyleSheet("color: #666; margin: 5px;")
        layout.addWidget(self.gallery_stats)
        
        # Scroll area for thumbnails
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Container for thumbnails
        self.gallery_container = QWidget()
        self.gallery_layout = QGridLayout(self.gallery_container)
        self.gallery_layout.setSpacing(10)
        self.gallery_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        self.scroll_area.setWidget(self.gallery_container)
        layout.addWidget(self.scroll_area)
        
        self.tab_widget.addTab(gallery_widget, "📸 Gallery")
        
    def update_confidence_label(self):
        """Update confidence threshold label"""
        value = self.confidence_slider.value() / 100.0
        self.confidence_label.setText(f"{value:.2f}")
        
    def filter_gallery(self, filter_type):
        """Filter gallery images"""
        # Reset button styles
        for btn in [self.show_all_btn, self.show_birds_btn, self.show_no_birds_btn]:
            btn.setStyleSheet(btn.styleSheet().replace("background: #FFC107", "background: #2196F3").replace("background: #66BB6A", "background: #4CAF50").replace("background: #EF5350", "background: #f44336"))
        
        # Highlight active button
        if filter_type == 'all':
            self.show_all_btn.setStyleSheet(self.show_all_btn.styleSheet().replace("background: #2196F3", "background: #FFC107"))
        elif filter_type == 'birds':
            self.show_birds_btn.setStyleSheet(self.show_birds_btn.styleSheet().replace("background: #4CAF50", "background: #66BB6A"))
        elif filter_type == 'no_birds':
            self.show_no_birds_btn.setStyleSheet(self.show_no_birds_btn.styleSheet().replace("background: #f44336", "background: #EF5350"))
        
        self.update_gallery(filter_type)
        
    def update_gallery(self, filter_type='all'):
        """Update the gallery display"""
        # Clear existing thumbnails
        for i in reversed(range(self.gallery_layout.count())):
            child = self.gallery_layout.itemAt(i).widget()
            if child:
                child.setParent(None)
        
        # Filter images based on type
        if filter_type == 'birds':
            filtered_images = [img for img in self.processed_images if img['is_bird']]
        elif filter_type == 'no_birds':
            filtered_images = [img for img in self.processed_images if not img['is_bird']]
        else:
            filtered_images = self.processed_images
        
        # Update stats
        total_images = len(self.processed_images)
        birds_count = len([img for img in self.processed_images if img['is_bird']])
        no_birds_count = total_images - birds_count
        showing_count = len(filtered_images)
        
        self.gallery_stats.setText(
            f"Total: {total_images} | Birds: {birds_count} | No Birds: {no_birds_count} | Showing: {showing_count}"
        )
        
        # Add thumbnails
        cols = 6  # 6 thumbnails per row
        for i, img_data in enumerate(filtered_images):
            row = i // cols
            col = i % cols
            
            thumbnail = ImageThumbnail(img_data['path'], img_data['is_bird'], 
                                      img_data['confidence'], img_data.get('species', ''))
            thumbnail.clicked.connect(self.show_full_image)
            self.gallery_layout.addWidget(thumbnail, row, col)
        
        # If no images, show message
        if not filtered_images:
            no_images_label = QLabel("No images to display")
            no_images_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_images_label.setStyleSheet("color: #999; font-size: 16px; margin: 50px;")
            self.gallery_layout.addWidget(no_images_label, 0, 0, 1, cols)
    
    def show_full_image(self, image_path):
        """Show full-size image in dialog"""
        # Find image data
        img_data = next((img for img in self.processed_images if img['path'] == image_path), None)
        if img_data:
            dialog = ImageDialog(image_path, img_data['is_bird'], 
                               img_data['confidence'], img_data.get('species', ''))
            dialog.exec()
        
    def initialize_models(self):
        """Initialize the pre-filter model"""
        try:
            # Load config
            config_path = Path(__file__).parent.parent / "config.json"
            if config_path.exists():
                import json
                with open(config_path, 'r') as f:
                    config = json.load(f)
            else:
                config = {'prefilter': {'enabled': True, 'confidence_threshold': 0.1}}
            
            # Load the prefilter for bird detection
            self.prefilter = BirdPreFilter(config)
            self.using_classifier = False
            
            # Check if model loaded successfully
            if hasattr(self.prefilter, 'enabled') and self.prefilter.enabled:
                self.model_status.setText("✅ Bird detection model loaded")
                self.model_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
                self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] Bird detection model loaded successfully")
            else:
                self.model_status.setText("❌ Model failed to load")
                self.model_status.setStyleSheet("color: #f44336; font-weight: bold;")
                self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] Model failed to load")
                
        except Exception as e:
            self.model_status.setText(f"❌ Error: {str(e)}")
            self.model_status.setStyleSheet("color: #f44336; font-weight: bold;")
            self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] Error loading model: {e}")
            
    def browse_folder(self):
        """Browse for folder containing images"""
        folder = QFileDialog.getExistingDirectory(
            self, 
            "Select folder containing images",
            str(Path.home())
        )
        
        if folder:
            self.folder_path = folder
            self.folder_label.setText(folder)
            self.scan_btn.setEnabled(True)
            
            # Count images in folder
            image_count = self.count_images(Path(folder))
            self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] Selected folder: {folder}")
            self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] Found {image_count} images")
            
    def count_images(self, folder_path):
        """Count images in folder"""
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
        count = 0
        for ext in image_extensions:
            count += len(list(folder_path.glob(f'*{ext}')))
            count += len(list(folder_path.glob(f'*{ext.upper()}')))
        return count
        
    def start_scanning(self):
        """Start scanning images"""
        if not self.prefilter or not self.prefilter.enabled:
            QMessageBox.warning(self, "Error", "Bird detection model is not loaded!")
            return
            
        if not self.folder_path:
            QMessageBox.warning(self, "Error", "Please select a folder first!")
            return
            
        # Confirm deletion if checkbox is checked
        delete_mode = self.delete_checkbox.isChecked()
        if delete_mode:
            reply = QMessageBox.question(
                self, 
                "Confirm Deletion",
                "Are you sure you want to DELETE non-bird images?\n\nThis action cannot be undone!",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
                
        # Reset statistics
        for key in self.stat_labels:
            self.stat_labels[key].setText('0' if key != 'processing_time' else '0s')
            
        # Clear log
        self.log_text.clear()
        self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] Starting scan...")
        if delete_mode:
            self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ DELETE MODE ENABLED")
            
        # Setup UI for processing
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Clear previous results
        self.processed_images.clear()
        
        # Get confidence threshold from slider
        confidence_threshold = self.confidence_slider.value() / 100.0
        
        # Start worker thread
        self.worker = ImageFilterWorker(self.folder_path, self.prefilter, delete_mode, confidence_threshold)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.image_processed.connect(self.on_image_processed)
        self.worker.finished_processing.connect(self.on_finished)
        self.worker.log_message.connect(self.add_log_message)
        self.worker.start()
        
    def stop_scanning(self):
        """Stop scanning process"""
        if self.worker:
            self.worker.stop()
            self.add_log_message("Stopping scan...")
            
    def update_progress(self, current, total):
        """Update progress bar"""
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setValue(percentage)
            
    def on_image_processed(self, image_path, is_bird, confidence, species):
        """Handle individual image processing result"""
        # Store result for gallery
        self.processed_images.append({
            'path': image_path,
            'is_bird': is_bird,
            'confidence': confidence,
            'species': species
        })
        
        # Update running statistics
        birds = int(self.stat_labels['birds_found'].text())
        non_birds = int(self.stat_labels['non_birds_found'].text())
        
        if is_bird:
            self.stat_labels['birds_found'].setText(str(birds + 1))
        else:
            self.stat_labels['non_birds_found'].setText(str(non_birds + 1))
            
    def on_finished(self, stats):
        """Handle completion of processing"""
        # Update all statistics
        self.stat_labels['total_images'].setText(str(stats['total_images']))
        self.stat_labels['birds_found'].setText(str(stats['birds_found']))
        self.stat_labels['non_birds_found'].setText(str(stats['non_birds_found']))
        self.stat_labels['deleted_images'].setText(str(stats['deleted_images']))
        self.stat_labels['errors'].setText(str(stats['errors']))
        self.stat_labels['processing_time'].setText(f"{stats['processing_time']:.1f}s")
        
        # Calculate percentages
        total = stats['total_images']
        if total > 0:
            bird_pct = (stats['birds_found'] / total) * 100
            non_bird_pct = (stats['non_birds_found'] / total) * 100
            
            self.add_log_message(f"📊 Results: {bird_pct:.1f}% birds, {non_bird_pct:.1f}% non-birds")
            
        self.add_log_message("✅ Scanning complete!")
        
        # Update gallery
        self.update_gallery()
        
        # Reset UI
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        
        # Show completion message
        QMessageBox.information(
            self, 
            "Scan Complete", 
            f"Processing finished!\n\n"
            f"Total images: {stats['total_images']}\n"
            f"Birds found: {stats['birds_found']}\n"
            f"Non-birds: {stats['non_birds_found']}\n"
            f"Images deleted: {stats['deleted_images']}\n"
            f"Errors: {stats['errors']}\n"
            f"Time: {stats['processing_time']:.1f}s"
        )
        
    def add_log_message(self, message):
        """Add message to log with timestamp"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_text.append(f"[{timestamp}] {message}")
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

def main():
    app = QApplication(sys.argv)
    window = BirdFilterApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()