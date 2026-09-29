from abc import ABC, abstractmethod

from app.ai.interpretation.schemas import InterpretationInput
from app.schemas.movement import InterpretationOutput


class MovementInterpreter(ABC):
    @abstractmethod
    async def interpret(self, context: InterpretationInput) -> InterpretationOutput: ...
