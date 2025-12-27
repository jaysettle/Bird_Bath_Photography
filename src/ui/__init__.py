#!/usr/bin/env python3
"""UI components for Bird Detection System"""

from .themes import apply_dark_theme
from .preview_widgets import InteractivePreviewLabel
from .logs_tab import LogsTab
from .services_tab import ServicesTab
from .config_tab import ConfigTab
from .gallery_tab import GalleryTab
from .camera_tab import CameraTab
from .dialogs import ImageViewerDialog

__all__ = ['apply_dark_theme', 'InteractivePreviewLabel', 'LogsTab', 'ServicesTab',
           'ConfigTab', 'GalleryTab', 'CameraTab', 'ImageViewerDialog']
