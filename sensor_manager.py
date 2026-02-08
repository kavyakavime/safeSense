import threading
import time
from dataclasses import dataclass, asdict
from typing import Optional

import config

try:
    import serial
except Exception:  # pragma: no cover - optional dependency
    serial = None


@dataclass
class SensorData:
    temperature_c: Optional[float] = None
    humidity: Optional[float] = None
    distance_cm: Optional[float] = None
    updated_at: Optional[float] = None

    def as_dict(self):
        return asdict(self)


class SensorManager:
    def __init__(self, port=None, baud=None, timeout=None, simulate=None):
        self.port = port or config.SERIAL_PORT
        self.baud = baud or config.SERIAL_BAUD
        self.timeout = timeout or config.SERIAL_TIMEOUT
        self.simulate = config.SIMULATE_SENSORS if simulate is None else simulate

        self._lock = threading.Lock()
        self._data = SensorData()
        self._running = False
        self._thread = None
        self._ser = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass

    def get_data(self) -> SensorData:
        with self._lock:
            return SensorData(**self._data.as_dict())

    def is_person_detected(self) -> bool:
        data = self.get_data()
        return data.distance_cm is not None and data.distance_cm < config.PERSON_DISTANCE_CM

    def is_temperature_alert(self) -> bool:
        data = self.get_data()
        return data.temperature_c is not None and data.temperature_c > config.TEMP_ALERT_C

    def _loop(self):
        if self.simulate:
            self._simulate_loop()
            return

        if serial is None:
            raise RuntimeError("pyserial is required for hardware sensor mode")

        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
            time.sleep(2)  # Wait for Arduino to reset after serial connection
            self._ser.reset_input_buffer()  # Flush any garbage data
            self._ser.reset_output_buffer()
            print(f"[SENSOR] Connected to {self.port} at {self.baud} baud")
        except Exception as exc:
            raise RuntimeError(f"Failed to open serial port {self.port}: {exc}")

        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while self._running:
            if consecutive_errors >= max_consecutive_errors:
                print(f"[SENSOR] Too many consecutive errors, resetting buffers...")
                try:
                    self._ser.reset_input_buffer()
                    consecutive_errors = 0
                    time.sleep(1)
                except Exception:
                    pass
            try:
                line = self._ser.readline().decode("utf-8", errors="ignore").strip()
            except Exception:
                consecutive_errors += 1
                time.sleep(0.1)
                continue

            if not line:
                time.sleep(0.05)
                continue

            # Skip lines that are obviously corrupted (missing opening brace or too short)
            if line.startswith("{") and len(line) < 20:
                consecutive_errors += 1
                continue
                
            parsed = self._parse_line(line)
            if parsed is None:
                consecutive_errors += 1
                continue

            # Successfully parsed - reset error counter
            consecutive_errors = 0
            with self._lock:
                self._data = parsed

    def _simulate_loop(self):
        temp = 24.0
        hum = 45.0
        dist = 150.0
        direction = 1
        while self._running:
            temp += 0.1 * direction
            hum += 0.2 * direction
            dist += 2.0 * direction
            if temp > 30 or temp < 22:
                direction *= -1

            with self._lock:
                self._data = SensorData(
                    temperature_c=round(temp, 1),
                    humidity=round(hum, 1),
                    distance_cm=round(dist, 1),
                    updated_at=time.time(),
                )
            time.sleep(0.5)

    def send_command(self, command: str):
        """Send command to Arduino (FIRE, INTRUSION, VIOLENCE, ALERT_OFF, etc.)"""
        if not self._ser or self.simulate:
            return
        try:
            self._ser.write(f"{command}\n".encode('utf-8'))
        except Exception as e:
            print(f"Failed to send command to Arduino: {e}")

    @staticmethod
    def _parse_line(line: str) -> Optional["SensorData"]:
        # Try JSON format first: {"type":"SENSOR_DATA","temp":21.60,"humidity":10.00,"distance":20.7,...}
        if line.startswith("{"):
            try:
                import json
                data = json.loads(line)
                if data.get("type") == "SENSOR_DATA":
                    temp = data.get("temp")
                    hum = data.get("humidity")
                    dist = data.get("distance")
                    return SensorData(
                        temperature_c=temp,
                        humidity=hum,
                        distance_cm=dist,
                        updated_at=time.time(),
                    )
            except Exception:
                pass
        
        # Fallback to old format: TEMP:24.5,HUMID:42,DIST:145
        parts = line.split(",")
        if not parts:
            return None
        temp = hum = dist = None
        for part in parts:
            if ":" not in part:
                continue
            key, value = part.split(":", 1)
            key = key.strip().upper()
            value = value.strip()
            try:
                if key == "TEMP":
                    temp = float(value)
                elif key == "HUMID":
                    hum = float(value)
                elif key == "DIST":
                    dist = float(value)
            except ValueError:
                continue

        if temp is None and hum is None and dist is None:
            return None

        return SensorData(
            temperature_c=temp,
            humidity=hum,
            distance_cm=dist,
            updated_at=time.time(),
        )
