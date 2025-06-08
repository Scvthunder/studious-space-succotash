#!/bin/bash

# Find an available display number
find_free_display() {
    i=0
    while [ -f /tmp/.X$i-lock ]; do
        i=$((i+1))
    done
    echo $i
}

# Stop any existing Xvfb processes
pkill Xvfb || true

# Fix X11 permissions
sudo mkdir -p /tmp/.X11-unix
sudo chmod 1777 /tmp/.X11-unix

# Get available display
DISPLAY_NUM=$(find_free_display)

# Start virtual display
Xvfb :$DISPLAY_NUM -screen 0 1024x768x16 >/dev/null 2>&1 &

# Set display
export DISPLAY=:$DISPLAY_NUM

# Run the application
python main.py
