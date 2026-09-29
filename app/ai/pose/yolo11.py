from pathlib import Path

import cv2

from app.ai.pose.base import PoseEstimator
from app.ai.pose.schemas import Keypoint, PoseFrame, PoseSequence
from app.core.config import get_settings

COCO_NAMES = ["nose", "left_eye", "right_eye", "left_ear", "right_ear", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist", "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"]


class YOLO11PoseEstimator(PoseEstimator):
    def __init__(self):
        from ultralytics import YOLO
        settings = get_settings()
        self.settings = settings
        self.model = YOLO(settings.pose_model)

    def estimate_video(self, video_path: str) -> PoseSequence:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0; width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)); cap.release()
        frames = []
        results = self.model.predict(source=video_path, stream=True, conf=self.settings.pose_confidence_threshold, device=self.settings.pose_device, verbose=False)
        for index, result in enumerate(results):
            people = result.keypoints
            if people is None or len(people) == 0: continue
            # Dominant person is the detection with highest mean keypoint confidence.
            conf = people.conf.cpu().numpy(); person_index = int(conf.mean(axis=1).argmax())
            xy = people.xyn.cpu().numpy()[person_index]
            keypoints = {name: Keypoint(x=float(xy[i][0]), y=float(xy[i][1]), confidence=float(conf[person_index][i])) for i, name in enumerate(COCO_NAMES)}
            frames.append(PoseFrame(frame=index, timestamp_ms=round(index / fps * 1000), keypoints=keypoints))
        return PoseSequence(fps=fps, width=width, height=height, frames=frames, model_metadata={"provider": "ultralytics", "model_family": "YOLO11", "model_name": Path(self.settings.pose_model).stem, "model_version": "11", "inference_config_version": "pose-config-v1", "device": self.settings.pose_device})


def get_pose_estimator() -> PoseEstimator:
    from app.ai.pose.base import FakePoseEstimator
    settings = get_settings(); return FakePoseEstimator() if settings.pose_provider == "fake" else YOLO11PoseEstimator()
