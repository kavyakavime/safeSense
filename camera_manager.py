import threading
import time
from typing import Optional

import config

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


class CameraManager:
    def __init__(self, device_index=None, width=None, height=None, fps=None):
        self.device_index = config.CAMERA_DEVICE_INDEX if device_index is None else device_index
        self.width = config.CAMERA_WIDTH if width is None else width
        self.height = config.CAMERA_HEIGHT if height is None else height
        self.fps = config.CAMERA_FPS if fps is None else fps

        self._lock = threading.Lock()
        self._frame = None
        self._timestamp = None
        self._running = False
        self._thread = None
        self._cap = None

    def start(self):
        if self._running:
            return
        if cv2 is None:
            raise RuntimeError("opencv-python is required for camera capture")
        if self.device_index < 0:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass

    def get_frame(self):
        with self._lock:
            return self._frame, self._timestamp

    def _loop(self):
        print(f"[CAMERA] Opening camera at index {self.device_index}...")
        self._cap = cv2.VideoCapture(self.device_index)
        
        if not self._cap.isOpened():
            print(f"[CAMERA] ✗ Failed to open camera {self.device_index}")
            print("[CAMERA] Try different CAMERA_DEVICE_INDEX in .env (0, 1, 2)")
            return
        
        print(f"[CAMERA] ✓ Camera {self.device_index} opened successfully")
        
        if self.width:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height:
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if self.fps:
            self._cap.set(cv2.CAP_PROP_FPS, self.fps)

        frame_count = 0
        while self._running:
            ok, frame = self._cap.read()
            if not ok:
                if frame_count == 0:
                    print(f"[CAMERA] ✗ Camera opened but can't read frames")
                time.sleep(0.05)
                continue
            
            if frame_count == 0:
                h, w = frame.shape[:2]
                print(f"[CAMERA] ✓ Reading frames: {w}x{h}")
            
            frame_count += 1
            with self._lock:
                self._frame = frame
                self._timestamp = time.time()
