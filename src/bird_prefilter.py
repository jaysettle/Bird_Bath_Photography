#!/usr/bin/env python3
"""
Local Bird Pre-filter Service using MobileNet
Reduces unnecessary OpenAI API calls by detecting if birds are present
"""

import os
import json
import time
import queue
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple
import numpy as np

try:
    from .logger import get_logger
except ImportError:
    # If relative import fails, try absolute import
    from logger import get_logger

logger = get_logger(__name__)

# Try to import TensorFlow Lite, but make it optional
try:
    import tflite_runtime.interpreter as tflite
    TFLITE_AVAILABLE = True
except ImportError:
    try:
        import tensorflow.lite as tflite
        TFLITE_AVAILABLE = True
    except ImportError:
        TFLITE_AVAILABLE = False
        logger.warning("TensorFlow Lite not available - pre-filtering disabled")

# Try to import PIL for image processing
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL not available - pre-filtering disabled")


class BirdPreFilter:
    """Pre-filters images to detect if birds are likely present"""
    
    def __init__(self, config: dict):
        """Initialize the pre-filter service"""
        self.enabled = False
        self.config = config.get('prefilter', {})
        self.confidence_threshold = self.config.get('confidence_threshold', 0.7)
        self.config_enabled = self.config.get('enabled', True)  # Store config setting
        self.model_path = Path(__file__).parent.parent / "models" / "bird_detector.tflite"
        
        # Statistics tracking
        self.stats = {
            'total_images': 0,
            'images_processed': 0,
            'birds_detected': 0,
            'no_birds_detected': 0,
            'processing_errors': 0,
            'total_processing_time': 0,
            'service_start_time': time.time(),
            'last_detection_time': None,
            'average_processing_time': 0
        }
        
        # Processing queue for non-blocking operation
        self.processing_queue = queue.Queue(maxsize=10)
        self.results_cache = {}
        self.processing_thread = None
        self.running = False
        
        # Initialize model if available
        self.interpreter = None
        self.input_details = None
        self.output_details = None
        
        if TFLITE_AVAILABLE and PIL_AVAILABLE:
            self._initialize_model()
        else:
            logger.warning("Dependencies missing - pre-filter service disabled")
    
    def _initialize_model(self):
        """Initialize the TensorFlow Lite model"""
        try:
            # Check if model exists
            if not self.model_path.exists():
                logger.info(f"Model not found at {self.model_path}")
                self.enabled = False
                return
            
            # Load TFLite model
            self.interpreter = tflite.Interpreter(model_path=str(self.model_path))
            self.interpreter.allocate_tensors()
            
            # Get input and output details
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            
            # Get input shape
            self.input_shape = self.input_details[0]['shape']
            logger.info(f"Model loaded successfully. Input shape: {self.input_shape}")
            
            # Only enable if both model loaded successfully AND config allows it
            self.enabled = self.config_enabled
            if self.enabled:
                self.start_processing_thread()
            else:
                logger.info("Pre-filter service disabled by configuration")
            
        except Exception as e:
            logger.error(f"Failed to initialize model: {e}")
            self.enabled = False
    
    def start_processing_thread(self):
        """Start the background processing thread"""
        if not self.running:
            self.running = True
            self.processing_thread = threading.Thread(
                target=self._processing_worker,
                daemon=True
            )
            self.processing_thread.start()
            logger.info("Pre-filter processing thread started")
    
    def stop(self):
        """Stop the pre-filter service"""
        self.running = False
        if self.processing_thread:
            self.processing_thread.join(timeout=2)
        logger.info("Pre-filter service stopped")
    
    def _processing_worker(self):
        """Background worker for processing images"""
        while self.running:
            try:
                # Get image from queue with timeout
                image_path = self.processing_queue.get(timeout=1)
                
                if image_path is None:  # Shutdown signal
                    break
                
                # Process the image
                result = self._process_image_internal(image_path)
                
                # Cache the result
                self.results_cache[image_path] = result
                
                # Clean old cache entries (keep last 100)
                if len(self.results_cache) > 100:
                    oldest = list(self.results_cache.keys())[0]
                    del self.results_cache[oldest]
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in processing worker: {e}")
    
    def process_image(self, image_path: str, timeout: float = 0.5) -> Dict:
        """
        Process an image to detect if birds are present
        Non-blocking with timeout
        """
        self.stats['total_images'] += 1
        
        if not self.enabled:
            return {
                'processed': False,
                'bird_detected': None,
                'confidence': 0,
                'processing_time': 0,
                'reason': 'Service disabled'
            }
        
        # Check cache first
        if image_path in self.results_cache:
            logger.debug(f"Using cached result for {image_path}")
            return self.results_cache[image_path]
        
        # Add to processing queue (non-blocking)
        try:
            self.processing_queue.put_nowait(image_path)
        except queue.Full:
            logger.warning("Processing queue full - skipping pre-filter")
            return {
                'processed': False,
                'bird_detected': None,
                'confidence': 0,
                'processing_time': 0,
                'reason': 'Queue full'
            }
        
        # Wait for result with timeout
        start_time = time.time()
        while time.time() - start_time < timeout:
            if image_path in self.results_cache:
                return self.results_cache[image_path]
            time.sleep(0.01)  # 10ms polling interval
        
        # Timeout - return unprocessed
        logger.debug(f"Pre-filter timeout for {image_path}")
        return {
            'processed': False,
            'bird_detected': None,
            'confidence': 0,
            'processing_time': timeout,
            'reason': 'Timeout'
        }
    
    def _process_image_internal(self, image_path: str) -> Dict:
        """Internal method to actually process the image"""
        start_time = time.time()
        
        try:
            # Load and preprocess image
            image = Image.open(image_path).convert('RGB')
            
            # Resize to model input size
            input_size = (self.input_shape[1], self.input_shape[2])
            image = image.resize(input_size, Image.Resampling.LANCZOS)
            
            # Convert to numpy array - model expects UINT8
            input_data = np.array(image, dtype=np.uint8)
            input_data = np.expand_dims(input_data, axis=0)  # Add batch dimension
            
            # Run inference
            self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
            self.interpreter.invoke()
            
            # Get outputs from COCO SSD MobileNet model
            # The model has multiple outputs: boxes, classes, scores, num_detections
            boxes = self.interpreter.get_tensor(self.output_details[0]['index'])[0]  # Bounding boxes
            classes = self.interpreter.get_tensor(self.output_details[1]['index'])[0]  # Class IDs
            scores = self.interpreter.get_tensor(self.output_details[2]['index'])[0]  # Confidence scores
            
            # Bird class ID in COCO is 17 (from labelmap.txt line 17)
            BIRD_CLASS_ID = 17
            
            # Find highest confidence bird detection
            bird_confidence = 0.0
            bird_detected = False
            
            for i in range(len(scores)):
                if classes[i] == BIRD_CLASS_ID and scores[i] > bird_confidence:
                    bird_confidence = float(scores[i])
                    if bird_confidence >= self.confidence_threshold:
                        bird_detected = True
            
            # Update statistics
            processing_time = time.time() - start_time
            self.stats['images_processed'] += 1
            self.stats['total_processing_time'] += processing_time
            
            if bird_detected:
                self.stats['birds_detected'] += 1
                self.stats['last_detection_time'] = time.time()
            else:
                self.stats['no_birds_detected'] += 1
            
            # Update average processing time
            self.stats['average_processing_time'] = (
                self.stats['total_processing_time'] / self.stats['images_processed']
            )
            
            logger.debug(f"Pre-filter result: bird_detected={bird_detected}, "
                        f"confidence={bird_confidence:.2f}, time={processing_time:.3f}s")
            
            return {
                'processed': True,
                'bird_detected': bird_detected,
                'confidence': bird_confidence,
                'processing_time': processing_time,
                'reason': 'Success'
            }
            
        except Exception as e:
            logger.error(f"Error processing image {image_path}: {e}")
            self.stats['processing_errors'] += 1
            
            processing_time = time.time() - start_time
            return {
                'processed': False,
                'bird_detected': None,
                'confidence': 0,
                'processing_time': processing_time,
                'reason': f'Error: {str(e)}'
            }
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        uptime = time.time() - self.stats['service_start_time']
        
        # Calculate detection rate
        if self.stats['images_processed'] > 0:
            detection_rate = (self.stats['birds_detected'] / 
                            self.stats['images_processed']) * 100
        else:
            detection_rate = 0
        
        return {
            'enabled': self.enabled,
            'uptime': uptime,
            'total_images': self.stats['total_images'],
            'images_processed': self.stats['images_processed'],
            'birds_detected': self.stats['birds_detected'],
            'no_birds_detected': self.stats['no_birds_detected'],
            'processing_errors': self.stats['processing_errors'],
            'detection_rate': detection_rate,
            'average_processing_time': self.stats['average_processing_time'],
            'last_detection_time': self.stats['last_detection_time'],
            'confidence_threshold': self.confidence_threshold,
            'queue_size': self.processing_queue.qsize()
        }
    
    def set_confidence_threshold(self, threshold: float):
        """Update confidence threshold"""
        self.confidence_threshold = max(0.0, min(1.0, threshold))
        logger.info(f"Pre-filter confidence threshold set to {self.confidence_threshold}")
    
    def download_model(self) -> bool:
        """Download the bird detection model if not present"""
        if self.model_path.exists():
            return True
        
        try:
            # Create models directory
            self.model_path.parent.mkdir(exist_ok=True)
            
            # TODO: Download from a model repository
            # For now, we'll create a placeholder
            logger.info("Model download not implemented - please manually add bird_detector.tflite")
            return False
            
        except Exception as e:
            logger.error(f"Failed to download model: {e}")
            return False