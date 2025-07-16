#!/bin/bash
# Setup script for Bird Detection System

echo "Installing system packages..."
sudo apt update
sudo apt install -y \
    python3-pyqt6 \
    python3-opencv \
    python3-numpy \
    python3-watchdog \
    python3-systemd \
    python3-psutil \
    python3-requests \
    python3-termcolor

echo "Installing Python packages via pip..."
pip install --user --break-system-packages \
    google-api-python-client \
    google-auth-httplib2 \
    google-auth-oauthlib \
    depthai

echo "Creating directories..."
mkdir -p logs

echo "Setting permissions..."
chmod +x main.py
chmod +x src/*.py

echo "Setup complete!"
echo "To run: python3 main.py"