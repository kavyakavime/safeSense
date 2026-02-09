"""
Fall detection using motion/proximity sensors + pose analysis
- Falling: person lying down (aspect ratio) or sudden distance change
- Fall risk: rapid distance fluctuations, unstable motion
- Climbing: person moving upward in frame
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class FallDetection:
    fall_detected: bool = False
    fall_confidence: float = 0.0
    fall_risk: bool = False
    fall_risk_confidence: float = 0.0
    climbing: bool = False
    climbing_confidence: float = 0.0
    reason: str = ""


class MotionTracker:
    """Tracks distance and pose history for fall/fall-risk detection"""

    HOLD_SECONDS = 12  # Persist detection state for 12s so dashboard shows it

    def __init__(self, history_size=15):
        self.distance_history: deque = deque(maxlen=history_size)
        self.pose_history: deque = deque(maxlen=history_size)
        self.last_update = 0.0
        self._last_fall: Optional[tuple] = None  # (timestamp, FallDetection)
        self._last_fall_risk: Optional[tuple] = None
        self._last_climbing: Optional[tuple] = None

    def update(self, distance_cm: Optional[float], person_box: Optional[tuple]):
        """person_box: (x1, y1, x2, y2) or None"""
        now = time.time()
        if distance_cm is not None:
            self.distance_history.append((now, distance_cm))
        if person_box is not None:
            x1, y1, x2, y2 = person_box
            w, h = x2 - x1, y2 - y1
            aspect = h / w if w > 0 else 0
            self.pose_history.append((now, aspect, y1, h))
        self.last_update = now

    def get_fall_detection(self) -> FallDetection:
        now = time.time()
        result = FallDetection()

        # Pose-based: person lying down = low aspect ratio (wide, short)
        # Standing: height/width ~ 2-3, lying: ~0.3-0.8
        if len(self.pose_history) >= 3:
            recent = list(self.pose_history)[-5:]
            aspects = [p[1] for p in recent]
            avg_aspect = sum(aspects) / len(aspects)
            if avg_aspect < 0.9 and avg_aspect > 0.2:
                result.fall_detected = True
                result.fall_confidence = min(0.95, 1.0 - avg_aspect + 0.5)
                result.reason = f"Person appears lying down (aspect {avg_aspect:.2f})"

        # Proximity-based: person was close then suddenly far = may have fallen
        if len(self.distance_history) >= 5:
            recent = [(t, d) for t, d in self.distance_history if now - t < 3.0]
            if len(recent) >= 3:
                dists = [d for _, d in recent]
                was_close = any(d < 80 for d in dists[:-2])
                now_far = dists[-1] > 150 if dists else False
                sudden_jump = dists[-1] - dists[-3] > 80 if len(dists) >= 3 else False
                if was_close and (now_far or sudden_jump):
                    result.fall_detected = True
                    result.fall_confidence = max(result.fall_confidence, 0.75)
                    result.reason = "Sudden distance change - possible fall"

        # Fall risk: rapid distance fluctuations = unstable movement (LOWERED thresholds)
        if len(self.distance_history) >= 5:
            dists = [d for _, d in list(self.distance_history)[-8:]]
            if len(dists) >= 3:
                changes = [abs(dists[i] - dists[i - 1]) for i in range(1, len(dists))]
                avg_change = sum(changes) / len(changes) if changes else 0
                max_change = max(changes) if changes else 0
                result.fall_risk_confidence = min(0.85, avg_change / 30)  # Always compute score
                if avg_change > 12 and max_change > 20:
                    result.fall_risk = True
                    result.fall_risk_confidence = max(result.fall_risk_confidence, min(0.85, avg_change / 30))
                    if not result.reason:
                        result.reason = "Unstable motion detected - fall risk"

        # Climbing: person moving upward in frame OR distance decreasing (person approaching)
        if len(self.pose_history) >= 5:
            y_positions = [p[2] for p in list(self.pose_history)[-5:]]
            if y_positions[-1] < y_positions[0] - 30:
                result.climbing = True
                result.climbing_confidence = 0.7
                if not result.reason:
                    result.reason = "Person moving upward - climbing"
        # Distance-based: person approaching (distance decreasing) = possible climbing/movement
        elif len(self.distance_history) >= 5:
            dists = [d for _, d in list(self.distance_history)[-5:]]
            if dists[-1] < dists[0] - 15:  # Person moved 15cm+ closer
                result.climbing = True
                result.climbing_confidence = min(0.6, (dists[0] - dists[-1]) / 80)
                if not result.reason:
                    result.reason = "Person approaching - distance decreasing"

        # Persist: hold state for HOLD_SECONDS so dashboard shows it
        if result.fall_detected:
            self._last_fall = (now, FallDetection(
                fall_detected=True, fall_confidence=result.fall_confidence,
                fall_risk=result.fall_risk, fall_risk_confidence=result.fall_risk_confidence,
                climbing=result.climbing, climbing_confidence=result.climbing_confidence,
                reason=result.reason))
        if result.fall_risk:
            self._last_fall_risk = (now, result)
        if result.climbing:
            self._last_climbing = (now, result)

        # Return persisted state if current is clear but we're within hold window
        if not result.fall_detected and self._last_fall:
            ts, fd = self._last_fall
            if now - ts < self.HOLD_SECONDS:
                result.fall_detected = True
                result.fall_confidence = fd.fall_confidence
                result.reason = fd.reason or result.reason
        if not result.fall_risk and self._last_fall_risk:
            ts, fd = self._last_fall_risk
            if now - ts < self.HOLD_SECONDS:
                result.fall_risk = True
                result.fall_risk_confidence = max(result.fall_risk_confidence, fd.fall_risk_confidence)
        if not result.climbing and self._last_climbing:
            ts, fd = self._last_climbing
            if now - ts < self.HOLD_SECONDS:
                result.climbing = True
                result.climbing_confidence = max(result.climbing_confidence, fd.climbing_confidence)

        return result
