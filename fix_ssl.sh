#!/bin/bash
# Fix SSL certificate issues on Raspberry Pi

echo "Fixing SSL certificate issues..."

# Update system certificates
echo "Updating system certificates..."
sudo apt-get update
sudo apt-get install -y ca-certificates

# Update certificate store
echo "Updating certificate store..."
sudo update-ca-certificates

# Update pip certificates
echo "Updating Python certificates..."
pip3 install --upgrade certifi --break-system-packages

# Set correct time (SSL needs accurate time)
echo "Syncing system time..."
sudo timedatectl set-ntp true

echo "SSL fixes applied. Please restart the Bird Detection app."