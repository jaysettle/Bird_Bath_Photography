#!/usr/bin/env python3
"""
Species Tab - Display identified bird species with thumbnails
"""

import os
import json
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                           QScrollArea, QGroupBox, QGridLayout, QPushButton,
                           QDialog, QSizePolicy)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread, pyqtSlot, QTimer
from PyQt6.QtGui import QPixmap

from .logger import get_logger

logger = get_logger(__name__)

class ThumbnailLoader(QThread):
    """Background thread for loading thumbnails"""
    thumbnail_loaded = pyqtSignal(str, QPixmap)  # image_path, pixmap
    
    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path
        
    def run(self):
        try:
            if os.path.exists(self.image_path):
                pixmap = QPixmap(self.image_path)
                if not pixmap.isNull():
                    # Pre-scale to thumbnail size to reduce memory usage
                    scaled = pixmap.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
                    self.thumbnail_loaded.emit(self.image_path, scaled)
        except Exception as e:
            logger.error(f"Error loading thumbnail for {self.image_path}: {e}")

class ClickableLabel(QLabel):
    """Label that emits clicked signal"""
    clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

class ImageDialog(QDialog):
    """Dialog to show full-size image"""
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bird Photo")
        self.setModal(True)
        
        layout = QVBoxLayout()
        
        # Load and display image with size limits to prevent crashes
        try:
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                # Scale to reasonable size (max 800x600) to prevent memory issues
                scaled = pixmap.scaled(800, 600, Qt.AspectRatioMode.KeepAspectRatio, 
                                     Qt.TransformationMode.SmoothTransformation)
                
                label = QLabel()
                label.setPixmap(scaled)
                layout.addWidget(label)
            else:
                layout.addWidget(QLabel("Image not found"))
        except Exception as e:
            logger.error(f"Error loading full-size image {image_path}: {e}")
            layout.addWidget(QLabel("Error loading image"))
            
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)

class SpeciesTab(QWidget):
    """Tab for displaying identified bird species"""
    
    def __init__(self, bird_identifier):
        super().__init__()
        self.bird_identifier = bird_identifier
        self.thumbnail_loaders = {}  # Track active thumbnail loading threads
        self.label_mappings = {}     # Map image paths to their labels
        self.setup_ui()
        self.load_species()
        
    def setup_ui(self):
        """Set up the UI"""
        layout = QVBoxLayout()
        
        # Header
        header = QLabel("Identified Bird Species")
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        layout.addWidget(header)
        
        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_species)
        refresh_btn.setMaximumWidth(100)
        layout.addWidget(refresh_btn)
        
        # Scroll area for species
        scroll = QScrollArea()
        self.species_widget = QWidget()
        self.species_layout = QVBoxLayout(self.species_widget)
        
        scroll.setWidget(self.species_widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        
        self.setLayout(layout)
        
    def load_species(self):
        """Load and display species from database"""
        # Use QTimer to defer loading to prevent blocking UI
        QTimer.singleShot(100, self._load_species_deferred)
    
    def _load_species_deferred(self):
        """Deferred species loading"""
        # Clear existing widgets
        while self.species_layout.count():
            child = self.species_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        if not self.bird_identifier:
            self.species_layout.addWidget(QLabel("Bird identifier not available"))
            return
            
        # Load database
        self.bird_identifier.load_database()
        species_dict = self.bird_identifier.database.get('species', {})
        
        if not species_dict:
            no_species = QLabel("No bird species identified yet")
            no_species.setStyleSheet("color: gray; padding: 20px;")
            self.species_layout.addWidget(no_species)
            return
            
        # Display each species
        for scientific_name, species_data in species_dict.items():
            species_group = QGroupBox()
            species_layout = QHBoxLayout()
            
            # Gallery on the left
            gallery_widget = QWidget()
            gallery_widget.setFixedWidth(330)  # Width for 3 x 100px thumbnails + spacing
            gallery_layout = QGridLayout(gallery_widget)
            gallery_layout.setSpacing(5)
            
            # Get photo gallery or fall back to just last_photo
            photo_gallery = species_data.get('photo_gallery', [])
            if not photo_gallery and 'last_photo' in species_data:
                photo_gallery = [species_data['last_photo']]
            
            # Create thumbnails for up to 9 photos (3x3 grid)
            row, col = 0, 0
            for i, photo_path in enumerate(photo_gallery[-9:]):  # Show last 9 photos
                thumb_label = ClickableLabel()
                thumb_label.setFixedSize(100, 100)
                thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb_label.setStyleSheet("background-color: #333; color: gray; border: 1px solid #555;")
                thumb_label.setText("Loading...")
                
                # Connect click to show full image
                thumb_label.clicked.connect(lambda p=photo_path: self.show_full_image(p))
                
                # Store label mapping for async loading
                self.label_mappings[f"{photo_path}_{i}"] = thumb_label
                
                # Start async thumbnail loading
                self.load_thumbnail_async_with_key(f"{photo_path}_{i}", photo_path)
                
                gallery_layout.addWidget(thumb_label, row, col)
                
                col += 1
                if col >= 3:
                    col = 0
                    row += 1
            
            # Add empty labels to fill remaining slots (up to 3x3 grid)
            total_photos = len(photo_gallery[-9:])
            remaining_slots = 9 - total_photos
            
            for _ in range(remaining_slots):
                empty_label = QLabel()
                empty_label.setFixedSize(100, 100)
                empty_label.setStyleSheet("background-color: #222; border: 1px dashed #444;")
                gallery_layout.addWidget(empty_label, row, col)
                col += 1
                if col >= 3:
                    col = 0
                    row += 1
                    
            species_layout.addWidget(gallery_widget)
            
            # Species info on the right
            info_widget = QWidget()
            info_layout = QVBoxLayout(info_widget)
            
            # Common name
            common_name = species_data.get('common_name', 'Unknown')
            name_label = QLabel(f"<b>{common_name}</b>")
            name_label.setStyleSheet("font-size: 16px;")
            info_layout.addWidget(name_label)
            
            # Scientific name
            sci_label = QLabel(f"<i>{scientific_name}</i>")
            sci_label.setStyleSheet("color: #888;")
            info_layout.addWidget(sci_label)
            
            # Conservation status
            status = species_data.get('conservation_status', 'Unknown')
            status_label = QLabel(f"Conservation Status: {status}")
            info_layout.addWidget(status_label)
            
            # Sighting count
            count = species_data.get('sighting_count', 0)
            count_label = QLabel(f"Sightings: {count}")
            info_layout.addWidget(count_label)
            
            # First seen
            first_seen = species_data.get('first_seen', '')
            if first_seen:
                try:
                    dt = datetime.fromisoformat(first_seen)
                    first_seen_str = dt.strftime("%B %d, %Y at %I:%M %p")
                    first_label = QLabel(f"First seen: {first_seen_str}")
                    first_label.setStyleSheet("font-size: 11px; color: #666;")
                    info_layout.addWidget(first_label)
                except:
                    pass
                    
            # Fun fact
            fun_facts = species_data.get('fun_facts', [])
            if fun_facts and fun_facts[0]:
                fact_label = QLabel(f"Fun fact: {fun_facts[0]}")
                fact_label.setWordWrap(True)
                fact_label.setStyleSheet("font-style: italic; color: #4CAF50; margin-top: 5px;")
                info_layout.addWidget(fact_label)
                
            info_layout.addStretch()
            species_layout.addWidget(info_widget, 1)
            
            species_group.setLayout(species_layout)
            self.species_layout.addWidget(species_group)
            
        self.species_layout.addStretch()
        
    def load_thumbnail_async(self, image_path):
        """Start asynchronous thumbnail loading"""
        if image_path in self.thumbnail_loaders:
            return  # Already loading this thumbnail
            
        loader = ThumbnailLoader(image_path)
        loader.thumbnail_loaded.connect(self.on_thumbnail_loaded)
        loader.finished.connect(lambda: self.cleanup_loader(image_path))
        
        self.thumbnail_loaders[image_path] = loader
        loader.start()
    
    def load_thumbnail_async_with_key(self, key, image_path):
        """Start asynchronous thumbnail loading with custom key"""
        if key in self.thumbnail_loaders:
            return  # Already loading this thumbnail
            
        loader = ThumbnailLoader(image_path)
        loader.thumbnail_loaded.connect(lambda path, pixmap: self.on_thumbnail_loaded_with_key(key, pixmap))
        loader.finished.connect(lambda: self.cleanup_loader(key))
        
        self.thumbnail_loaders[key] = loader
        loader.start()
    
    @pyqtSlot(str, QPixmap)
    def on_thumbnail_loaded(self, image_path, pixmap):
        """Handle completed thumbnail loading"""
        if image_path in self.label_mappings:
            label = self.label_mappings[image_path]
            label.setPixmap(pixmap)
            label.setText("")  # Clear "Loading..." text
    
    def on_thumbnail_loaded_with_key(self, key, pixmap):
        """Handle completed thumbnail loading with custom key"""
        if key in self.label_mappings:
            label = self.label_mappings[key]
            label.setPixmap(pixmap)
            label.setText("")  # Clear "Loading..." text
    
    def cleanup_loader(self, image_path):
        """Clean up finished loader thread"""
        if image_path in self.thumbnail_loaders:
            loader = self.thumbnail_loaders.pop(image_path)
            loader.deleteLater()
    
    def show_full_image(self, image_path):
        """Show full-size image in dialog"""
        dialog = ImageDialog(image_path, self)
        dialog.exec()
    
    def closeEvent(self, event):
        """Clean up threads when widget is closed"""
        for loader in self.thumbnail_loaders.values():
            loader.terminate()
            loader.wait()
        super().closeEvent(event)