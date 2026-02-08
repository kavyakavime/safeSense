"""
AI CCTV Hazard Detection System - Computer Vision Module
With HC-SR04 Ultrasonic Motion Sensor + DHT22 Temperature/Humidity
"""

import cv2
import numpy as np
from ultralytics import YOLO
import torch
import serial
import json
import time
from datetime import datetime
from collections import deque
import threading
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

# ==================== CONFIGURATION ====================

class Config:
    # Camera settings
    CAMERA_INDEX = 0
    FRAME_WIDTH = 1280
    FRAME_HEIGHT = 720
    FPS = 30
    
    # Arduino settings - CHANGE THIS TO YOUR PORT!
    ARDUINO_PORT = '/dev/cu.usbserial-10'
    # Linux: /dev/ttyUSB0 or /dev/ttyACM0
    # Windows: COM3, COM4, etc.
    # Mac: /dev/cu.usbserial-XXXX
    ARDUINO_BAUD = 115200
    
    # AI Model settings
    YOLO_MODEL = 'yolov8n.pt'
    CONFIDENCE_THRESHOLD = 0.5
    IOU_THRESHOLD = 0.45
    
    # Detection settings
    FIRE_COLOR_LOWER = np.array([0, 100, 100])
    FIRE_COLOR_UPPER = np.array([30, 255, 255])
    SMOKE_THRESHOLD = 0.15
    
    # Alert settings
    ALERT_COOLDOWN = 30
    MOTION_HISTORY = 50
    
    # Notification settings
    ENABLE_EMAIL_ALERTS = False
    EMAIL_FROM = "your-email@gmail.com"
    EMAIL_PASSWORD = "your-app-password"
    EMAIL_TO = ["security@company.com"]
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    
    # Recording settings
    SAVE_RECORDINGS = True
    RECORDING_PATH = Path("recordings")
    SAVE_ON_ALERT = True
    ALERT_BUFFER_SECONDS = 10
    
    # Display settings
    SHOW_VIDEO = True
    SHOW_FPS = True
    SHOW_SENSOR_DATA = True

# ==================== LOGGING SETUP ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ai_cctv.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== HAZARD DETECTOR CLASS ====================

class HazardDetector:
    def __init__(self, config):
        self.config = config
        self.running = False
        
        logger.info("Loading YOLO model...")
        self.model = YOLO(config.YOLO_MODEL)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f"Using device: {self.device}")
        
        logger.info("Initializing camera...")
        self.camera = cv2.VideoCapture(config.CAMERA_INDEX)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
        self.camera.set(cv2.CAP_PROP_FPS, config.FPS)
        
        if not self.camera.isOpened():
            raise RuntimeError("Failed to open camera")
        
        self.arduino = None
        self.arduino_data = {}
        self.init_arduino()
        
        self.motion_history = deque(maxlen=config.MOTION_HISTORY)
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=16, detectShadows=True
        )
        
        self.alert_history = {}
        self.current_alerts = set()
        
        self.frame_buffer = deque(maxlen=config.FPS * config.ALERT_BUFFER_SECONDS)
        self.video_writer = None
        self.recording_active = False
        
        self.stats = {
            'total_frames': 0,
            'total_alerts': 0,
            'fps': 0,
            'start_time': time.time()
        }
        
        self.hazard_classes = {
            'person': 0,
            'fire': None,
            'smoke': None,
            'knife': 43,
            'bottle': 39,
            'backpack': 24,
            'suitcase': 28,
        }
        
        if config.SAVE_RECORDINGS:
            config.RECORDING_PATH.mkdir(exist_ok=True)
        
        logger.info("Hazard Detector initialized successfully")
    
    def init_arduino(self):
        try:
            self.arduino = serial.Serial(
                self.config.ARDUINO_PORT,
                self.config.ARDUINO_BAUD,
                timeout=1
            )
            time.sleep(2)
            logger.info(f"Arduino connected on {self.config.ARDUINO_PORT}")
            
            self.arduino_thread = threading.Thread(target=self.read_arduino, daemon=True)
            self.arduino_thread.start()
        except Exception as e:
            logger.error(f"Failed to connect to Arduino: {e}")
            logger.warning("Continuing without Arduino integration")
            self.arduino = None
    
    def read_arduino(self):
        while self.running:
            try:
                if self.arduino and self.arduino.in_waiting:
                    line = self.arduino.readline().decode('utf-8').strip()
                    if line:
                        try:
                            data = json.loads(line)
                            if data.get('type') == 'SENSOR_DATA':
                                self.arduino_data = data
                                
                                # Fire hazard from temperature
                                if data.get('temp', 0) > 45:
                                    self.trigger_alert('FIRE', 'Temperature spike detected')
                                
                                # Log ultrasonic motion
                                if data.get('motion') and data.get('motion_count', 0) > 5:
                                    logger.info(f"High motion activity detected by ultrasonic sensor: {data.get('motion_count')} events")
                            
                            elif data.get('event'):
                                event = data.get('event')
                                logger.info(f"Arduino event: {data}")
                                
                                # Handle motion events from ultrasonic sensor
                                if event == 'MOTION_DETECTED':
                                    distance = data.get('distance', 0)
                                    change = data.get('change', 0)
                                    logger.debug(f"Motion: distance={distance}cm, change={change}cm")
                                
                                # Handle fire hazard from temperature
                                elif event == 'FIRE_HAZARD':
                                    self.trigger_alert('FIRE', f"Temperature: {data.get('temp')}°C")
                        
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                logger.error(f"Arduino read error: {e}")
            time.sleep(0.1)
    
    def send_arduino_command(self, command):
        if self.arduino:
            try:
                self.arduino.write(f"{command}\n".encode('utf-8'))
                logger.debug(f"Sent to Arduino: {command}")
            except Exception as e:
                logger.error(f"Failed to send command to Arduino: {e}")
    
    def detect_fire(self, frame):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.config.FIRE_COLOR_LOWER, self.config.FIRE_COLOR_UPPER)
        
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        fire_percentage = np.sum(mask > 0) / (mask.shape[0] * mask.shape[1])
        
        if fire_percentage > 0.01:
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            return True, contours
        
        return False, []
    
    def detect_smoke(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (21, 21), 0)
        
        mean = cv2.blur(blur, (21, 21))
        sqr_mean = cv2.blur(blur**2, (21, 21))
        variance = sqr_mean - mean**2
        
        variance_norm = variance / 255.0
        
        smoke_mask = (variance_norm < self.config.SMOKE_THRESHOLD).astype(np.uint8) * 255
        smoke_percentage = np.sum(smoke_mask > 0) / (smoke_mask.shape[0] * smoke_mask.shape[1])
        
        if smoke_percentage > 0.05:
            return True, smoke_mask
        
        return False, None
    
    def detect_violence(self, detections, motion_intensity):
        person_count = sum(1 for det in detections if det['class'] == 'person')
        
        # Also check ultrasonic motion sensor
        arduino_motion = self.arduino_data.get('motion', False)
        motion_count = self.arduino_data.get('motion_count', 0)
        
        # Combine camera motion + ultrasonic motion
        if person_count >= 2 and (motion_intensity > 30 or motion_count > 3):
            return True, "Multiple persons with high activity"
        
        return False, None
    
    def detect_intrusion(self, detections):
        person_count = sum(1 for det in detections if det['class'] == 'person')
        
        # Also check ultrasonic sensor for motion
        arduino_motion = self.arduino_data.get('motion', False)
        
        hour = datetime.now().hour
        if (person_count > 0 or arduino_motion) and (hour >= 22 or hour <= 6):
            return True, f"{person_count} person(s) detected after hours"
        
        return False, None
    
    def detect_abandoned_object(self, detections):
        suspicious_objects = ['backpack', 'suitcase', 'handbag']
        
        for det in detections:
            if det['class'] in suspicious_objects:
                return True, f"Abandoned {det['class']} detected"
        
        return False, None
    
    def calculate_motion_intensity(self, fg_mask):
        motion_pixels = np.sum(fg_mask == 255)
        total_pixels = fg_mask.shape[0] * fg_mask.shape[1]
        intensity = (motion_pixels / total_pixels) * 100
        return intensity
    
    def trigger_alert(self, alert_type, message):
        current_time = time.time()
        
        if alert_type in self.alert_history:
            if current_time - self.alert_history[alert_type] < self.config.ALERT_COOLDOWN:
                return
        
        self.alert_history[alert_type] = current_time
        self.current_alerts.add(alert_type)
        self.stats['total_alerts'] += 1
        
        logger.warning(f"ALERT: {alert_type} - {message}")
        
        self.send_arduino_command(alert_type)
        
        if self.config.SAVE_ON_ALERT and not self.recording_active:
            self.start_recording(alert_type)
        
        if self.config.ENABLE_EMAIL_ALERTS:
            threading.Thread(
                target=self.send_email_alert,
                args=(alert_type, message),
                daemon=True
            ).start()
    
    def start_recording(self, alert_type):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.config.RECORDING_PATH / f"alert_{alert_type}_{timestamp}.mp4"
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.video_writer = cv2.VideoWriter(
            str(filename),
            fourcc,
            self.config.FPS,
            (self.config.FRAME_WIDTH, self.config.FRAME_HEIGHT)
        )
        
        for frame in self.frame_buffer:
            self.video_writer.write(frame)
        
        self.recording_active = True
        logger.info(f"Started recording: {filename}")
    
    def stop_recording(self):
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            self.recording_active = False
            logger.info("Recording stopped")
    
    def send_email_alert(self, alert_type, message):
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config.EMAIL_FROM
            msg['To'] = ', '.join(self.config.EMAIL_TO)
            msg['Subject'] = f"AI CCTV ALERT: {alert_type}"
            
            body = f"""
            AI CCTV Hazard Detection System Alert
            
            Alert Type: {alert_type}
            Message: {message}
            Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            
            Sensor Data:
            - Temperature: {self.arduino_data.get('temp', 'N/A')}°C
            - Humidity: {self.arduino_data.get('humidity', 'N/A')}%
            - Ultrasonic Distance: {self.arduino_data.get('distance', 'N/A')}cm
            - Motion Detected: {'Yes' if self.arduino_data.get('motion') else 'No'}
            - Motion Count: {self.arduino_data.get('motion_count', 0)}
            
            Please check the surveillance system immediately.
            
            ---
            AI CCTV System
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(self.config.SMTP_SERVER, self.config.SMTP_PORT)
            server.starttls()
            server.login(self.config.EMAIL_FROM, self.config.EMAIL_PASSWORD)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email alert sent for {alert_type}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
    
    def process_frame(self, frame):
        display_frame = frame.copy()
        detections = []
        alerts = []
        
        results = self.model(frame, conf=self.config.CONFIDENCE_THRESHOLD, 
                            iou=self.config.IOU_THRESHOLD, verbose=False)
        
        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                cls = int(box.cls[0])
                class_name = self.model.names[cls]
                
                detections.append({
                    'class': class_name,
                    'confidence': conf,
                    'bbox': (x1, y1, x2, y2)
                })
                
                color = (0, 255, 0)
                if class_name in ['knife', 'scissors']:
                    color = (0, 0, 255)
                
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
                label = f"{class_name}: {conf:.2f}"
                cv2.putText(display_frame, label, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        fg_mask = self.bg_subtractor.apply(frame)
        motion_intensity = self.calculate_motion_intensity(fg_mask)
        
        fire_detected, fire_contours = self.detect_fire(frame)
        if fire_detected:
            self.trigger_alert('FIRE', 'Fire detected in camera view')
            alerts.append('FIRE')
            for contour in fire_contours:
                cv2.drawContours(display_frame, [contour], -1, (0, 0, 255), 3)
        
        smoke_detected, _ = self.detect_smoke(frame)
        if smoke_detected:
            self.trigger_alert('FIRE', 'Smoke detected in camera view')
            alerts.append('SMOKE')
        
        violence, violence_msg = self.detect_violence(detections, motion_intensity)
        if violence:
            self.trigger_alert('VIOLENCE', violence_msg)
            alerts.append('VIOLENCE')
        
        intrusion, intrusion_msg = self.detect_intrusion(detections)
        if intrusion:
            self.trigger_alert('INTRUSION', intrusion_msg)
            alerts.append('INTRUSION')
        
        weapon_detected = any(det['class'] in ['knife', 'scissors'] for det in detections)
        if weapon_detected:
            self.trigger_alert('WEAPON', 'Weapon detected')
            alerts.append('WEAPON')
        
        self.draw_overlay(display_frame, detections, motion_intensity, alerts)
        
        return display_frame, detections, alerts
    
    def draw_overlay(self, frame, detections, motion_intensity, alerts):
        h, w = frame.shape[:2]
        
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 140), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        
        cv2.putText(frame, "AI CCTV HAZARD DETECTION", (10, 25),
                   cv2.FONT_HERSHEY_BOLD, 0.7, (0, 255, 255), 2)
        
        if self.config.SHOW_FPS:
            cv2.putText(frame, f"FPS: {self.stats['fps']:.1f}", (10, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        person_count = sum(1 for d in detections if d['class'] == 'person')
        cv2.putText(frame, f"Persons: {person_count}", (10, 75),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        color = (0, 255, 0) if motion_intensity < 20 else (0, 165, 255) if motion_intensity < 50 else (0, 0, 255)
        cv2.putText(frame, f"Motion: {motion_intensity:.1f}%", (10, 100),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        if self.config.SHOW_SENSOR_DATA and self.arduino_data:
            temp = self.arduino_data.get('temp', 0)
            humidity = self.arduino_data.get('humidity', 0)
            distance = self.arduino_data.get('distance', 0)
            arduino_motion = self.arduino_data.get('motion', False)
            motion_count = self.arduino_data.get('motion_count', 0)
            
            cv2.putText(frame, f"Temp: {temp:.1f}C", (w - 250, 40),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            cv2.putText(frame, f"Humidity: {humidity:.1f}%", (w - 250, 65),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            cv2.putText(frame, f"Distance: {distance:.0f}cm", (w - 250, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            
            motion_color = (0, 255, 0) if arduino_motion else (100, 100, 100)
            cv2.putText(frame, f"Ultrasonic: {'MOTION' if arduino_motion else 'Clear'} [{motion_count}]", 
                       (w - 250, 115),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, motion_color, 2)
        
        if alerts:
            alert_overlay = frame.copy()
            cv2.rectangle(alert_overlay, (0, h - 60), (w, h), (0, 0, 255), -1)
            cv2.addWeighted(alert_overlay, 0.7, frame, 0.3, 0, frame)
            
            alert_text = " | ".join(alerts)
            cv2.putText(frame, f"ALERT: {alert_text}", (10, h - 20),
                       cv2.FONT_HERSHEY_BOLD, 1.0, (255, 255, 255), 3)
        
        if self.recording_active:
            cv2.circle(frame, (w - 30, 30), 10, (0, 0, 255), -1)
            cv2.putText(frame, "REC", (w - 80, 35),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    
    def run(self):
        self.running = True
        logger.info("Starting hazard detection...")
        
        frame_count = 0
        fps_start_time = time.time()
        
        try:
            while self.running:
                ret, frame = self.camera.read()
                if not ret:
                    logger.error("Failed to read frame from camera")
                    break
                
                self.frame_buffer.append(frame.copy())
                
                display_frame, detections, alerts = self.process_frame(frame)
                
                if self.recording_active and self.video_writer:
                    self.video_writer.write(display_frame)
                
                frame_count += 1
                self.stats['total_frames'] += 1
                if frame_count >= 30:
                    elapsed = time.time() - fps_start_time
                    self.stats['fps'] = frame_count / elapsed
                    frame_count = 0
                    fps_start_time = time.time()
                
                if self.config.SHOW_VIDEO:
                    cv2.imshow('AI CCTV - Hazard Detection', display_frame)
                    
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        break
                    elif key == ord('r'):
                        if self.recording_active:
                            self.stop_recording()
                        else:
                            self.start_recording('MANUAL')
                    elif key == ord('c'):
                        self.send_arduino_command('ALERT_OFF')
                        self.current_alerts.clear()
                
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.cleanup()
    
    def cleanup(self):
        logger.info("Cleaning up...")
        self.running = False
        
        if self.recording_active:
            self.stop_recording()
        
        if self.camera:
            self.camera.release()
        
        if self.arduino:
            self.send_arduino_command('ALERT_OFF')
            self.arduino.close()
        
        cv2.destroyAllWindows()
        
        runtime = time.time() - self.stats['start_time']
        logger.info(f"Total runtime: {runtime:.1f} seconds")
        logger.info(f"Total frames: {self.stats['total_frames']}")
        logger.info(f"Total alerts: {self.stats['total_alerts']}")
        logger.info(f"Average FPS: {self.stats['total_frames'] / runtime:.1f}")

# ==================== MAIN ====================

def main():
    print("=" * 60)
    print("AI CCTV HAZARD DETECTION SYSTEM")
    print("=" * 60)
    print("Sensors: HC-SR04 Ultrasonic + DHT22 + Camera AI")
    print()
    print("Controls:")
    print("  Q - Quit")
    print("  R - Toggle recording")
    print("  C - Clear alerts")
    print()
    
    config = Config()
    detector = HazardDetector(config)
    
    try:
        detector.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        detector.cleanup()

if __name__ == "__main__":
    main()
