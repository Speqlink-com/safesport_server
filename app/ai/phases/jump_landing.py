from app.ai.phases.base import PhaseDetector
from app.ai.phases.common import knee_angle, midpoint
from app.ai.phases.schemas import PhaseDetectionResult, PhaseReference
from app.ai.pose.schemas import PoseSequence


class JumpLandingPhaseDetector(PhaseDetector):
    """2D pilot detector. Uses hip vertical trajectory and deepest knee flexion."""

    def detect(self, sequence: PoseSequence) -> PhaseDetectionResult:
        if len(sequence.frames) < 5: raise ValueError("MOVEMENT_PHASE_NOT_DETECTED")
        hips = [(index, midpoint(frame, "left_hip", "right_hip")) for index, frame in enumerate(sequence.frames)]
        visible = [(index, point[1]) for index, point in hips if point]
        if len(visible) < 5: raise ValueError("MOVEMENT_PHASE_NOT_DETECTED")
        # Normalized y grows down the image: lowest hip point approximates loading/deepest landing.
        load_index = max(visible, key=lambda item: item[1])[0]
        angles = [(index, knee_angle(frame)) for index, frame in enumerate(sequence.frames)]
        flexion_index = min(((index, angle) for index, angle in angles if angle is not None), key=lambda item: item[1])[0]
        contact_index = min(load_index, flexion_index)
        start = sequence.frames[0]; end = sequence.frames[-1]
        takeoff_index = max(0, contact_index // 3)
        flight_index = max(takeoff_index, contact_index - 1)
        stabilization_index = min(len(sequence.frames) - 1, max(contact_index + 1, flexion_index + 1))
        named = {"START": 0, "TAKE_OFF": takeoff_index, "FLIGHT": flight_index, "INITIAL_CONTACT": contact_index, "LOAD_ACCEPTANCE": contact_index, "MAX_FLEXION": flexion_index, "STABILIZATION": stabilization_index, "END": len(sequence.frames) - 1}
        return PhaseDetectionResult(drill="JUMP_LANDING", phases={name: PhaseReference(name=name, frame=sequence.frames[index].frame, timestamp_ms=sequence.frames[index].timestamp_ms) for name, index in named.items()}, confidence=.55, limitations=["Pilot two-dimensional phase detection; clinician review is required."])
