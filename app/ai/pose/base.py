from abc import ABC, abstractmethod

from app.ai.pose.schemas import PoseSequence


class PoseEstimator(ABC):
    @abstractmethod
    def estimate_video(self, video_path: str) -> PoseSequence: ...


class FakePoseEstimator(PoseEstimator):
    """Deterministic fixture estimator used only in tests and local pipeline checks."""

    def estimate_video(self, video_path: str) -> PoseSequence:
        from app.ai.pose.schemas import Keypoint, PoseFrame

        def frame(number: int, knee_y: float) -> PoseFrame:
            hip_y = .45 + (knee_y - .62) * .18
            points = {
                "left_shoulder": (0.35, 0.20), "right_shoulder": (0.63, 0.20),
                "left_hip": (0.40, hip_y), "right_hip": (0.60, hip_y),
                "left_knee": (0.43, knee_y), "right_knee": (0.69, knee_y),
                "left_ankle": (0.45, 0.88), "right_ankle": (0.64, 0.88),
            }
            return PoseFrame(frame=number, timestamp_ms=number * 33, keypoints={name: Keypoint(x=x, y=y, confidence=.95) for name, (x, y) in points.items()})

        return PoseSequence(
            fps=30.0, width=1920, height=1080,
            frames=[frame(0, .62), frame(1, .70), frame(2, .77), frame(3, .70), frame(4, .62)],
            model_metadata={"provider": "fake", "model_family": "FIXTURE", "model_name": "fake-pose", "model_version": "1", "inference_config_version": "fixture-v1", "device": "cpu"},
        )
