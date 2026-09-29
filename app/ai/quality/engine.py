from app.ai.quality.schemas import QualityResult
from app.core.config import get_settings
from app.core.enums import QualityStatus
from typing import Any
from app.ai.pose.schemas import PoseSequence


def validate_video_metadata(video: Any) -> QualityResult:
    settings = get_settings()
    checks = {
        "resolution": bool(video.width and video.height and video.width >= settings.movement_min_width and video.height >= settings.movement_min_height),
        "fps": bool(video.fps and video.fps >= settings.movement_min_fps),
        "duration": bool(video.duration_seconds and settings.movement_min_duration_seconds <= video.duration_seconds <= settings.movement_max_duration_seconds),
        "supported_format": (video.format or "").lower() in {"mp4", "mov", "webm"},
    }
    reasons = [f"{name.upper()}_INVALID" for name, passed in checks.items() if not passed]
    score = sum(checks.values()) / len(checks)
    state = QualityStatus.ACCEPTABLE if all(checks.values()) else QualityStatus.RETAKE_REQUIRED
    return QualityResult(status=state, score=score, reasons=reasons, checks=checks)


def validate_pose_quality(sequence: PoseSequence) -> QualityResult:
    settings = get_settings()
    required_joints = {"left_shoulder", "right_shoulder", "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"}
    if not sequence.frames:
        return QualityResult(status=QualityStatus.RETAKE_REQUIRED, score=0.0, reasons=["POSE_CONFIDENCE_TOO_LOW"], checks={"full_body": False, "required_joints": False, "pose_confidence": False, "movement_detected": False})
    observed = [frame for frame in sequence.frames if required_joints.issubset(frame.keypoints)]
    joint_confidences = [point.confidence for frame in observed for name, point in frame.keypoints.items() if name in required_joints]
    hip_positions = [((frame.keypoints["left_hip"].x + frame.keypoints["right_hip"].x) / 2, (frame.keypoints["left_hip"].y + frame.keypoints["right_hip"].y) / 2) for frame in observed]
    movement = max((abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(hip_positions, hip_positions[1:])), default=0.0)
    checks = {"full_body": len(observed) / len(sequence.frames) >= .70, "required_joints": len(observed) / len(sequence.frames) >= .70, "pose_confidence": bool(joint_confidences and sum(joint_confidences) / len(joint_confidences) >= settings.pose_confidence_threshold), "movement_detected": movement >= .004}
    reasons = [f"{name.upper()}_INSUFFICIENT" for name, passed in checks.items() if not passed]
    score = sum(checks.values()) / len(checks)
    return QualityResult(status=QualityStatus.ACCEPTABLE if all(checks.values()) else QualityStatus.RETAKE_REQUIRED, score=score, reasons=reasons, checks=checks)


def merge_quality_results(metadata: QualityResult, pose: QualityResult) -> QualityResult:
    checks = metadata.checks | pose.checks
    reasons = metadata.reasons + pose.reasons
    score = sum(checks.values()) / len(checks)
    return QualityResult(status=QualityStatus.ACCEPTABLE if not reasons else QualityStatus.RETAKE_REQUIRED, score=score, reasons=reasons, checks=checks)
