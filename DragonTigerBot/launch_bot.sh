#!/bin/bash
# Try offscreen platform first
QT_QPA_PLATFORM=offscreen python main.py

# If offscreen fails, try with virtual display
if [ $? -ne 0 ]; then
    echo "Offscreen failed, trying with Xvfb..."
    pkill Xvfb
    Xvfb :99 -screen 0 1024x768x16 &
    export DISPLAY=:99
    python main.py
fi
