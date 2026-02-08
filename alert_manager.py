import json
import os
import time
from dataclasses import asdict

import config
try:
    from twilio.rest import Client  # type: ignore
except Exception:  # pragma: no cover
    Client = None


class AlertManager:
    def __init__(self, alerts_dir=None, log_file=None):
        self.alerts_dir = alerts_dir or config.ALERTS_DIR
        self.log_file = log_file or config.ALERT_LOG_FILE
        os.makedirs(self.alerts_dir, exist_ok=True)

    def log_alert(self, assessment, ai, vitals, sensor_data):
        payload = {
            "timestamp": time.time(),
            "level": assessment.level,
            "confidence": assessment.confidence,
            "reason": assessment.reason,
            "ai": asdict(ai),
            "vitals": asdict(vitals),
            "sensor": sensor_data.as_dict(),
        }
        line = json.dumps(payload)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return payload

    def read_recent_alerts(self, limit=10):
        if not os.path.exists(self.log_file):
            return []
        alerts = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    alerts.append(json.loads(line))
                except Exception:
                    continue
        return alerts[-limit:]

    def send_sms(self, assessment, ai, vitals, sensor_data):
        if not (config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN):
            return
        if not (config.TWILIO_FROM_NUMBER and config.TWILIO_TO_NUMBER):
            return
        if Client is None:
            raise RuntimeError("twilio is required for SMS alerts. Install with: pip install twilio")

        client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)

        temp = sensor_data.temperature_c
        dist = sensor_data.distance_cm
        hr = vitals.heart_rate
        stress = vitals.stress

        lines = [
            f"🚨 {assessment.level} EMERGENCY!",
            assessment.reason,
            "",
            f"AI: fire={ai.fire} ({ai.fire_confidence:.2f}) person={ai.person}",
            f"Temp: {temp if temp is not None else 'NA'} C",
            f"Distance: {dist if dist is not None else 'NA'} cm",
            f"HR: {hr if hr is not None else 'NA'} bpm",
            f"Stress: {int(stress * 100) if stress is not None else 'NA'}%",
            time.strftime("%Y-%m-%d %H:%M:%S"),
        ]
        body = "\n".join(lines)

        client.messages.create(
            body=body,
            from_=config.TWILIO_FROM_NUMBER,
            to=config.TWILIO_TO_NUMBER,
        )
