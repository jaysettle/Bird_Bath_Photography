#!/bin/bash
# Bird Detection System - Quick Install Script
# For Raspberry Pi OS and Ubuntu systems

set -e  # Exit on any error

echo "🐦 Bird Detection System - Installation Starting..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running on supported OS
print_status "Checking operating system..."
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    print_success "Linux system detected"
else
    print_error "This installer is designed for Linux systems only"
    exit 1
fi

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    print_error "Please don't run this script as root"
    exit 1
fi

# Update system packages
print_status "Updating system packages..."
sudo apt update

# Install system dependencies
print_status "Installing system dependencies..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libfontconfig1 \
    libice6 \
    libxrandr2 \
    libxss1 \
    libxtst6 \
    build-essential \
    cmake \
    pkg-config

# Install Qt6 if available
print_status "Installing Qt6 dependencies..."
if apt list --installed | grep -q python3-pyqt6; then
    print_success "PyQt6 already installed via system packages"
else
    sudo apt install -y python3-pyqt6 python3-pyqt6.qtmultimedia || print_warning "Qt6 system packages not available, will install via pip"
fi

# Create virtual environment (optional)
read -p "Create Python virtual environment? (recommended) [Y/n]: " create_venv
create_venv=${create_venv:-Y}

if [[ $create_venv =~ ^[Yy]$ ]]; then
    print_status "Creating Python virtual environment..."
    if [ ! -d "bird_env" ]; then
        python3 -m venv bird_env
        print_success "Virtual environment created"
    fi
    
    print_status "Activating virtual environment..."
    source bird_env/bin/activate
    
    # Add activation to .bashrc for convenience
    echo "To activate virtual environment later, run: source bird_env/bin/activate"
fi

# Upgrade pip
print_status "Upgrading pip..."
python3 -m pip install --upgrade pip

# Install Python dependencies
print_status "Installing Python packages..."
python3 -m pip install -r requirements.txt

# Check DepthAI installation
print_status "Testing DepthAI installation..."
if python3 -c "import depthai as dai; print('DepthAI version:', dai.__version__)" 2>/dev/null; then
    print_success "DepthAI installed successfully"
else
    print_warning "DepthAI installation may have issues, but continuing..."
fi

# Create config file from example if it doesn't exist
if [ ! -f "config.json" ] && [ -f "config.example.json" ]; then
    print_status "Creating config.json from example..."
    cp config.example.json config.json
    print_success "Configuration file created - please edit config.json with your settings"
fi

# Create directories
print_status "Creating required directories..."
mkdir -p logs
mkdir -p "${HOME}/BirdPhotos"
print_success "Directories created"

# Set permissions
print_status "Setting permissions..."
chmod +x *.sh 2>/dev/null || true
chmod +x *.py 2>/dev/null || true

# Final checks
print_status "Running final system checks..."

# Check Python version
python_version=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
print_status "Python version: $python_version"

# Check camera connection
if lsusb | grep -i movidius >/dev/null; then
    print_success "OAK camera detected"
elif lsusb | grep -i luxonis >/dev/null; then
    print_success "OAK camera detected (Luxonis)"
else
    print_warning "OAK camera not detected - please connect camera and restart"
fi

print_success "Installation completed successfully! 🎉"
echo ""
echo "📋 Next Steps:"
echo "1. Edit config.json with your settings (email, OpenAI API key, etc.)"
echo "2. Connect your OAK-D camera"
echo "3. Run the application: python3 main.py"
echo ""
echo "📖 For detailed configuration help, see INSTALLATION.md"
echo "🌐 Mobile web interface will be available at: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "🚀 To start the application now, run: python3 main.py"