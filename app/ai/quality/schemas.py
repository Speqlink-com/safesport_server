from pydantic import BaseModel, Field

from app.core.enums import QualityStatus


class QualityResult(BaseModel):
    status: QualityStatus
    score: float = Field(ge=0, le=1)
    reasons: list[str]
    checks: dict[str, bool]
