# 🦅 Bird Filter - Experimental Tool

An experimental application that uses the pre-filter model to scan local images and optionally delete non-bird photos.

## Features

- **Smart Bird Detection**: Uses the same TensorFlow Lite model as the main app
- **Batch Processing**: Process entire folders of images
- **Safe Mode**: Scan-only mode to see results without deleting
- **Delete Mode**: Permanently remove non-bird images (with confirmation)
- **Real-time Statistics**: Live progress and detailed results
- **Processing Log**: Detailed log of each image processed

## How to Use

### Option 1: Run with script
```bash
cd experimental/
./run_filter.sh
```

### Option 2: Run directly
```bash
cd experimental/
python3 bird_filter_app.py
```

## Interface Guide

1. **Model Status**: Shows if the pre-filter model loaded successfully
2. **Folder Selection**: Browse and select folder containing images
3. **Options**: 
   - ☐ Scan only (safe mode)
   - ☑️ Delete non-bird images (PERMANENT - use carefully!)
4. **Scan Button**: Start processing images
5. **Statistics**: Real-time stats during processing
6. **Log**: Detailed processing information

## Safety Features

- **Confirmation Dialog**: When delete mode is enabled
- **Stop Button**: Cancel processing at any time
- **Scan-Only Mode**: Preview results without deleting
- **Detailed Logging**: See exactly what happens to each image

## Statistics Provided

- **Total Images**: Number of images found
- **Birds Found**: Images containing birds (kept)
- **Non-Birds Found**: Images without birds
- **Images Deleted**: Count of deleted files (delete mode only)
- **Errors**: Processing failures
- **Processing Time**: Total time taken

## Example Use Cases

### 1. Clean Up Photo Collection
- Point to your photo folder
- Enable delete mode
- Remove all non-bird images automatically

### 2. Analyze Collection
- Scan-only mode to see bird vs non-bird ratio
- No files deleted, just statistics

### 3. Free Up Space
- Process large folders to remove non-bird images
- Reclaim disk space automatically

## Technical Details

- Uses the same COCO SSD MobileNet model as main app
- Supports: JPG, JPEG, PNG, BMP, TIFF formats
- Multi-threading for responsive UI
- 5-second timeout per image processing
- Confidence threshold from main app config

## Caution ⚠️

**DELETE MODE IS PERMANENT!** 
- Files are permanently deleted (not moved to trash)
- Always test with scan-only mode first
- Consider backing up important photos
- The app will ask for confirmation before deleting

## Requirements

- Same as main bird detection app
- Pre-filter model must be loaded successfully
- Sufficient disk space for processing