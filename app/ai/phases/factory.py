from app.ai.phases.base import PhaseDetector
from app.ai.phases.jump_landing import JumpLandingPhaseDetector
from app.ai.phases.single_leg_squat import SingleLegSquatPhaseDetector


def get_phase_detector(drill: str) -> PhaseDetector:
    if drill == "JUMP_LANDING": return JumpLandingPhaseDetector()
    if drill == "SINGLE_LEG_SQUAT": return SingleLegSquatPhaseDetector()
    raise ValueError(f"MOVEMENT_PHASE_NOT_DETECTED: unsupported drill {drill}")
