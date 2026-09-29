from app.ai.phases.base import PhaseDetector
from app.ai.phases.common import knee_angle
from app.ai.phases.schemas import PhaseDetectionResult, PhaseReference
from app.ai.pose.schemas import PoseSequence


class SingleLegSquatPhaseDetector(PhaseDetector):
    def detect(self, sequence: PoseSequence) -> PhaseDetectionResult:
        if len(sequence.frames) < 5: raise ValueError("MOVEMENT_PHASE_NOT_DETECTED")
        candidates = [(index, knee_angle(frame)) for index, frame in enumerate(sequence.frames)]
        usable = [(index, angle) for index, angle in candidates if angle is not None]
        if len(usable) < 5: raise ValueError("MOVEMENT_PHASE_NOT_DETECTED")
        bottom_index = min(usable, key=lambda item: item[1])[0]
        if bottom_index in {0, len(sequence.frames) - 1}: raise ValueError("MOVEMENT_PHASE_NOT_DETECTED")
        named = {"START": 0, "DESCENT": max(1, bottom_index // 2), "BOTTOM": bottom_index, "ASCENT": min(len(sequence.frames) - 2, bottom_index + max(1, (len(sequence.frames) - bottom_index) // 2)), "END": len(sequence.frames) - 1}
        return PhaseDetectionResult(drill="SINGLE_LEG_SQUAT", phases={name: PhaseReference(name=name, frame=sequence.frames[index].frame, timestamp_ms=sequence.frames[index].timestamp_ms) for name, index in named.items()}, confidence=.7, limitations=["Pilot two-dimensional phase detection; clinician review is required."])
