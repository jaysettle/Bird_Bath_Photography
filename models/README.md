# Bird Detection Models

This directory contains AI models for local bird pre-filtering.

## Required Model

Place `bird_detector.tflite` in this directory to enable local pre-filtering.

## Model Requirements

The pre-filter service expects:
- **File name**: `bird_detector.tflite`
- **Format**: TensorFlow Lite (.tflite)
- **Input**: RGB image tensor
- **Output**: Single float confidence score (0.0 to 1.0)
- **Purpose**: Binary classification (bird/no-bird)

## Creating a Custom Model

You can create a custom bird detection model using:

1. **MobileNet v2** - Lightweight and fast
2. **TensorFlow Lite Converter** - Convert to .tflite format
3. **Training data** - Bird vs non-bird images

Example model architectures:
- MobileNet v2 (224x224 input)
- EfficientNet B0/B1 (lightweight versions)

## Benefits

- Reduces OpenAI API calls by 50-80%
- Saves money on AI identification costs
- Faster initial filtering
- Works offline

## Model Not Found

If no model is present, the pre-filter will be disabled and all images will be sent directly to OpenAI for identification.