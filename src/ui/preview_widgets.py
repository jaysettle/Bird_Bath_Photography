#!/usr/bin/env python3
"""Interactive preview widget for camera ROI selection and focus control"""

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor

from src.logger import get_logger

logger = get_logger(__name__)


class InteractivePreviewLabel(QLabel):
    """Custom QLabel that handles mouse events for ROI selection and focus control"""
    roi_selected = pyqtSignal(QPoint, QPoint)
    focus_point_clicked = pyqtSignal(QPoint)

    def __init__(self):
        super().__init__()
        self.base_width = 960
        self.base_height = 540
        self.aspect_ratio = self.base_width / self.base_height

        self.setFixedSize(self.base_width, self.base_height)
        self.setStyleSheet("border: 2px solid #555555; background-color: #252525; border-radius: 6px;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("Camera Preview")
        self.setScaledContents(False)

        self.drawing = False
        self.has_dragged = False
        self.potential_roi_start = QPoint()
        self.roi_start = QPoint()
        self.roi_end = QPoint()
        self.roi_rect = QRect()
        self.current_pixmap = None

        self.focus_click_point = None
        self.focus_indicator_timer = QTimer()
        self.focus_indicator_timer.timeout.connect(self.clear_focus_indicator)
        self.focus_indicator_timer.setSingleShot(True)

        self.right_button_pressed = False
        self.right_click_start = None
        self.drag_threshold = 5

    def heightForWidth(self, width):
        """Maintain 16:9 aspect ratio (locked)"""
        return int(width * 9 / 16)

    def mousePressEvent(self, event):
        """Handle mouse press for ROI selection or focus control"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.potential_roi_start = event.pos()
            self.has_dragged = False
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_button_pressed = True
            self.right_click_start = event.pos()

    def mouseMoveEvent(self, event):
        """Handle mouse move for ROI selection"""
        if event.buttons() & Qt.MouseButton.LeftButton and hasattr(self, 'potential_roi_start'):
            if not self.drawing:
                distance = ((event.pos().x() - self.potential_roi_start.x()) ** 2 +
                           (event.pos().y() - self.potential_roi_start.y()) ** 2) ** 0.5
                if distance > 10:
                    self.drawing = True
                    self.has_dragged = True
                    self.roi_start = self.potential_roi_start
                    self.roi_end = event.pos()
                    self.update()
            else:
                self.roi_end = event.pos()
                self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release events"""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.drawing:
                self.drawing = False
                self.roi_end = event.pos()
                self.update()

                width = abs(self.roi_end.x() - self.roi_start.x())
                height = abs(self.roi_end.y() - self.roi_start.y())
                if width > 20 and height > 20:
                    self.roi_selected.emit(self.roi_start, self.roi_end)
                else:
                    self.update()
            self.has_dragged = False

        elif event.button() == Qt.MouseButton.RightButton and self.right_button_pressed:
            self.right_button_pressed = False

            if self.right_click_start:
                distance = ((event.pos().x() - self.right_click_start.x()) ** 2 +
                           (event.pos().y() - self.right_click_start.y()) ** 2) ** 0.5

                if distance <= self.drag_threshold:
                    self.focus_click_point = self.right_click_start
                    self.focus_indicator_timer.start(2000)
                    self.update()
                    self.focus_point_clicked.emit(self.right_click_start)
                    logger.info(f"Focus point clicked at: {self.right_click_start.x()}, {self.right_click_start.y()}")

            self.right_click_start = None

    def paintEvent(self, event):
        """Custom paint event to draw ROI rectangle and focus indicator"""
        super().paintEvent(event)

        if self.current_pixmap:
            painter = QPainter(self)

            if not self.roi_rect.isEmpty():
                painter.setPen(QPen(QColor(0, 255, 100), 3))
                painter.drawRect(self.roi_rect)

                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.setBrush(QColor(0, 255, 100, 180))
                label_rect = QRect(self.roi_rect.topLeft() + QPoint(5, -20),
                                  QPoint(self.roi_rect.topLeft().x() + 85, self.roi_rect.topLeft().y() - 5))
                painter.drawRect(label_rect)
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.drawText(self.roi_rect.topLeft() + QPoint(8, -8), "MOTION ROI")

            if self.drawing:
                painter.setPen(QPen(QColor(255, 255, 0), 2))
                temp_rect = QRect(self.roi_start, self.roi_end)
                painter.drawRect(temp_rect.normalized())

            painter.end()

    def setPixmap(self, pixmap):
        """Override setPixmap to store current pixmap"""
        self.current_pixmap = pixmap
        super().setPixmap(pixmap)

    def clear_focus_indicator(self):
        """Clear the focus click indicator"""
        self.focus_click_point = None
        self.update()

    def clear_roi(self):
        """Clear the ROI rectangle"""
        self.roi_rect = QRect()
        self.drawing = False
        self.has_dragged = False
        self.potential_roi_start = QPoint()
        self.roi_start = QPoint()
        self.roi_end = QPoint()
        self.update()

    def set_roi_rect(self, x, y, width, height):
        """Set the ROI rectangle programmatically"""
        self.roi_rect = QRect(x, y, width, height)
        self.update()
