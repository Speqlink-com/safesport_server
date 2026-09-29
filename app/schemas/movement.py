from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Drill = Literal["JUMP_LANDING", "SINGLE_LEG_SQUAT", "SPRINT_ACCELERATION", "CUTTING", "KICKING"]
CameraView = Literal["FRONTAL", "SAGITTAL", "REAR", "MULTI_VIEW"]


class MovementSessionCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    scheduled_at: str = Field(default="", max_length=60)
    location: str = Field(default="", max_length=200)
    drill: Drill = "JUMP_LANDING"
    camera_view: CameraView = "FRONTAL"
    instructions_html: str = ""


class MovementSessionResponse(BaseModel):
    id: str
    institution_id: str | None = None
    institution_name: str = ""
    title: str
    scheduled_at: str
    location: str
    drill: str
    camera_view: str
    instructions_html: str
    status: str
    created_at: datetime


class MovementScreeningCreate(BaseModel):
    athlete_safesport_id: str = Field(min_length=5, max_length=20)
    session_id: str | None = None
    drill: Drill = "JUMP_LANDING"
    camera_view: CameraView = "FRONTAL"


class MovementVideoUploadResponse(BaseModel):
    video_url: str
    video_public_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class MovementReviewPayload(BaseModel):
    decision: Literal["ACCEPT", "MODIFY", "REJECT", "REFER_PHYSIO", "PHYSIO_REVIEWED"] = "ACCEPT"
    interpretation: str = Field(min_length=1)
    action: str = Field(default="PREVENTION", max_length=80)
    override_reason: str = ""


class MovementReportPayload(BaseModel):
    summary: str = Field(min_length=1)


class MovementScreeningResponse(BaseModel):
    id: str
    session_id: str | None = None
    athlete_id: str
    athlete_safesport_id: str
    athlete_name: str
    institution_id: str | None = None
    institution_name: str = ""
    sport: str = ""
    team: str = ""
    drill: str
    camera_view: str
    status: str
    video_url: str = ""
    video_public_id: str = ""
    video_metadata: dict[str, Any] = Field(default_factory=dict)
    ai_result: dict[str, Any] = Field(default_factory=dict)
    clinician_review: dict[str, Any] = Field(default_factory=dict)
    physio_review: dict[str, Any] = Field(default_factory=dict)
    report_summary: str = ""
    report_generated_at: datetime | None = None
    created_at: datetime


class MovementWorkspaceResponse(BaseModel):
    sessions: list[MovementSessionResponse]
    screenings: list[MovementScreeningResponse]
    notices: list[dict[str, Any]] = Field(default_factory=list)


class Observation(BaseModel):
    finding: str
    severity: str
    confidence: float = Field(ge=0, le=1)
    evidence_metrics: list[str] = Field(default_factory=list)
    evidence_timestamps_ms: list[int] = Field(default_factory=list)


class InterpretationOutput(BaseModel):
    summary: str
    observations: list[Observation] = Field(default_factory=list)
    risk_interpretation: str = ""
    suggested_prevention_focus: list[str] = Field(default_factory=list)
    clinician_questions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
