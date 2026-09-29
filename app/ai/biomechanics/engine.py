from app.ai.biomechanics.geometry import angle_from_vertical, joint_angle
from app.ai.pose.schemas import Keypoint, PoseFrame, PoseSequence
from app.ai.phases.schemas import PhaseDetectionResult


def _point(frame: PoseFrame, name: str) -> tuple[float, float] | None:
    value = frame.keypoints.get(name)
    return (value.x, value.y) if value and value.confidence >= .35 else None


def _metric(value, unit, confidence, side=None, phase=None, frame=None):
    if value is None: return {"value": None, "unit": unit, "confidence": confidence, "side": side, "phase": phase, "evidence": None, "calculation_version": "biomechanics-v1"}
    return {"value": round(float(value), 3), "unit": unit, "confidence": round(float(confidence), 3), "side": side, "phase": phase, "evidence": {"frame": frame.frame, "timestamp_ms": frame.timestamp_ms} if frame else None, "calculation_version": "biomechanics-v1"}


def compute_metrics(drill: str, sequence: PoseSequence, phases: PhaseDetectionResult | None = None) -> dict:
    if not sequence.frames: return {}
    # Maximum knee flexion is a useful deterministic landmark for both MVP drills.
    candidates = []
    for frame in sequence.frames:
        hip, knee, ankle = _point(frame, "right_hip"), _point(frame, "right_knee"), _point(frame, "right_ankle")
        angle = joint_angle(hip, knee, ankle) if hip and knee and ankle else None
        if angle is not None: candidates.append((angle, frame))
    if not candidates: return {}
    knee_angle, frame = min(candidates, key=lambda item: item[0]); phase = "MAX_FLEXION" if drill == "JUMP_LANDING" else "BOTTOM"
    if phases and phases.reference(phase):
        phase_frame = phases.reference(phase).frame
        frame = next((item for item in sequence.frames if item.frame == phase_frame), frame)
        candidate = next((angle for angle, candidate_frame in candidates if candidate_frame.frame == frame.frame), knee_angle)
        knee_angle = candidate
    lh, rh, lk, rk, la, ra = (_point(frame, n) for n in ("left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"))
    ls, rs = _point(frame, "left_shoulder"), _point(frame, "right_shoulder")
    confidence = sum(k.confidence for k in frame.keypoints.values()) / len(frame.keypoints)
    shoulder_mid = ((ls[0]+rs[0])/2, (ls[1]+rs[1])/2) if ls and rs else None; hip_mid = ((lh[0]+rh[0])/2, (lh[1]+rh[1])/2) if lh and rh else None
    trunk = angle_from_vertical(shoulder_mid, hip_mid) if shoulder_mid and hip_mid else None
    if drill == "JUMP_LANDING":
        valgus = joint_angle(rh, rk, ra) if rh and rk and ra else None
        valgus = abs(180 - valgus) if valgus is not None else None
        left_flex = joint_angle(lh, lk, la) if lh and lk and la else None
        symmetry = min(left_flex, knee_angle) / max(left_flex, knee_angle) * 100 if left_flex else None
        return {"knee_valgus_angle": _metric(valgus, "degree", confidence, "RIGHT", phase, frame), "knee_flexion_angle": _metric(knee_angle, "degree", confidence, "RIGHT", phase, frame), "trunk_lean": _metric(trunk, "degree", confidence, None, phase, frame), "limb_symmetry_index": _metric(symmetry, "percent", confidence, None, phase, frame), "stabilization_time": _metric(None, "second", confidence, None, "STABILIZATION")}
    medial = abs(rk[0] - ra[0]) if rk and ra else None
    pelvic = abs(lh[1] - rh[1]) * 100 if lh and rh else None
    depth = abs(rh[1] - rk[1]) if rh and rk else None
    control = max(0, 100 - ((medial or 0) * 500 + (trunk or 0) * 2 + (pelvic or 0) * 2))
    return {"knee_medial_displacement": _metric(medial, "normalized_distance", confidence, "RIGHT", phase, frame), "trunk_lean": _metric(trunk, "degree", confidence, None, phase, frame), "pelvic_drop": _metric(pelvic, "percent_frame_height", confidence, None, phase, frame), "squat_depth": _metric(depth, "normalized_distance", confidence, "RIGHT", phase, frame), "movement_control_score": _metric(control, "score", confidence, "RIGHT", phase, frame)}
