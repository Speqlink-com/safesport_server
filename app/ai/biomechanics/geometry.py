import numpy as np


def joint_angle(a: tuple[float, float], vertex: tuple[float, float], c: tuple[float, float]) -> float | None:
    first = np.array(a) - np.array(vertex); second = np.array(c) - np.array(vertex)
    denominator = np.linalg.norm(first) * np.linalg.norm(second)
    if denominator == 0: return None
    return float(np.degrees(np.arccos(np.clip(np.dot(first, second) / denominator, -1, 1))))


def angle_from_vertical(top: tuple[float, float], bottom: tuple[float, float]) -> float | None:
    vector = np.array(top) - np.array(bottom)
    if np.linalg.norm(vector) == 0: return None
    return float(np.degrees(np.arctan2(abs(vector[0]), abs(vector[1]))))
