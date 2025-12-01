#!/bin/bash
# Suppress harmless error messages when running the Bird Detection app

# Suppress DBUS/XDG errors
export NO_AT_BRIDGE=1

# Suppress GTK accessibility warnings
export GTK_A11Y=none

# Run the app with error suppression
cd "$(dirname "$0")"
python3 main.py 2>&1 | grep -v -E "(DEPRECATED_ENDPOINT|close object|dbus/xdg/request)" | grep -v "^$"