import os
import time
from dataclasses import dataclass
from typing import Optional

import config

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


@dataclass
class RecordingState:
    active: bool = False
    path: Optional[str] = None
    end_time: Optional[float] = None


class RecordingManager:
    def __init__(self, output_dir=None, duration_s=None, fps=None):
        self.output_dir = output_dir or config.RECORDINGS_DIR
        self.duration_s = duration_s or config.RECORDING_SECONDS
        self.fps = fps or config.RECORDING_FPS
        self._writer = None
        self._state = RecordingState()
        os.makedirs(self.output_dir, exist_ok=True)

    def state(self):
        return self._state

    def start_if_needed(self, frame):
        if self._state.active:
            return
        if cv2 is None or frame is None:
            return

        h, w = frame.shape[:2]
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.output_dir, f"critical_{ts}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(path, fourcc, float(self.fps), (w, h))
        if not self._writer.isOpened():
            self._writer = None
            return

        self._state = RecordingState(active=True, path=path, end_time=time.time() + self.duration_s)

    def write(self, frame):
        if not self._state.active or self._writer is None or frame is None:
            return
        self._writer.write(frame)
        if self._state.end_time and time.time() >= self._state.end_time:
            self.stop()

    def stop(self):
        if self._writer is not None:
            try:
                self._writer.release()
            except Exception:
                pass
        self._writer = None
        self._state = RecordingState()
