import numpy as np
from scipy.signal import savgol_filter

from app.ai.pose.schemas import PoseSequence


def smooth_pose(sequence: PoseSequence) -> PoseSequence:
    if len(sequence.frames) < 5: return sequence
    names = set.intersection(*(set(frame.keypoints) for frame in sequence.frames))
    for name in names:
        for axis in ("x", "y"):
            values = np.array([getattr(frame.keypoints[name], axis) for frame in sequence.frames])
            window = min(7, len(values) if len(values) % 2 else len(values) - 1)
            if window >= 5:
                filtered = savgol_filter(values, window, 2)
                for frame, value in zip(sequence.frames, filtered): setattr(frame.keypoints[name], axis, float(value))
    return sequence
