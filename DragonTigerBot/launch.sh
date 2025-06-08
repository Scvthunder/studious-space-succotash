#!/bin/bash
cd "$(dirname "$0")"
QT_QPA_PLATFORM=offscreen python main.py 2>&1 | grep -v "propagateSizeHints"