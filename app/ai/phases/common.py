from app.ai.pose.schemas import PoseFrame


def midpoint(frame: PoseFrame, first: str, second: str) -> tuple[float, float] | None:
    a, b = frame.keypoints.get(first), frame.keypoints.get(second)
    if not a or not b or min(a.confidence, b.confidence) < .35: return None
    return ((a.x + b.x) / 2, (a.y + b.y) / 2)


def knee_angle(frame: PoseFrame, side: str = "right") -> float | None:
    from app.ai.biomechanics.geometry import joint_angle
    names = [f"{side}_hip", f"{side}_knee", f"{side}_ankle"]
    points = [frame.keypoints.get(name) for name in names]
    if any(point is None or point.confidence < .35 for point in points): return None
    return joint_angle(*[(point.x, point.y) for point in points])
