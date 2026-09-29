from __future__ import annotations

from pathlib import Path

import cv2

from app.ai.pose.schemas import PoseSequence

SKELETON_EDGES = (
    ("left_shoulder", "right_shoulder"), ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"), ("left_hip", "right_hip"),
    ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
)


def generate_pose_overlay(video_path: str, sequence: PoseSequence, output_path: Path) -> Path:
    """Create a clinician-review overlay without exposing YOLO internals."""
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError("Unable to open source video for pose overlay")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)); height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS) or sequence.fps or 30.0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    frames = {frame.frame: frame for frame in sequence.frames}
    number = 0
    try:
        while True:
            success, image = capture.read()
            if not success: break
            pose = frames.get(number)
            if pose:
                pixels = {name: (round(point.x * width), round(point.y * height)) for name, point in pose.keypoints.items() if point.confidence >= .35}
                for left, right in SKELETON_EDGES:
                    if left in pixels and right in pixels: cv2.line(image, pixels[left], pixels[right], (0, 220, 0), 2)
                for pixel in pixels.values(): cv2.circle(image, pixel, 4, (30, 80, 255), -1)
                cv2.putText(image, f"Pose frame {number}", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, .7, (255, 255, 255), 2)
            writer.write(image); number += 1
    finally:
        capture.release(); writer.release()
    return output_path


def generate_flagged_frame(video_path: str, sequence: PoseSequence, frame_number: int, output_path: Path) -> Path | None:
    """Extract one evidence image at a metric's deterministic frame reference."""
    capture = cv2.VideoCapture(video_path)
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    success, image = capture.read(); capture.release()
    if not success: return None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path if cv2.imwrite(str(output_path), image) else None
