from dataclasses import dataclass, field
from typing import List, Optional

import config


@dataclass
class AIDetections:
    fire: bool = False
    fire_confidence: float = 0.0
    flood: bool = False
    flood_confidence: float = 0.0
    person: bool = False
    fall_detected: bool = False
    fall_confidence: float = 0.0
    fall_risk: bool = False
    fall_risk_confidence: float = 0.0
    climbing: bool = False
    climbing_confidence: float = 0.0
    person_box: Optional[tuple] = None  # (x1,y1,x2,y2) for fall/pose analysis
    boxes: List["DetectionBox"] = field(default_factory=list)


@dataclass
class DetectionBox:
    label: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass
class Vitals:
    heart_rate: Optional[int] = None
    stress: Optional[float] = None
    face_detected: bool = False


@dataclass
class EmergencyAssessment:
    level: str
    confidence: int
    reason: str


def assess_emergency_level(ai: AIDetections, vitals: Vitals, sensor_data, fall_detection=None) -> EmergencyAssessment:
    temp = sensor_data.temperature_c
    humidity = getattr(sensor_data, "humidity", None)
    dist = getattr(sensor_data, "distance_cm", None)

    # CRITICAL: Fall detected when person is close (50cm or less) AND fall confidence 25%+
    if fall_detection and fall_detection.fall_detected and fall_detection.fall_confidence >= config.FALL_CONFIDENCE_THRESHOLD:
        if dist is not None and dist <= config.FALL_PROXIMITY_CM:
            return EmergencyAssessment(
                level="CRITICAL",
                confidence=95,
                reason=f"🚨 FALL DETECTED! ({int(fall_detection.fall_confidence*100)}%) at {int(dist)}cm - {fall_detection.reason}",
            )

    # HIGH: Fall risk (unstable motion, person close)
    if fall_detection and fall_detection.fall_risk and dist is not None and dist < config.FALL_RISK_DISTANCE_CM:
        return EmergencyAssessment(
            level="HIGH",
            confidence=85,
            reason=f"⚠️ FALL RISK! Unstable motion at {int(dist)}cm - {fall_detection.reason}",
        )

    # MEDIUM: Climbing detected
    if fall_detection and fall_detection.climbing:
        return EmergencyAssessment(
            level="MEDIUM",
            confidence=70,
            reason=f"📈 Climbing detected - {fall_detection.reason}",
        )

    # CRITICAL: Fire > 50% + Temp > threshold
    if ai.fire_confidence >= config.FIRE_CONFIDENCE and temp is not None and temp > config.TEMP_ALERT_C:
        return EmergencyAssessment(
            level="CRITICAL",
            confidence=95,
            reason=f"🔥 FIRE DETECTED! AI: {int(ai.fire_confidence*100)}% | Temp: {temp}°C",
        )

    # CRITICAL: Flood > 45% + Humidity > 45%
    if ai.flood_confidence >= config.FLOOD_CONFIDENCE and humidity is not None and humidity > config.HUMIDITY_FLOOD_THRESHOLD:
        return EmergencyAssessment(
            level="CRITICAL",
            confidence=95,
            reason=f"🌊 FLOOD DETECTED! AI: {int(ai.flood_confidence*100)}% | Humidity: {int(humidity)}%",
        )

    # LOW: Person detected
    person_close = getattr(sensor_data, "distance_cm", None) is not None and sensor_data.distance_cm < config.PERSON_DISTANCE_CM
    if ai.person or person_close:
        return EmergencyAssessment(level="LOW", confidence=50, reason="Person detected - Normal conditions")

    return EmergencyAssessment(level="LOW", confidence=10, reason="Normal operation")


class Detector:
    def __init__(self, simulate=None, model_path=None, device=None, conf=None, imgsz=None):
        import os
        self.simulate = config.SIMULATE_AI if simulate is None else simulate
        self.fire_model = None
        self.flood_model = None
        self.model_names = None
        self.fire_model_path = model_path or config.YOLO_MODEL_PATH
        self.flood_model_path = "flood_vision.pt"
        self.device = device if device is not None else (config.YOLO_DEVICE or None)
        self.conf = conf if conf is not None else config.YOLO_CONF
        self.imgsz = imgsz if imgsz is not None else config.YOLO_IMGSZ
        self.person_class_name = config.PERSON_CLASS_NAME
        self.fire_class_names = set(config.FIRE_CLASS_NAMES)

        if not self.simulate:
            try:
                from ultralytics import YOLO  # type: ignore
            except Exception as exc:
                raise RuntimeError("ultralytics required. pip install ultralytics") from exc

            # Load fire model (required)
            self.fire_model = YOLO(self.fire_model_path)
            self.model_names = getattr(self.fire_model, "names", None)
            print(f"[AI] Fire model loaded: {self.fire_model_path}")

            # Load flood model (optional)
            if os.path.exists(self.flood_model_path):
                self.flood_model = YOLO(self.flood_model_path)
                print(f"[AI] Flood model loaded: {self.flood_model_path}")

    def detect(self, frame=None) -> AIDetections:
        if self.simulate:
            return AIDetections(fire=False, fire_confidence=0.0, flood=False, flood_confidence=0.0, person=False, boxes=[])

        if frame is None or self.fire_model is None:
            return AIDetections(fire=False, fire_confidence=0.0, flood=False, flood_confidence=0.0, person=False, boxes=[])

        fire_conf = 0.0
        flood_conf = 0.0
        person = False
        boxes_out: List[DetectionBox] = []

        # Run fire model
        results = self.fire_model.predict(source=frame, conf=self.conf, imgsz=self.imgsz, device=self.device, verbose=False)
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None or boxes.cls is None or boxes.conf is None or boxes.xyxy is None:
                continue
            names = getattr(result, "names", None) or self.model_names
            for cls_id, conf, xyxy in zip(boxes.cls, boxes.conf, boxes.xyxy):
                try:
                    idx = int(cls_id)
                except Exception:
                    continue
                if isinstance(names, dict):
                    name = names.get(idx)
                elif isinstance(names, (list, tuple)) and idx < len(names):
                    name = names[idx]
                else:
                    name = None
                if not name:
                    continue
                label = str(name).strip().lower()
                if label == self.person_class_name:
                    person = True
                if label in self.fire_class_names:
                    fire_conf = max(fire_conf, float(conf))
                try:
                    x1, y1, x2, y2 = [int(v) for v in xyxy.tolist()]
                except Exception:
                    continue
                boxes_out.append(DetectionBox(label=label, confidence=float(conf), x1=x1, y1=y1, x2=x2, y2=y2))

        # Fallback: color-based water detection (blue/cyan hues = water when significant)
        import cv2
        import numpy as np
        if frame is not None:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            lower_water = np.array([85, 80, 80])
            upper_water = np.array([135, 255, 255])
            mask = cv2.inRange(hsv, lower_water, upper_water)
            water_ratio = np.sum(mask > 0) / (mask.shape[0] * mask.shape[1])
            if water_ratio > 0.12:  # 12%+ of frame is water-colored
                flood_conf = max(flood_conf, min(0.45, water_ratio * 2))

        # Run flood model (handles both detection and segmentation models)
        if self.flood_model is not None:
            flood_results = self.flood_model.predict(source=frame, conf=0.25, imgsz=self.imgsz, device=self.device, verbose=False)
            for result in flood_results:
                # Try boxes first (object detection)
                boxes = getattr(result, "boxes", None)
                if boxes is not None and boxes.cls is not None and boxes.conf is not None and boxes.xyxy is not None:
                    names = getattr(result, "names", None)
                    for cls_id, conf, xyxy in zip(boxes.cls, boxes.conf, boxes.xyxy):
                        try:
                            idx = int(cls_id)
                        except Exception:
                            continue
                        if isinstance(names, dict):
                            name = names.get(idx, "water")
                        elif isinstance(names, (list, tuple)) and idx < len(names):
                            name = names[idx]
                        else:
                            name = "water"  # Segmentation model: any detection = water
                        label = str(name).strip().lower()
                        flood_conf = max(flood_conf, float(conf))
                        try:
                            x1, y1, x2, y2 = [int(v) for v in xyxy.tolist()]
                        except Exception:
                            continue
                        boxes_out.append(DetectionBox(label=f"flood-{label}", confidence=float(conf), x1=x1, y1=y1, x2=x2, y2=y2))
                # Segmentation model: check masks (flood model uses seg, not detection)
                masks = getattr(result, "masks", None)
                if masks is not None and hasattr(masks, "data") and masks.data is not None:
                    conf_val = 0.7  # Segmentation detected water
                    flood_conf = max(flood_conf, conf_val)
                    # Get bounding box from boxes (seg models still have box coords)
                    seg_boxes = getattr(result, "boxes", None)
                    if seg_boxes is not None and hasattr(seg_boxes, "xyxy") and seg_boxes.xyxy is not None and len(seg_boxes.xyxy) > 0:
                        try:
                            xyxy = seg_boxes.xyxy[0]
                            x1, y1, x2, y2 = [int(v) for v in xyxy.tolist()]
                            boxes_out.append(DetectionBox(label="flood-water", confidence=conf_val, x1=x1, y1=y1, x2=x2, y2=y2))
                        except Exception:
                            pass

        # Get largest person box for fall/pose analysis
        person_box = None
        person_boxes = [b for b in boxes_out if b.label == self.person_class_name]
        if person_boxes:
            largest = max(person_boxes, key=lambda b: (b.x2 - b.x1) * (b.y2 - b.y1))
            person_box = (largest.x1, largest.y1, largest.x2, largest.y2)

        return AIDetections(
            fire=fire_conf >= config.FIRE_CONFIDENCE,
            fire_confidence=round(fire_conf, 3),
            flood=flood_conf >= config.FLOOD_CONFIDENCE,
            flood_confidence=round(flood_conf, 3),
            person=person,
            fall_detected=False,
            fall_confidence=0.0,
            fall_risk=False,
            fall_risk_confidence=0.0,
            climbing=False,
            climbing_confidence=0.0,
            person_box=person_box,
            boxes=boxes_out,
        )

    def read_vitals(self, frame=None) -> Vitals:
        if self.simulate:
            return Vitals(heart_rate=78, stress=0.25, face_detected=True)

        # TODO: Integrate Presage SDK for contactless vitals
        return Vitals()
