#!/usr/bin/env python3
"""Gallery loader thread for background image loading"""

from datetime import datetime
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QPixmap

from src.logger import get_logger

logger = get_logger(__name__)


class GalleryLoader(QThread):
    """Background thread for loading gallery images"""
    progress = pyqtSignal(int, int, str)  # current, total, message
    image_loaded = pyqtSignal(object, str, float)  # widget_data, date_str, mtime
    finished_loading = pyqtSignal()

    def __init__(self, storage_dir):
        super().__init__()
        self.storage_dir = storage_dir
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        """Load images in background thread"""
        try:
            if not self.storage_dir.exists():
                self.finished_loading.emit()
                return

            self.progress.emit(0, 0, "Scanning for images...")
            image_files = []
            for ext in ['*.jpg', '*.jpeg', '*.png']:
                image_files.extend(self.storage_dir.glob(ext))

            if not image_files:
                self.finished_loading.emit()
                return

            image_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            total_images = len(image_files)

            for idx, image_path in enumerate(image_files):
                if not self._is_running:
                    break

                self.progress.emit(idx + 1, total_images, f"Loading {image_path.name}...")

                mtime = image_path.stat().st_mtime
                date_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')

                try:
                    pixmap = QPixmap(str(image_path))
                    if not pixmap.isNull() and self._is_running:
                        scaled_pixmap = pixmap.scaled(180, 135, Qt.AspectRatioMode.KeepAspectRatio,
                                                     Qt.TransformationMode.FastTransformation)

                        widget_data = {
                            'path': str(image_path),
                            'name': image_path.name,
                            'pixmap': scaled_pixmap,
                            'mtime': mtime
                        }
                        if self._is_running:
                            self.image_loaded.emit(widget_data, date_str, mtime)
                except Exception as e:
                    logger.debug(f"Failed to load thumbnail for {image_path}: {e}")

                if not self._is_running:
                    break

                if idx % 10 == 0:
                    self.msleep(10)

            self.finished_loading.emit()

        except Exception as e:
            logger.error(f"Error in gallery loader: {e}")
            self.finished_loading.emit()
