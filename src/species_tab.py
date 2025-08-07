#!/usr/bin/env python3
"""
Species Tab - Display identified bird species with thumbnails
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import re

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                           QScrollArea, QGroupBox, QGridLayout, QPushButton,
                           QDialog, QSizePolicy, QFrame)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread, pyqtSlot, QTimer
from PyQt6.QtGui import QPixmap, QPainter, QColor, QBrush, QPen, QFont, QPolygonF
from PyQt6.QtCore import QPointF, QRectF

from .logger import get_logger

logger = get_logger(__name__)


class BirdHeatmap(QWidget):
    """Weekly bird activity heatmap showing 7 days x 24 hours"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setMaximumHeight(280)
        self.setMaximumWidth(900)
        self.daily_data = {}
        self.max_count = 0
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QWidget { border-radius: 5px; }")
        
    def update_data(self, bird_identifier):
        """Update heatmap with REAL timestamp data from IdentifiedSpecies folder photos"""
        self.daily_data = defaultdict(lambda: defaultdict(int))
        self.max_count = 0
        
        # Get data from IdentifiedSpecies folder file timestamps
        identified_species_folder = Path('/home/jaysettle/BirdPhotos/IdentifiedSpecies')
        
        if identified_species_folder.exists():
            # Process all photos in IdentifiedSpecies folder
            for species_folder in identified_species_folder.iterdir():
                if species_folder.is_dir():
                    for photo_file in species_folder.glob('*.jpeg'):
                        try:
                            # Get file modification time (when photo was copied = when bird was identified)
                            mod_time = datetime.fromtimestamp(photo_file.stat().st_mtime)
                            
                            # Only include last 7 days
                            if (datetime.now() - mod_time).days <= 7:
                                day_key = mod_time.strftime("%Y-%m-%d")
                                hour = mod_time.hour
                                
                                # Increment the actual hour when this bird was identified
                                self.daily_data[day_key][hour] += 1
                                
                                if self.daily_data[day_key][hour] > self.max_count:
                                    self.max_count = self.daily_data[day_key][hour]
                                    
                        except Exception as e:
                            logger.debug(f"Failed to process photo timestamp {photo_file}: {e}")
        
        # Fallback to database sightings if no IdentifiedSpecies photos found
        if self.max_count == 0 and bird_identifier and hasattr(bird_identifier, 'database'):
            bird_identifier.load_database()
            sightings = bird_identifier.database.get('sightings', [])
            
            for sighting in sightings:
                timestamp_str = sighting.get('timestamp', '')
                if timestamp_str:
                    try:
                        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        if (datetime.now() - dt).days <= 7:
                            day_key = dt.strftime("%Y-%m-%d")
                            hour = dt.hour
                            self.daily_data[day_key][hour] += 1
                            if self.daily_data[day_key][hour] > self.max_count:
                                self.max_count = self.daily_data[day_key][hour]
                    except Exception as e:
                        logger.debug(f"Failed to parse timestamp {timestamp_str}: {e}")
        
        logger.info(f"Heatmap updated with IdentifiedSpecies folder data: {len(self.daily_data)} days, max_count: {self.max_count}")
        
        # Convert defaultdict to regular dict for logging
        regular_dict = {day: dict(hours) for day, hours in self.daily_data.items()}
        logger.info(f"Real hourly data: {regular_dict}")
        self.update()
    
    def paintEvent(self, event):
        """Paint the heatmap"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        
        # Draw rounded background
        painter.setPen(Qt.PenStyle.NoPen)
        bg_color = self.palette().window().color().darker(105)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(0, 0, width, height, 5, 5)
        
        # Margins
        left_margin = 80
        top_margin = 35
        right_margin = 20
        bottom_margin = 45
        
        # Grid dimensions
        grid_width = width - left_margin - right_margin
        grid_height = height - top_margin - bottom_margin
        
        days = 7
        hours = 24
        cell_width = grid_width / hours
        cell_height = grid_height / days
        
        # Draw bird icon and title
        painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        painter.setPen(QPen(self.palette().windowText().color()))
        
        # Simple bird icon
        bird_x, bird_y = 15, 10
        painter.setBrush(QBrush(self.palette().windowText().color()))
        painter.drawEllipse(bird_x, bird_y + 6, 12, 8)  # body
        painter.drawEllipse(bird_x + 8, bird_y + 2, 6, 6)  # head
        
        # Title
        painter.drawText(bird_x + 25, top_margin - 5, "Weekly Bird Activity Heatmap")
        
        # Draw day labels
        painter.setFont(QFont("Arial", 10))
        days_of_week = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        today = datetime.now()
        
        for i in range(days):
            day_date = today - timedelta(days=days-1-i)
            day_name = days_of_week[day_date.weekday()]
            day_str = f"{day_name} {day_date.strftime('%m/%d')}"
            
            y = top_margin + i * cell_height + cell_height/2
            painter.drawText(5, int(y-5), left_margin-10, 20, 
                           Qt.AlignmentFlag.AlignRight, day_str)
        
        # Draw hour labels (12-hour format)
        painter.setFont(QFont("Arial", 8))
        for hour in range(0, 24, 3):
            x = left_margin + hour * cell_width + cell_width/2
            if hour == 0:
                hour_str = "12AM"
            elif hour < 12:
                hour_str = f"{hour}AM"
            elif hour == 12:
                hour_str = "12PM"
            else:
                hour_str = f"{hour-12}PM"
            
            painter.drawText(int(x-20), height-bottom_margin+5, 40, 20, 
                           Qt.AlignmentFlag.AlignCenter, hour_str)
        
        # Draw heatmap cells
        cells_with_data = 0
        for day_idx in range(days):
            day_date = today - timedelta(days=days-1-day_idx)
            day_key = day_date.strftime("%Y-%m-%d")
            
            for hour in range(hours):
                x = left_margin + hour * cell_width
                y = top_margin + day_idx * cell_height
                
                # Get activity count
                count = self.daily_data.get(day_key, {}).get(hour, 0)
                if count > 0:
                    cells_with_data += 1
                
                # Set brush and pen for cell drawing
                painter.setPen(QPen(QColor(100, 100, 100), 1))  # Border
                
                # Color cells based on bird activity intensity
                if count > 0:
                    intensity = count / self.max_count
                    # Green gradient - darker green = more activity
                    green_intensity = int(255 * intensity)
                    color = QColor(
                        255 - green_intensity,  # Less red as activity increases
                        255,                    # Keep green high
                        255 - green_intensity   # Less blue as activity increases
                    )
                    painter.setBrush(QBrush(color))
                else:
                    color = QColor(248, 248, 248)  # Very light gray for no activity
                    painter.setBrush(QBrush(color))
                
                # Draw cell background and border
                cell_rect = QRectF(x, y, cell_width-1, cell_height-1)
                painter.drawRect(cell_rect)
                
                # Draw count if > 0 with large, bold text
                if count > 0:
                    painter.setPen(QPen(QColor(0, 0, 0)))  # Black text
                    painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))  # Larger, bold
                    painter.drawText(int(x), int(y), int(cell_width), int(cell_height), 
                                   Qt.AlignmentFlag.AlignCenter, str(count))
        
        
        # Draw legend
        painter.setFont(QFont("Arial", 8))
        painter.setPen(QPen(self.palette().windowText().color()))
        painter.drawText(left_margin, height-20, grid_width, 20,
                        Qt.AlignmentFlag.AlignCenter, "Time of Day")


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


class SpeciesGalleryDialog(QDialog):
    """Dialog to show all photos for a specific species"""
    def __init__(self, species_data, all_photos, parent=None):
        super().__init__(parent)
        self.species_data = species_data
        self.all_photos = all_photos
        self.current_index = 0
        
        # Set window properties
        species_name = species_data.get('common_name', species_data.get('species_common', 'Unknown Species'))
        self.setWindowTitle(f"{species_name} - {len(all_photos)} photos")
        self.setModal(True)
        self.resize(900, 700)
        
        self.setup_ui()
        self.load_current_image()
    
    def setup_ui(self):
        """Setup the gallery dialog UI"""
        layout = QVBoxLayout()
        
        # Title and navigation info
        title_layout = QHBoxLayout()
        species_name = self.species_data.get('common_name', self.species_data.get('species_common', 'Unknown Species'))
        scientific_name = self.species_data.get('scientific_name', '')
        
        title_label = QLabel(f"{species_name}")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2196F3;")
        title_layout.addWidget(title_label)
        
        if scientific_name:
            scientific_label = QLabel(f"({scientific_name})")
            scientific_label.setStyleSheet("font-size: 12px; font-style: italic; color: #666;")
            title_layout.addWidget(scientific_label)
        
        title_layout.addStretch()
        
        # Image counter
        self.counter_label = QLabel()
        self.counter_label.setStyleSheet("font-size: 12px; color: #999;")
        title_layout.addWidget(self.counter_label)
        
        layout.addLayout(title_layout)
        
        # Image display area
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #000; border: 1px solid #555;")
        self.image_label.setMinimumSize(600, 400)
        layout.addWidget(self.image_label)
        
        # Image info and species details area
        info_layout = QHBoxLayout()
        
        # Current image info
        self.image_info = QLabel("Loading image info...")
        self.image_info.setStyleSheet("background-color: #2b2b2b; border: 1px solid #444; padding: 8px; border-radius: 4px; color: #e0e0e0;")
        self.image_info.setMaximumHeight(60)
        self.image_info.setWordWrap(True)
        info_layout.addWidget(self.image_info)
        
        # Species details  
        species_info_text = []
        if self.species_data.get('conservation_status'):
            species_info_text.append(f"Conservation: {self.species_data['conservation_status']}")
        if self.species_data.get('sighting_count'):
            species_info_text.append(f"Sightings: {self.species_data['sighting_count']}")
        if self.species_data.get('fun_facts'):
            facts = self.species_data.get('fun_facts', [])
            if facts and facts[0]:
                species_info_text.append(f"Fun fact: {facts[0][:100]}...")
        
        self.species_info = QLabel(" | ".join(species_info_text) if species_info_text else "No additional species information available")
        self.species_info.setStyleSheet("background-color: #2b2b2b; border: 1px solid #444; padding: 8px; border-radius: 4px; color: #e0e0e0;")
        self.species_info.setMaximumHeight(60)
        self.species_info.setWordWrap(True)
        info_layout.addWidget(self.species_info)
        
        layout.addLayout(info_layout)
        
        # Navigation controls
        nav_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self.previous_image)
        nav_layout.addWidget(self.prev_btn)
        
        nav_layout.addStretch()
        
        # Thumbnail strip (show 10 at a time)
        self.thumb_layout = QHBoxLayout()
        self.thumb_layout.setSpacing(5)
        self.thumb_scroll = QScrollArea()
        self.thumb_widget = QWidget()
        self.thumb_widget.setLayout(self.thumb_layout)
        self.thumb_widget.setStyleSheet("background-color: #2b2b2b;")
        self.thumb_scroll.setWidget(self.thumb_widget)
        self.thumb_scroll.setFixedHeight(80)
        self.thumb_scroll.setStyleSheet("background-color: #2b2b2b; border: 1px solid #444; border-radius: 4px;")
        self.thumb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.thumb_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_layout.addWidget(self.thumb_scroll)
        
        nav_layout.addStretch()
        
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self.next_image)
        nav_layout.addWidget(self.next_btn)
        
        layout.addLayout(nav_layout)
        
        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Load thumbnails
        self.load_thumbnails()
    
    def load_thumbnails(self):
        """Load thumbnail strip"""
        self.thumb_buttons = []
        for i, photo_path in enumerate(self.all_photos):
            thumb_btn = QPushButton()
            thumb_btn.setFixedSize(60, 45)
            thumb_btn.clicked.connect(lambda checked, idx=i: self.go_to_image(idx))
            
            # Style the thumbnail buttons
            thumb_btn.setStyleSheet("""
                QPushButton {
                    border: 2px solid #555;
                    border-radius: 3px;
                    background-color: #3a3a3a;
                    color: #e0e0e0;
                }
                QPushButton:hover {
                    border: 2px solid #2196F3;
                }
            """)
            
            try:
                pixmap = QPixmap(photo_path)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(56, 41, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.FastTransformation)
                    thumb_btn.setIcon(QIcon(scaled))
                    thumb_btn.setIconSize(scaled.size())
                else:
                    thumb_btn.setText(str(i+1))
                    thumb_btn.setStyleSheet(thumb_btn.styleSheet() + "color: #e0e0e0;")
            except Exception:
                thumb_btn.setText(str(i+1))
                thumb_btn.setStyleSheet(thumb_btn.styleSheet() + "color: #e0e0e0;")
            
            self.thumb_buttons.append(thumb_btn)
            self.thumb_layout.addWidget(thumb_btn)
        
        # Highlight the first image
        if self.thumb_buttons:
            self.highlight_current_thumbnail()
    
    def load_current_image(self):
        """Load and display the current image"""
        if 0 <= self.current_index < len(self.all_photos):
            photo_path = self.all_photos[self.current_index]
            
            try:
                pixmap = QPixmap(photo_path)
                if not pixmap.isNull():
                    # Scale to fit display area while maintaining aspect ratio
                    scaled = pixmap.scaled(600, 400, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
                    self.image_label.setPixmap(scaled)
                    
                    # Update image info
                    filename = os.path.basename(photo_path)
                    file_size = os.path.getsize(photo_path) / 1024  # KB
                    mod_time = datetime.fromtimestamp(os.path.getmtime(photo_path))
                    self.image_info.setText(f"File: {filename} | Size: {file_size:.1f} KB | Modified: {mod_time.strftime('%Y-%m-%d %H:%M')}")
                else:
                    self.image_label.setText("Image not found")
                    self.image_info.setText("Image file not found")
            except Exception as e:
                self.image_label.setText(f"Error loading image: {e}")
                self.image_info.setText(f"Error: {e}")
            
            # Update counter and navigation buttons
            self.counter_label.setText(f"{self.current_index + 1} of {len(self.all_photos)}")
            self.prev_btn.setEnabled(self.current_index > 0)
            self.next_btn.setEnabled(self.current_index < len(self.all_photos) - 1)
            
            # Highlight current thumbnail
            self.highlight_current_thumbnail()
    
    def highlight_current_thumbnail(self):
        """Highlight the current thumbnail in the strip"""
        if hasattr(self, 'thumb_buttons'):
            for i, btn in enumerate(self.thumb_buttons):
                if i == self.current_index:
                    btn.setStyleSheet("""
                        QPushButton {
                            border: 3px solid #2196F3;
                            border-radius: 3px;
                            background-color: #1565C0;
                            color: #ffffff;
                        }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton {
                            border: 2px solid #555;
                            border-radius: 3px;
                            background-color: #3a3a3a;
                            color: #e0e0e0;
                        }
                        QPushButton:hover {
                            border: 2px solid #2196F3;
                        }
                    """)
    
    def previous_image(self):
        """Go to previous image"""
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_image()
    
    def next_image(self):
        """Go to next image"""
        if self.current_index < len(self.all_photos) - 1:
            self.current_index += 1
            self.load_current_image()
    
    def go_to_image(self, index):
        """Go to specific image by index"""
        if 0 <= index < len(self.all_photos):
            self.current_index = index
            self.load_current_image()
    
    def keyPressEvent(self, event):
        """Handle keyboard navigation"""
        if event.key() == Qt.Key.Key_Left:
            self.previous_image()
        elif event.key() == Qt.Key.Key_Right:
            self.next_image()
        elif event.key() == Qt.Key.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)


class SpeciesTab(QWidget):
    """Tab for displaying identified bird species"""
    
    def __init__(self, bird_identifier):
        super().__init__()
        self.bird_identifier = bird_identifier
        self.first_load = True
        self.last_species_count = 0
        self.last_total_photos = 0
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the UI"""
        layout = QVBoxLayout()
        
        # Header with statistics
        header_layout = QVBoxLayout()
        
        # Title
        header = QLabel("Identified Bird Species")
        header.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        header_layout.addWidget(header)
        
        # Statistics section
        self.stats_widget = QGroupBox("Species Statistics")
        stats_layout = QGridLayout()
        
        # Create stat labels
        self.total_species_label = QLabel("Total Species: 0")
        self.total_sightings_label = QLabel("Total Sightings: 0")
        self.today_sightings_label = QLabel("Today's Sightings: 0")
        self.week_sightings_label = QLabel("This Week: 0")
        self.most_common_label = QLabel("Most Common: None")
        self.rare_species_label = QLabel("Rare Species: 0")
        
        # Style the labels
        stat_style = "padding: 5px; font-size: 12px;"
        for label in [self.total_species_label, self.total_sightings_label, 
                     self.today_sightings_label, self.week_sightings_label,
                     self.most_common_label, self.rare_species_label]:
            label.setStyleSheet(stat_style)
        
        # Arrange in grid
        stats_layout.addWidget(self.total_species_label, 0, 0)
        stats_layout.addWidget(self.total_sightings_label, 0, 1)
        stats_layout.addWidget(self.today_sightings_label, 0, 2)
        stats_layout.addWidget(self.week_sightings_label, 1, 0)
        stats_layout.addWidget(self.most_common_label, 1, 1)
        stats_layout.addWidget(self.rare_species_label, 1, 2)
        
        self.stats_widget.setLayout(stats_layout)
        header_layout.addWidget(self.stats_widget)
        
        # Heatmap
        self.heatmap_widget = BirdHeatmap()
        header_layout.addWidget(self.heatmap_widget)
        
        layout.addLayout(header_layout)
        
        # Status and refresh section
        top_section = QHBoxLayout()
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #666; padding: 5px;")
        top_section.addWidget(self.status_label)
        
        top_section.addStretch()  # Push refresh button to the right
        
        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_species)
        refresh_btn.setMaximumWidth(100)
        top_section.addWidget(refresh_btn)
        
        layout.addLayout(top_section)
        
        # Scroll area for species
        scroll = QScrollArea()
        self.species_widget = QWidget()
        self.species_layout = QVBoxLayout(self.species_widget)
        
        scroll.setWidget(self.species_widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        
        self.setLayout(layout)
        
        # Track if we need to refresh when shown
        self.needs_refresh = False
    
    def showEvent(self, event):
        """Handle tab being shown - refresh if needed"""
        super().showEvent(event)
        if self.first_load:
            self.load_species()
            self.first_load = False
        elif self.needs_refresh:
            # Check if there are actual changes before refreshing
            if self._has_new_photos():
                self.load_species()
            self.needs_refresh = False
        
    def load_species(self):
        """Load and display species from database"""
        # Show loading status
        self.status_label.setText("Loading species...")
        self.status_label.setStyleSheet("color: #2196F3; padding: 5px;")  # Blue color
        
        # Process events to update UI immediately
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        
        # Load species data
        self._load_species_deferred()
    
    def _load_species_deferred(self):
        """Deferred species loading"""
        # Clear existing widgets
        while self.species_layout.count():
            child = self.species_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        if not self.bird_identifier:
            self.species_layout.addWidget(QLabel("Bird identifier not available"))
            self.status_label.setText("Bird identifier not available")
            self.status_label.setStyleSheet("color: #f44336; padding: 5px;")  # Red color
            return
            
        # Load database
        self.bird_identifier.load_database()
        species_dict = self.bird_identifier.database.get('species', {})
        
        # Calculate and display statistics
        self._update_statistics(species_dict)
        
        # Update heatmap
        self.heatmap_widget.update_data(self.bird_identifier)
        
        if not species_dict:
            no_species = QLabel("Be sure to configure your OpenAI API key for this feature in the Configuration tab.")
            no_species.setStyleSheet("color: gray; padding: 20px;")
            self.species_layout.addWidget(no_species)
            self.status_label.setText("No species identified yet")
            self.status_label.setStyleSheet("color: #666; padding: 5px;")
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
            
            # Get photos from IdentifiedSpecies folder
            photo_gallery = self._get_species_photos(species_data)
            
            # Filter out missing photos for better performance
            all_existing_photos = [path for path in photo_gallery if os.path.exists(path)]
            total_available = len(all_existing_photos)
            
            # Show up to 8 images (leaving space for "Show More" if needed)
            max_display = 8 if total_available > 9 else 9
            existing_photos = all_existing_photos[-max_display:]
            
            # Create thumbnails for existing photos only
            row, col = 0, 0
            for i, photo_path in enumerate(existing_photos):
                thumb_label = ClickableLabel()
                thumb_label.setFixedSize(100, 75)  # 4:3 aspect ratio
                thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb_label.setStyleSheet("background-color: #333; color: gray; border: 1px solid #555;")
                
                # Load thumbnail with basic error handling
                try:
                    pixmap = QPixmap(photo_path)
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(100, 75, Qt.AspectRatioMode.KeepAspectRatio,
                                             Qt.TransformationMode.FastTransformation)
                        thumb_label.setPixmap(scaled)
                    else:
                        continue  # Skip failed images
                except Exception as e:
                    logger.debug(f"Skipping thumbnail with error: {e}")
                    continue  # Skip images that fail to load
                
                # Connect click to show full image
                thumb_label.clicked.connect(lambda p=photo_path: self.show_full_image(p))
                
                gallery_layout.addWidget(thumb_label, row, col)
                
                col += 1
                if col >= 3:
                    col = 0
                    row += 1
            
            # Add "Show More" button if there are more than 9 images
            total_photos = len(existing_photos)
            if total_available > 9:
                show_more_btn = QPushButton(f"+{total_available - 8}\nmore")
                show_more_btn.setFixedSize(100, 75)
                show_more_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2196F3;
                        color: white;
                        border: 2px solid #1976D2;
                        border-radius: 8px;
                        font-size: 11px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #1976D2;
                        border-color: #1565C0;
                    }
                    QPushButton:pressed {
                        background-color: #1565C0;
                    }
                """)
                # Pass species data with both the original data and scientific name
                show_more_btn.clicked.connect(
                    lambda checked=False, sd=species_data, sn=scientific_name, ap=all_existing_photos: 
                    self.show_species_gallery({**sd, 'scientific_name': sn}, ap)
                )
                gallery_layout.addWidget(show_more_btn, row, col)
                col += 1
                if col >= 3:
                    col = 0
                    row += 1
                total_photos += 1  # Account for the button
            
            # Add empty labels to fill remaining slots (up to 3x3 grid)
            remaining_slots = 9 - total_photos
            
            for _ in range(remaining_slots):
                empty_label = QLabel()
                empty_label.setFixedSize(100, 75)  # 4:3 aspect ratio
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
        
        # Update status and tracking counts when done
        species_count = len(species_dict)
        total_photos = sum(len(data.get('photo_gallery', [])) for data in species_dict.values())
        
        self.last_species_count = species_count
        self.last_total_photos = total_photos
        
        self.status_label.setText(f"Loaded {species_count} species")
        self.status_label.setStyleSheet("color: #4CAF50; padding: 5px;")  # Green color
    
    def _has_new_photos(self):
        """Check if there are new photos since last load"""
        if not self.bird_identifier:
            return False
            
        # Load current database state
        self.bird_identifier.load_database()
        species_dict = self.bird_identifier.database.get('species', {})
        
        # Count total photos
        total_photos = 0
        for species_data in species_dict.values():
            gallery = species_data.get('photo_gallery', [])
            total_photos += len(gallery)
            
        # Check if counts have changed
        species_count = len(species_dict)
        has_changes = (species_count != self.last_species_count or 
                      total_photos != self.last_total_photos)
        
        return has_changes
    
    def _update_statistics(self, species_dict):
        """Update species statistics"""
        if not species_dict:
            return
            
        # Calculate statistics
        total_species = len(species_dict)
        total_sightings = sum(data.get('sighting_count', 0) for data in species_dict.values())
        
        # Today's sightings
        today = datetime.now().date()
        today_sightings = 0
        
        # Week sightings
        week_start = today - timedelta(days=7)
        week_sightings = 0
        
        # Find most common species
        most_common = None
        max_sightings = 0
        
        # Count rare species (seen only once)
        rare_species = 0
        
        for species_name, data in species_dict.items():
            count = data.get('sighting_count', 0)
            
            # Most common
            if count > max_sightings:
                max_sightings = count
                most_common = data.get('common_name', species_name)
            
            # Rare species
            if count == 1:
                rare_species += 1
            
            # Count recent sightings from IdentifiedSpecies folder
            common_name = data.get('common_name', 'Unknown')
            scientific_name = species_name  # species_name is the key
            
            # Create folder name matching the AI identifier logic
            folder_name = f"{common_name}_{scientific_name}".replace(' ', '_').replace('/', '_')
            folder_name = ''.join(c for c in folder_name if c.isalnum() or c in ['_', '-'])
            
            species_folder = Path('/home/jaysettle/BirdPhotos/IdentifiedSpecies') / folder_name
            
            if species_folder.exists():
                for photo_file in species_folder.glob('*.jpeg'):
                    try:
                        # Get file modification time (when photo was copied = when bird was identified)
                        mod_time = datetime.fromtimestamp(photo_file.stat().st_mtime)
                        photo_date = mod_time.date()
                        
                        if photo_date == today:
                            today_sightings += 1
                        if photo_date >= week_start:
                            week_sightings += 1
                    except Exception as e:
                        logger.debug(f"Error processing photo timestamp {photo_file}: {e}")
        
        # Update labels
        self.total_species_label.setText(f"Total Species: {total_species}")
        self.total_sightings_label.setText(f"Total Sightings: {total_sightings}")
        self.today_sightings_label.setText(f"Today's Sightings: {today_sightings}")
        self.week_sightings_label.setText(f"This Week: {week_sightings}")
        self.most_common_label.setText(f"Most Common: {most_common or 'None'}")
        self.rare_species_label.setText(f"Rare Species: {rare_species}")
    
    
    def _get_species_photos(self, species_data):
        """Get photos from IdentifiedSpecies folder for a species"""
        photos = []
        try:
            common_name = species_data.get('common_name', 'Unknown')
            scientific_name = species_data.get('scientific_name', 'unknown')
            
            # Create folder name matching the AI identifier logic
            folder_name = f"{common_name}_{scientific_name}".replace(' ', '_').replace('/', '_')
            folder_name = ''.join(c for c in folder_name if c.isalnum() or c in ['_', '-'])
            
            species_folder = Path('/home/jaysettle/BirdPhotos/IdentifiedSpecies') / folder_name
            
            if species_folder.exists():
                # Get all JPEG files in the species folder, sorted by modification time (newest first)
                photo_files = list(species_folder.glob('*.jpeg'))
                photo_files.extend(species_folder.glob('*.jpg'))
                photo_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                photos = [str(p) for p in photo_files]
            
            # Fallback to database photo_gallery if IdentifiedSpecies folder is empty
            if not photos:
                photos = species_data.get('photo_gallery', [])
                if not photos and 'last_photo' in species_data:
                    photos = [species_data['last_photo']]
                    
        except Exception as e:
            logger.debug(f"Error getting species photos: {e}")
            # Fallback to database
            photos = species_data.get('photo_gallery', [])
            if not photos and 'last_photo' in species_data:
                photos = [species_data['last_photo']]
        
        return photos
    
    def show_full_image(self, image_path):
        """Show full-size image in dialog"""
        dialog = ImageDialog(image_path, self)
        dialog.exec()
    
    def show_species_gallery(self, species_data, all_photos):
        """Show a gallery dialog with all photos for this species"""
        dialog = SpeciesGalleryDialog(species_data, all_photos, self)
        dialog.exec()