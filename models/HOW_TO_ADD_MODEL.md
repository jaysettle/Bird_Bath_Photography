# How to Add a Bird Detection Model

## Quick Start
1. Find a TensorFlow Lite model for bird/animal detection
2. Rename it to `bird_detector.tflite`
3. Place it in this directory
4. Restart the bird detection app

## Model Requirements
- **Format**: TensorFlow Lite (.tflite)
- **Input**: RGB image tensor (typically 224x224x3 or 320x320x3)
- **Output**: Classification score (0.0 to 1.0)
  - 0.0 = No bird detected
  - 1.0 = Bird detected with high confidence

## Recommended Models
1. **MobileNet v2** - Fast and efficient
2. **EfficientNet B0** - Good accuracy/speed balance
3. **Custom trained model** - Best performance for your specific use case

## Testing
After adding the model:
1. Go to Configuration tab → Local Pre-filter section
2. Check if "Model Status" shows "🟢 Model loaded"
3. Adjust confidence threshold as needed (default: 0.70)
4. Monitor statistics in Services tab

## Expected Benefits
- 50-80% reduction in OpenAI API calls
- Significant cost savings
- Faster initial filtering
- Works offline
