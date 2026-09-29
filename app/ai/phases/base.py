from abc import ABC, abstractmethod

from app.ai.phases.schemas import PhaseDetectionResult
from app.ai.pose.schemas import PoseSequence


class PhaseDetector(ABC):
    @abstractmethod
    def detect(self, sequence: PoseSequence) -> PhaseDetectionResult: ...
