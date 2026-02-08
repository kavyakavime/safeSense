from dataclasses import dataclass, field
from typing import List, Optional

import config


@dataclass
class AIDetections:
    fire: bool = False
    fire_confidence: float = 0.0
    person: bool = False
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


def assess_emergency_level(ai: AIDetections, vitals: Vitals, sensor_data) -> EmergencyAssessment:
    temp = sensor_data.temperature_c
    dist = sensor_data.distance_cm

    ai_fire = ai.fire and ai.fire_confidence >= config.FIRE_CONFIDENCE
    ai_person = ai.person

    temp_alert = temp is not None and temp > config.TEMP_ALERT_C
    person_close = dist is not None and dist < config.PERSON_DISTANCE_CM
    person_very_close = dist is not None and dist < config.PERSON_DISTANCE_CLOSE_CM

    hr_high = vitals.heart_rate is not None and vitals.heart_rate > config.HEART_RATE_HIGH
    stress_high = vitals.stress is not None and vitals.stress > config.STRESS_HIGH
    stress_extreme = vitals.stress is not None and vitals.stress > config.STRESS_EXTREME

    if ai_fire and temp_alert and (ai_person or person_close) and (hr_high or stress_high):
        return EmergencyAssessment(
            level="CRITICAL",
            confidence=95,
            reason="Fire confirmed by vision + temp; person in danger zone with elevated vitals",
        )

    if temp_alert and (not ai_fire) and (ai_person or person_close):
        return EmergencyAssessment(
            level="HIGH",
            confidence=80,
            reason="Temperature spike with nearby person",
        )

    if ai_fire and temp_alert and not (ai_person or person_close):
        return EmergencyAssessment(
            level="HIGH",
            confidence=85,
            reason="Fire confirmed by vision + temp; no person nearby",
        )

    if (stress_extreme and person_very_close) or (ai_fire and not temp_alert):
        return EmergencyAssessment(
            level="MEDIUM",
            confidence=65,
            reason="Possible false positive or stress event; monitor closely",
        )

    if ai_person or person_close:
        return EmergencyAssessment(
            level="LOW",
            confidence=50,
            reason="Person detected with normal vitals",
        )

    return EmergencyAssessment(level="LOW", confidence=10, reason="Normal operation")


class Detector:
    def __init__(self, simulate=None, model_path=None, device=None, conf=None, imgsz=None):
        self.simulate = config.SIMULATE_AI if simulate is None else simulate
        self.model = None
        self.model_names = None
        self.model_path = model_path or config.YOLO_MODEL_PATH
        self.device = device if device is not None else (config.YOLO_DEVICE or None)
        self.conf = conf if conf is not None else config.YOLO_CONF
        self.imgsz = imgsz if imgsz is not None else config.YOLO_IMGSZ
        self.person_class_name = config.PERSON_CLASS_NAME
        self.fire_class_names = set(config.FIRE_CLASS_NAMES)

        if not self.simulate:
            try:
                from ultralytics import YOLO  # type: ignore
            except Exception as exc:
                raise RuntimeError(
                    "ultralytics is required for YOLOv8 detection. "
                    "Install it with: pip install ultralytics"
                ) from exc

            self.model = YOLO(self.model_path)
            self.model_names = getattr(self.model, "names", None)

    def detect(self, frame=None) -> AIDetections:
        if self.simulate:
            return AIDetections(fire=False, fire_confidence=0.0, person=False, boxes=[])

        if frame is None or self.model is None:
            return AIDetections(fire=False, fire_confidence=0.0, person=False, boxes=[])

        results = self.model.predict(
            source=frame,
            conf=self.conf,
            imgsz=self.imgsz,
            device=self.device,
            verbose=False,
        )

        fire_conf = 0.0
        person = False
        boxes_out: List[DetectionBox] = []

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

                boxes_out.append(
                    DetectionBox(
                        label=label,
                        confidence=float(conf),
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                    )
                )

        return AIDetections(
            fire=fire_conf >= config.FIRE_CONFIDENCE,
            fire_confidence=round(fire_conf, 3),
            person=person,
            boxes=boxes_out,
        )

    def read_vitals(self, frame=None) -> Vitals:
        if self.simulate:
            return Vitals(heart_rate=78, stress=0.25, face_detected=True)

        # TODO: Integrate Presage SDK for contactless vitals
        return Vitals()
