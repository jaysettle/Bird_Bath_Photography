#!/bin/bash

# Start the mobile web interface server
cd "$(dirname "$0")"

echo "Starting Bird Detection Mobile Web Interface..."
echo "The interface will be accessible at:"
echo "  http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

./venv/bin/python3 server.py