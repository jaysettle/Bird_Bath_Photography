#!/usr/bin/env python3
"""
Local Bird Species Classifier using MobileNet V2
Classifies bird images into 525 different bird species
"""

import os
import json
import time
import queue
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
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
        logger.warning("TensorFlow Lite not available - classification disabled")

# Try to import PIL for image processing
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL not available - classification disabled")


class BirdClassifier:
    """Classifies bird images into species using MobileNet V2"""
    
    def __init__(self, config: dict = None):
        """Initialize the bird classifier service"""
        self.enabled = False
        self.config = config or {}
        self.classifier_config = self.config.get('classifier', {})
        self.confidence_threshold = self.classifier_config.get('confidence_threshold', 0.1)
        self.top_k = self.classifier_config.get('top_k', 5)  # Number of top predictions to return
        
        # Model paths
        self.model_path = Path(__file__).parent.parent / "models" / "bird_species_classifier.tflite"
        self.labels_path = Path(__file__).parent.parent / "models" / "bird_species_labels.txt"
        
        # Statistics tracking
        self.stats = {
            'total_images': 0,
            'images_processed': 0,
            'processing_errors': 0,
            'total_processing_time': 0,
            'service_start_time': time.time(),
            'last_classification_time': None,
            'average_processing_time': 0,
            'species_counts': {}  # Track counts for each species
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
        self.labels = []
        
        if TFLITE_AVAILABLE and PIL_AVAILABLE:
            self._initialize_model()
        else:
            logger.warning("Dependencies missing - classifier service disabled")
    
    def _initialize_model(self):
        """Initialize the TensorFlow Lite model and load labels"""
        try:
            # Check if model exists
            if not self.model_path.exists():
                logger.error(f"Model not found at {self.model_path}")
                self.enabled = False
                return
            
            # Check if labels file exists
            if not self.labels_path.exists():
                logger.error(f"Labels file not found at {self.labels_path}")
                self.enabled = False
                return
            
            # Load labels
            with open(self.labels_path, 'r') as f:
                self.labels = [line.strip() for line in f.readlines()]
            logger.info(f"Loaded {len(self.labels)} bird species labels")
            
            # Load TFLite model
            self.interpreter = tflite.Interpreter(model_path=str(self.model_path))
            self.interpreter.allocate_tensors()
            
            # Get input and output details
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            
            # Get input shape and data type
            self.input_shape = self.input_details[0]['shape']
            self.input_dtype = self.input_details[0]['dtype']
            
            logger.info(f"Model loaded successfully. Input shape: {self.input_shape}, dtype: {self.input_dtype}")
            
            # Enable the service
            self.enabled = True
            self.start_processing_thread()
            
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
            logger.info("Classifier processing thread started")
    
    def stop(self):
        """Stop the classifier service"""
        self.running = False
        if self.processing_thread:
            self.processing_thread.join(timeout=2)
        logger.info("Classifier service stopped")
    
    def _processing_worker(self):
        """Background worker for processing images"""
        while self.running:
            try:
                # Get image from queue with timeout
                item = self.processing_queue.get(timeout=1)
                
                if item is None:  # Shutdown signal
                    break
                
                image_path, request_id = item
                
                # Process the image
                result = self._classify_image_internal(image_path)
                
                # Cache the result with request ID
                self.results_cache[request_id] = result
                
                # Clean old cache entries (keep last 100)
                if len(self.results_cache) > 100:
                    oldest = list(self.results_cache.keys())[0]
                    del self.results_cache[oldest]
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in processing worker: {e}")
    
    def classify_image(self, image_path: str, timeout: float = 2.0) -> Dict:
        """
        Classify a bird image to identify species
        Non-blocking with timeout
        
        Args:
            image_path: Path to the image file
            timeout: Maximum time to wait for results (seconds)
            
        Returns:
            Dict containing classification results
        """
        self.stats['total_images'] += 1
        
        if not self.enabled:
            return {
                'processed': False,
                'predictions': [],
                'processing_time': 0,
                'reason': 'Service disabled'
            }
        
        # Generate unique request ID
        request_id = f"{image_path}_{time.time()}"
        
        # Add to processing queue (non-blocking)
        try:
            self.processing_queue.put_nowait((image_path, request_id))
        except queue.Full:
            logger.warning("Processing queue full - skipping classification")
            return {
                'processed': False,
                'predictions': [],
                'processing_time': 0,
                'reason': 'Queue full'
            }
        
        # Wait for result with timeout
        start_time = time.time()
        while time.time() - start_time < timeout:
            if request_id in self.results_cache:
                result = self.results_cache.pop(request_id)
                return result
            time.sleep(0.01)  # 10ms polling interval
        
        # Timeout - return unprocessed
        logger.warning(f"Classification timeout for {image_path}")
        return {
            'processed': False,
            'predictions': [],
            'processing_time': timeout,
            'reason': 'Timeout'
        }
    
    def _classify_image_internal(self, image_path: str) -> Dict:
        """Internal method to actually classify the image"""
        start_time = time.time()
        
        try:
            # Load and preprocess image
            image = Image.open(image_path).convert('RGB')
            
            # Resize to model input size (224x224 for MobileNet V2)
            input_size = (self.input_shape[1], self.input_shape[2])
            image = image.resize(input_size, Image.Resampling.LANCZOS)
            
            # Convert to numpy array and normalize to [0, 1] range for FLOAT32
            input_data = np.array(image, dtype=np.float32)
            input_data = input_data / 255.0  # Normalize to [0, 1]
            input_data = np.expand_dims(input_data, axis=0)  # Add batch dimension
            
            # Run inference
            self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
            self.interpreter.invoke()
            
            # Get output predictions
            predictions = self.interpreter.get_tensor(self.output_details[0]['index'])[0]
            
            # Apply softmax if we have logits (negative values)
            if predictions.min() < 0:
                # Convert logits to probabilities using softmax
                exp_values = np.exp(predictions - np.max(predictions))  # Subtract max for numerical stability
                predictions = exp_values / exp_values.sum()
            
            # Get top-k predictions
            top_indices = np.argsort(predictions)[-self.top_k:][::-1]
            
            # Build predictions list
            results = []
            for idx in top_indices:
                confidence = float(predictions[idx])
                if confidence >= self.confidence_threshold:
                    species = self.labels[idx] if idx < len(self.labels) else f"Unknown_{idx}"
                    results.append({
                        'species': species,
                        'confidence': confidence,
                        'index': int(idx)
                    })
                    
                    # Update species count
                    if species not in self.stats['species_counts']:
                        self.stats['species_counts'][species] = 0
                    self.stats['species_counts'][species] += 1
            
            # Update statistics
            processing_time = time.time() - start_time
            self.stats['images_processed'] += 1
            self.stats['total_processing_time'] += processing_time
            self.stats['last_classification_time'] = time.time()
            
            # Update average processing time
            self.stats['average_processing_time'] = (
                self.stats['total_processing_time'] / self.stats['images_processed']
            )
            
            logger.debug(f"Classification result: {len(results)} species detected, "
                        f"top: {results[0]['species'] if results else 'None'}, "
                        f"time={processing_time:.3f}s")
            
            return {
                'processed': True,
                'predictions': results,
                'processing_time': processing_time,
                'reason': 'Success'
            }
            
        except Exception as e:
            logger.error(f"Error classifying image {image_path}: {e}")
            self.stats['processing_errors'] += 1
            
            processing_time = time.time() - start_time
            return {
                'processed': False,
                'predictions': [],
                'processing_time': processing_time,
                'reason': f'Error: {str(e)}'
            }
    
    @property
    def is_bird(self) -> bool:
        """
        Always returns True since all 525 classes in this classifier are bird species
        """
        return True
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        uptime = time.time() - self.stats['service_start_time']
        
        # Get top 10 most common species
        top_species = []
        if self.stats['species_counts']:
            sorted_species = sorted(
                self.stats['species_counts'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
            top_species = [
                {'species': species, 'count': count}
                for species, count in sorted_species
            ]
        
        return {
            'enabled': self.enabled,
            'uptime': uptime,
            'total_images': self.stats['total_images'],
            'images_processed': self.stats['images_processed'],
            'processing_errors': self.stats['processing_errors'],
            'average_processing_time': self.stats['average_processing_time'],
            'last_classification_time': self.stats['last_classification_time'],
            'confidence_threshold': self.confidence_threshold,
            'top_k': self.top_k,
            'queue_size': self.processing_queue.qsize(),
            'unique_species_seen': len(self.stats['species_counts']),
            'top_species': top_species
        }
    
    def set_confidence_threshold(self, threshold: float):
        """Update confidence threshold"""
        self.confidence_threshold = max(0.0, min(1.0, threshold))
        logger.info(f"Classifier confidence threshold set to {self.confidence_threshold}")
    
    def set_top_k(self, k: int):
        """Update number of top predictions to return"""
        self.top_k = max(1, min(len(self.labels), k))
        logger.info(f"Classifier top-k set to {self.top_k}")
    
    def get_all_species(self) -> List[str]:
        """Get list of all bird species the model can classify"""
        return self.labels.copy()


# Example usage and testing
if __name__ == "__main__":
    import sys
    
    # Test configuration
    test_config = {
        'classifier': {
            'confidence_threshold': 0.1,
            'top_k': 5
        }
    }
    
    # Initialize classifier
    classifier = BirdClassifier(test_config)
    
    if not classifier.enabled:
        print("Classifier is not enabled. Check that model and labels are present.")
        sys.exit(1)
    
    # Wait a moment for initialization
    time.sleep(0.5)
    
    print(f"Bird Classifier initialized with {len(classifier.labels)} species")
    print(f"Is bird classifier: {classifier.is_bird}")
    print()
    
    # Test with an image if provided
    if len(sys.argv) > 1:
        test_image = sys.argv[1]
        print(f"Classifying image: {test_image}")
        
        result = classifier.classify_image(test_image)
        
        if result['processed']:
            print(f"Processing time: {result['processing_time']:.3f}s")
            print(f"Predictions:")
            for i, pred in enumerate(result['predictions'], 1):
                print(f"  {i}. {pred['species']}: {pred['confidence']:.3f}")
        else:
            print(f"Failed to process: {result['reason']}")
    
    # Show stats
    print("\nClassifier Statistics:")
    stats = classifier.get_stats()
    for key, value in stats.items():
        if key != 'top_species':
            print(f"  {key}: {value}")
    
    # Stop the service
    classifier.stop()