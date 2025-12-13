#!/usr/bin/env python3
"""Dark theme styling for Bird Detection System"""

from PyQt6.QtGui import QPalette, QColor


def apply_dark_theme(app):
    """Apply dark theme to the application"""
    # Dark palette
    palette = QPalette()

    # Window colors
    palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))

    # Base colors (text input backgrounds)
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))

    # Text colors
    palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))

    # Button colors
    palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))

    # Highlight colors
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))

    # Link colors
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor(128, 0, 128))

    # Disabled colors
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(80, 80, 80))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor(127, 127, 127))

    app.setPalette(palette)

    # Additional dark theme styling
    app.setStyleSheet("""
        QMainWindow {
            background-color: #353535;
        }

        QTabWidget::pane {
            border: 1px solid #454545;
            background-color: #353535;
        }

        QTabBar::tab {
            background-color: #454545;
            color: #ffffff;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }

        QTabBar::tab:selected {
            background-color: #2a82da;
            color: #000000;
        }

        QTabBar::tab:hover {
            background-color: #555555;
        }

        QGroupBox {
            font-weight: bold;
            border: 2px solid #454545;
            border-radius: 8px;
            margin-top: 10px;
            padding-top: 10px;
            background-color: #404040;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
            color: #ffffff;
        }

        QPushButton {
            background-color: #454545;
            border: 2px solid #555555;
            border-radius: 6px;
            padding: 8px 16px;
            color: #ffffff;
            font-weight: bold;
        }

        QPushButton:hover {
            background-color: #555555;
            border: 2px solid #666666;
        }

        QPushButton:pressed {
            background-color: #2a82da;
            border: 2px solid #1a72da;
        }

        QSlider::groove:horizontal {
            border: 1px solid #454545;
            height: 8px;
            background: #252525;
            border-radius: 4px;
        }

        QSlider::handle:horizontal {
            background: #2a82da;
            border: 1px solid #1a72da;
            width: 18px;
            height: 18px;
            border-radius: 9px;
            margin: -5px 0;
        }

        QSlider::handle:horizontal:hover {
            background: #3a92ea;
        }

        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 2px solid #555555;
            border-radius: 3px;
            background-color: #353535;
        }

        QCheckBox::indicator:checked {
            background-color: #2a82da;
            border: 2px solid #1a72da;
        }

        QCheckBox::indicator:checked:hover {
            background-color: #3a92ea;
        }

        QTableWidget {
            background-color: #353535;
            alternate-background-color: #404040;
            gridline-color: #454545;
            border: 1px solid #454545;
            border-radius: 4px;
        }

        QTableWidget::item {
            padding: 8px;
            border: none;
        }

        QTableWidget::item:selected {
            background-color: #2a82da;
            color: #000000;
        }

        QHeaderView::section {
            background-color: #454545;
            color: #ffffff;
            padding: 8px;
            border: 1px solid #555555;
            font-weight: bold;
        }

        QTextEdit {
            background-color: #252525;
            color: #ffffff;
            border: 1px solid #454545;
            border-radius: 4px;
            padding: 4px;
            font-family: 'Courier New', monospace;
        }

        QLabel {
            color: #ffffff;
        }

        QStatusBar {
            background-color: #454545;
            color: #ffffff;
            border-top: 1px solid #555555;
        }

        QScrollBar:vertical {
            background: #353535;
            width: 16px;
            border: 1px solid #454545;
        }

        QScrollBar::handle:vertical {
            background: #555555;
            border-radius: 8px;
            min-height: 20px;
        }

        QScrollBar::handle:vertical:hover {
            background: #666666;
        }

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            border: none;
            background: none;
        }

        QScrollBar:horizontal {
            background: #353535;
            height: 16px;
            border: 1px solid #454545;
        }

        QScrollBar::handle:horizontal {
            background: #555555;
            border-radius: 8px;
            min-width: 20px;
        }

        QScrollBar::handle:horizontal:hover {
            background: #666666;
        }

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            border: none;
            background: none;
        }
    """)
