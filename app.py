import threading
import time
from dataclasses import asdict

from flask import Flask, Response, jsonify, render_template, request

import config
from alert_manager import AlertManager
from camera_manager import CameraManager
from detector import Detector, Vitals, assess_emergency_level
from presage_manager import PresageManager
from recorder import RecordingManager
from sensor_manager import SensorManager

app = Flask(__name__)

state_lock = threading.Lock()
latest_state = {
    "ai": None,
    "vitals": None,
    "sensor": None,
    "assessment": None,
    "recording": None,
    "updated_at": None,
}

camera_ref = {"camera": None}
vitals_lock = threading.Lock()
latest_vitals = {
    "heart_rate": None,
    "stress": None,
    "face_detected": False,
    "updated_at": None,
}

demo_lock = threading.Lock()
demo_override = {
    "enabled": False,
    "expires_at": None,
    "level": "CRITICAL",
    "reason": "Demo trigger activated",
}


def update_state(ai, vitals, sensor, assessment, recording_state=None):
    with state_lock:
        latest_state["ai"] = asdict(ai)
        latest_state["vitals"] = asdict(vitals)
        latest_state["sensor"] = sensor.as_dict()
        latest_state["assessment"] = asdict(assessment)
        latest_state["recording"] = recording_state
        latest_state["updated_at"] = time.time()


def get_state():
    with state_lock:
        return dict(latest_state)


def _draw_boxes(frame, boxes):
    import cv2

    for box in boxes or []:
        label = box.get("label", "")
        conf = box.get("confidence", 0.0)
        x1 = int(box.get("x1", 0))
        y1 = int(box.get("y1", 0))
        x2 = int(box.get("x2", 0))
        y2 = int(box.get("y2", 0))

        if label in {"fire", "smoke"}:
            color = (0, 0, 255)
        elif label == "person":
            color = (0, 255, 0)
        else:
            color = (0, 200, 255)

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        text = f"{label} {conf:.2f}"
        cv2.putText(frame, text, (x1, max(y1 - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


def background_loop():
    print("[SYSTEM] Starting background detection loop...")
    
    sensor_mgr = SensorManager()
    print(f"[ARDUINO] Connecting to {config.SERIAL_PORT} at {config.SERIAL_BAUD} baud...")
    
    detector = Detector()
    print(f"[AI] YOLO model: {config.YOLO_MODEL_PATH}, simulate={config.SIMULATE_AI}")
    
    camera = CameraManager()
    presage = PresageManager() if config.PRESAGE_BRIDGE_CMD else None
    alerts = AlertManager()
    recorder = RecordingManager()

    camera.start()
    camera_ref["camera"] = camera
    sensor_mgr.start()
    print("[ARDUINO] Sensor manager started")
    if presage:
        presage.start()
    last_alert_time = 0
    last_level = None

    while True:
        sensor = sensor_mgr.get_data()
        frame, _ = camera.get_frame()
        ai = detector.detect(frame=frame)

        with vitals_lock:
            vitals_snapshot = dict(latest_vitals)
        vitals_age = None
        if vitals_snapshot["updated_at"] is not None:
            vitals_age = time.time() - vitals_snapshot["updated_at"]

        if vitals_age is not None and vitals_age <= config.VITALS_TTL_SECONDS:
            vitals = Vitals(
                heart_rate=vitals_snapshot["heart_rate"],
                stress=vitals_snapshot["stress"],
                face_detected=vitals_snapshot["face_detected"],
            )
        elif presage:
            vitals = presage.get_vitals()
        else:
            vitals = detector.read_vitals()
        assessment = assess_emergency_level(ai, vitals, sensor)

        with demo_lock:
            if demo_override["enabled"] and demo_override["expires_at"]:
                if time.time() < demo_override["expires_at"]:
                    assessment.level = demo_override["level"]
                    assessment.confidence = 99
                    assessment.reason = demo_override["reason"]
                else:
                    demo_override["enabled"] = False

        if assessment.level == "CRITICAL":
            recorder.start_if_needed(frame)
        recorder.write(frame)

        recording_state = recorder.state()
        update_state(
            ai,
            vitals,
            sensor,
            assessment,
            recording_state={
                "active": recording_state.active,
                "path": recording_state.path,
                "end_time": recording_state.end_time,
            },
        )

        now = time.time()
        should_alert = assessment.level in {"CRITICAL", "HIGH"}
        cooldown_ok = (now - last_alert_time) > 30
        if should_alert and (cooldown_ok or assessment.level != last_level):
            alerts.log_alert(assessment, ai, vitals, sensor)
            alerts.send_sms(assessment, ai, vitals, sensor)
            
            # Send alert to Arduino for LED/LCD display
            arduino_command = "FIRE" if ai.fire else "HAZARD"
            if assessment.level == "CRITICAL":
                arduino_command = "FIRE" if ai.fire else "VIOLENCE"
            sensor_mgr.send_command(arduino_command)
            
            last_alert_time = now
            last_level = assessment.level
        elif not should_alert and last_level in {"CRITICAL", "HIGH"}:
            # Clear Arduino alert when returning to normal
            sensor_mgr.send_command("ALERT_OFF")
            last_level = assessment.level

        time.sleep(0.2)  # Update every 200ms for real-time feel


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    if not camera_ref["camera"]:
        return Response(status=503)

    def gen():
        import cv2
        import numpy as np

        no_camera_sent = False
        while True:
            frame, _ = camera_ref["camera"].get_frame()
            
            if frame is None:
                # Send "No Camera" placeholder image
                if not no_camera_sent:
                    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(placeholder, "Camera Not Available", (120, 220),
                               cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
                    cv2.putText(placeholder, "Check CAMERA_DEVICE_INDEX in .env", (80, 260),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
                    cv2.putText(placeholder, "Try: 0, 1, or 2", (220, 300),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
                    ok, buffer = cv2.imencode(".jpg", placeholder)
                    if ok:
                        jpg = buffer.tobytes()
                        yield (b"--frame\r\n"
                               b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
                        no_camera_sent = True
                time.sleep(1)
                continue
            
            no_camera_sent = False
            state = get_state()
            ai = state.get("ai") or {}
            boxes = ai.get("boxes") or []
            _draw_boxes(frame, boxes)
            ok, buffer = cv2.imencode(".jpg", frame)
            if not ok:
                continue
            jpg = buffer.tobytes()
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")

    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/status")
def api_status():
    return jsonify(get_state())


@app.route("/api/alerts")
def api_alerts():
    limit = request.args.get("limit", "10")
    try:
        limit = int(limit)
    except Exception:
        limit = 10
    alerts = AlertManager().read_recent_alerts(limit=limit)
    return jsonify({"alerts": alerts})


@app.route("/api/demo/trigger", methods=["POST"])
def api_demo_trigger():
    payload = request.get_json(silent=True) or {}
    level = (payload.get("level") or "CRITICAL").upper()
    seconds = payload.get("seconds") or 10
    reason = payload.get("reason") or "Demo trigger activated"

    try:
        seconds = int(seconds)
    except Exception:
        seconds = 10

    with demo_lock:
        demo_override["enabled"] = True
        demo_override["expires_at"] = time.time() + max(1, seconds)
        demo_override["level"] = level
        demo_override["reason"] = reason

    return jsonify({"ok": True, "level": level, "seconds": seconds})


@app.route("/api/vitals", methods=["POST"])
def api_vitals():
    payload = request.get_json(silent=True) or {}
    heart_rate = payload.get("heart_rate")
    stress = payload.get("stress")
    face_detected = payload.get("face_detected", False)

    try:
        heart_rate = int(heart_rate) if heart_rate is not None else None
    except Exception:
        heart_rate = None
    try:
        stress = float(stress) if stress is not None else None
    except Exception:
        stress = None

    with vitals_lock:
        latest_vitals["heart_rate"] = heart_rate
        latest_vitals["stress"] = stress
        latest_vitals["face_detected"] = bool(face_detected)
        latest_vitals["updated_at"] = time.time()

    return jsonify({"ok": True})


if __name__ == "__main__":
    t = threading.Thread(target=background_loop, daemon=True)
    t.start()
    port = int(__import__("os").getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
