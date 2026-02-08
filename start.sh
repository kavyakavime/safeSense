#!/bin/bash
# Quick start script for AI CCTV System

echo "========================================="
echo "   AI CCTV Hazard Detection System"
echo "========================================="
echo ""

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
echo "Activating virtual environment..."
source venv/bin/activate

# Install requirements if needed
if [ ! -f "venv/.installed" ]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
    touch venv/.installed
fi

# Create necessary directories
mkdir -p alerts/recordings

# Check Arduino connection
echo ""
echo "Checking Arduino connection..."
if ls /dev/cu.usbserial-* 1> /dev/null 2>&1; then
    PORT=$(ls /dev/cu.usbserial-* | head -n 1)
    echo "✓ Arduino found at: $PORT"
    echo "  Make sure .env has: SENSOR_SERIAL_PORT=$PORT"
else
    echo "⚠ Arduino not found. Check USB connection."
    echo "  Or set SIMULATE_SENSORS=1 in .env for testing"
fi

# Check camera
echo ""
echo "Checking camera..."
python3 -c "import cv2; cap = cv2.VideoCapture(0); print('✓ Camera working') if cap.isOpened() else print('⚠ Camera not found'); cap.release()"

echo ""
echo "Starting Flask server..."
echo "Dashboard will be available at: http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python3 app.py
