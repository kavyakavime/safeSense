import json
import os
import subprocess
import threading
import time
from typing import Optional

import config
from detector import Vitals


class PresageManager:
    def __init__(self, cmd: Optional[str] = None, simulate: Optional[bool] = None):
        self.cmd = cmd if cmd is not None else config.PRESAGE_BRIDGE_CMD
        self.simulate = config.SIMULATE_AI if simulate is None else simulate

        self._lock = threading.Lock()
        self._vitals = Vitals()
        self._running = False
        self._thread = None
        self._proc = None

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
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def get_vitals(self) -> Vitals:
        with self._lock:
            return Vitals(
                heart_rate=self._vitals.heart_rate,
                stress=self._vitals.stress,
                face_detected=self._vitals.face_detected,
            )

    def _loop(self):
        if self.simulate or not self.cmd:
            self._simulate_loop()
            return

        env = os.environ.copy()
        if config.PRESAGE_API_KEY:
            env["PRESAGE_API_KEY"] = config.PRESAGE_API_KEY
            env["SMARTSPECTRA_API_KEY"] = config.PRESAGE_API_KEY
        if config.PRESAGE_LICENSE_PATH:
            env["PRESAGE_LICENSE_PATH"] = config.PRESAGE_LICENSE_PATH

        self._proc = subprocess.Popen(
            self.cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )

        while self._running and self._proc.poll() is None:
            line = self._proc.stdout.readline() if self._proc.stdout else ""
            if not line:
                time.sleep(0.1)
                continue
            data = self._parse_line(line)
            if data is None:
                continue
            with self._lock:
                self._vitals = data

    def _simulate_loop(self):
        hr = 78
        stress = 0.25
        direction = 1
        while self._running:
            hr += direction
            stress += 0.01 * direction
            if hr > 95 or hr < 72:
                direction *= -1
            if stress > 0.6 or stress < 0.2:
                direction *= -1
            with self._lock:
                self._vitals = Vitals(heart_rate=hr, stress=round(stress, 2), face_detected=True)
            time.sleep(1)

    @staticmethod
    def _parse_line(line: str) -> Optional[Vitals]:
        # Expected JSON lines like: {"heart_rate":78,"stress":0.25,"face_detected":true}
        line = line.strip()
        if not line:
            return None
        try:
            payload = json.loads(line)
        except Exception:
            return None

        hr = payload.get("heart_rate")
        stress = payload.get("stress")
        face = payload.get("face_detected", False)

        try:
            hr = int(hr) if hr is not None else None
        except Exception:
            hr = None
        try:
            stress = float(stress) if stress is not None else None
        except Exception:
            stress = None

        return Vitals(heart_rate=hr, stress=stress, face_detected=bool(face))
