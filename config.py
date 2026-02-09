import os

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None

if load_dotenv:
    load_dotenv()

# Serial settings
SERIAL_PORT = os.getenv("SENSOR_SERIAL_PORT", "/dev/ttyUSB0")
SERIAL_BAUD = int(os.getenv("SENSOR_SERIAL_BAUD", "9600"))
SERIAL_TIMEOUT = float(os.getenv("SENSOR_SERIAL_TIMEOUT", "1"))

# Sensor thresholds
TEMP_ALERT_C = float(os.getenv("TEMP_ALERT_C", "40"))
PERSON_DISTANCE_CM = float(os.getenv("PERSON_DISTANCE_CM", "100"))
PERSON_DISTANCE_CLOSE_CM = float(os.getenv("PERSON_DISTANCE_CLOSE_CM", "50"))

# Flood detection
HUMIDITY_FLOOD_THRESHOLD = float(os.getenv("HUMIDITY_FLOOD_THRESHOLD", "45"))
FLOOD_CONFIDENCE = float(os.getenv("FLOOD_CONFIDENCE", "0.45"))

# Fall detection
FALL_CONFIDENCE_THRESHOLD = float(os.getenv("FALL_CONFIDENCE_THRESHOLD", "0.25"))
FALL_PROXIMITY_CM = float(os.getenv("FALL_PROXIMITY_CM", "50"))
FALL_RISK_DISTANCE_CM = float(os.getenv("FALL_RISK_DISTANCE_CM", "100"))

# Vitals thresholds
HEART_RATE_HIGH = int(os.getenv("HEART_RATE_HIGH", "100"))
STRESS_HIGH = float(os.getenv("STRESS_HIGH", "0.70"))
STRESS_EXTREME = float(os.getenv("STRESS_EXTREME", "0.80"))

# AI thresholds
FIRE_CONFIDENCE = float(os.getenv("FIRE_CONFIDENCE", "0.80"))
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "yolov8n.pt")
YOLO_CONF = float(os.getenv("YOLO_CONF", "0.25"))
YOLO_IMGSZ = int(os.getenv("YOLO_IMGSZ", "640"))
YOLO_DEVICE = os.getenv("YOLO_DEVICE", "")
PERSON_CLASS_NAME = os.getenv("PERSON_CLASS_NAME", "person").strip().lower()
FIRE_CLASS_NAMES = [
    name.strip().lower()
    for name in os.getenv("FIRE_CLASS_NAMES", "fire,smoke").split(",")
    if name.strip()
]

# App settings
ALERTS_DIR = os.getenv("ALERTS_DIR", "alerts")
ALERT_LOG_FILE = os.path.join(ALERTS_DIR, "alerts.log")
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "alerts/recordings")
RECORDING_SECONDS = int(os.getenv("RECORDING_SECONDS", "10"))
RECORDING_FPS = int(os.getenv("RECORDING_FPS", "10"))

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
TWILIO_TO_NUMBER = os.getenv("TWILIO_TO_NUMBER", "")
# Camera settings
CAMERA_DEVICE_INDEX = int(os.getenv("CAMERA_DEVICE_INDEX", "0"))
CAMERA_WIDTH = int(os.getenv("CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.getenv("CAMERA_HEIGHT", "480"))
CAMERA_FPS = int(os.getenv("CAMERA_FPS", "30"))

# Presage bridge settings
PRESAGE_BRIDGE_CMD = os.getenv("PRESAGE_BRIDGE_CMD", "")
PRESAGE_API_KEY = os.getenv("PRESAGE_API_KEY", "")
PRESAGE_LICENSE_PATH = os.getenv("PRESAGE_LICENSE_PATH", "")

# Vitals ingestion
VITALS_TTL_SECONDS = float(os.getenv("VITALS_TTL_SECONDS", "5"))

# Feature flags
SIMULATE_SENSORS = os.getenv("SIMULATE_SENSORS", "0") == "1"
SIMULATE_AI = os.getenv("SIMULATE_AI", "1") == "1"
