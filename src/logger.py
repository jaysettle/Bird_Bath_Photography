#!/usr/bin/env python3
"""
Logging utilities with systemd journal integration
"""

import logging
import logging.handlers
import os
import json
from datetime import datetime
from pathlib import Path

try:
    from systemd import journal
    SYSTEMD_AVAILABLE = True
except ImportError:
    SYSTEMD_AVAILABLE = False

class SystemdJournalHandler(logging.Handler):
    """Custom handler that sends logs to systemd journal"""
    
    def __init__(self):
        super().__init__()
        self.journal_available = SYSTEMD_AVAILABLE
        
    def emit(self, record):
        if not self.journal_available:
            return
            
        try:
            msg = self.format(record)
            # Map logging levels to journal priorities
            level_map = {
                logging.DEBUG: journal.LOG_DEBUG,
                logging.INFO: journal.LOG_INFO,
                logging.WARNING: journal.LOG_WARNING,
                logging.ERROR: journal.LOG_ERR,
                logging.CRITICAL: journal.LOG_CRIT
            }
            
            priority = level_map.get(record.levelno, journal.LOG_INFO)
            
            journal.send(
                msg,
                PRIORITY=priority,
                LOGGER_NAME=record.name,
                CODE_FILE=record.pathname,
                CODE_LINE=record.lineno,
                CODE_FUNC=record.funcName,
                SYSLOG_IDENTIFIER="bird-detection"
            )
        except Exception:
            # Don't let logging errors crash the application
            pass

class ColoredConsoleHandler(logging.StreamHandler):
    """Console handler with colored output"""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, '')
        reset = self.COLORS['RESET']
        
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        
        # Create colored log message
        formatted = f"{log_color}[{timestamp}] {record.levelname:8s} {record.name}: {record.getMessage()}{reset}"
        
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"
            
        return formatted

def setup_logging(config_path=None):
    """Setup logging with file, console, and systemd journal handlers"""
    
    # Load configuration
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        log_config = config.get('logging', {})
    else:
        log_config = {}
    
    # Get log level
    level = getattr(logging, log_config.get('level', 'INFO'))
    
    # Create logs directory
    log_dir = Path(__file__).parent.parent / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / 'bird_detection.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=log_config.get('backup_count', 5)
    )
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler with colors
    console_handler = ColoredConsoleHandler()
    root_logger.addHandler(console_handler)
    
    # Systemd journal handler
    if log_config.get('journal_integration', True):
        journal_handler = SystemdJournalHandler()
        journal_formatter = logging.Formatter('%(name)s: %(message)s')
        journal_handler.setFormatter(journal_formatter)
        root_logger.addHandler(journal_handler)
    
    return root_logger

def get_logger(name):
    """Get a logger for a specific module"""
    return logging.getLogger(name)

# Log viewer for GUI
class LogBuffer:
    """Thread-safe log buffer for GUI display"""
    
    def __init__(self, max_lines=1000):
        self.max_lines = max_lines
        self.lines = []
        self._lock = None
        
    def add_line(self, line):
        """Add a log line to the buffer"""
        if self._lock is None:
            import threading
            self._lock = threading.Lock()
            
        with self._lock:
            self.lines.append(line)
            if len(self.lines) > self.max_lines:
                self.lines.pop(0)
    
    def get_lines(self):
        """Get all log lines"""
        if self._lock is None:
            return self.lines.copy()
            
        with self._lock:
            return self.lines.copy()
    
    def clear(self):
        """Clear all log lines"""
        if self._lock is None:
            import threading
            self._lock = threading.Lock()
            
        with self._lock:
            self.lines.clear()

# Global log buffer for GUI
log_buffer = LogBuffer()

class GuiLogHandler(logging.Handler):
    """Handler that stores logs in buffer for GUI display"""
    
    def emit(self, record):
        try:
            msg = self.format(record)
            log_buffer.add_line(msg)
        except Exception:
            pass

def setup_gui_logging():
    """Setup logging specifically for GUI display"""
    gui_handler = GuiLogHandler()
    gui_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s: %(message)s'
    )
    gui_handler.setFormatter(gui_formatter)
    
    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(gui_handler)
    
    return gui_handler