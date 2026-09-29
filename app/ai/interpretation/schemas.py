from typing import Any

from pydantic import BaseModel, Field

from app.schemas.movement import InterpretationOutput


class InterpretationInput(BaseModel):
    athlete: dict[str, Any]
    screening: dict[str, Any]
    metrics: dict[str, Any]
    risk: dict[str, Any]
    evidence: list[dict[str, Any]] = []
