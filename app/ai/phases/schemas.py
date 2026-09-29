from pydantic import BaseModel


class PhaseReference(BaseModel):
    name: str
    frame: int
    timestamp_ms: int


class PhaseDetectionResult(BaseModel):
    drill: str
    phases: dict[str, PhaseReference]
    confidence: float
    limitations: list[str] = []

    def reference(self, phase: str) -> PhaseReference | None:
        return self.phases.get(phase)
