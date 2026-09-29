from pydantic import BaseModel, Field


class Keypoint(BaseModel):
    x: float; y: float
    confidence: float = Field(ge=0, le=1)


class PoseFrame(BaseModel):
    frame: int
    timestamp_ms: int
    keypoints: dict[str, Keypoint]


class PoseSequence(BaseModel):
    fps: float
    width: int
    height: int
    frames: list[PoseFrame]
    model_metadata: dict
