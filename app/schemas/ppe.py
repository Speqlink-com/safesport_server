import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PPEConsentPayload(BaseModel):
    clinical: Literal["obtained", "declined", "deferred", "withdrawn"] = "deferred"
    video: bool = False
    research: bool = False
    assent: bool = False
    signer: str = Field(default="", max_length=200)
    version: str = Field(default="PPE privacy v1.0", max_length=100)


class PPEConsentResponse(PPEConsentPayload):
    athlete_id: str
    at: str


class PPEAssessmentPayload(BaseModel):
    status: str = "draft"
    history: dict[str, str] = Field(default_factory=dict)
    followups: dict[str, str] = Field(default_factory=dict)
    historyAnswers: dict[str, str] = Field(default_factory=dict)
    historyDetails: dict[str, dict[str, Any]] = Field(default_factory=dict)
    historyResolutions: dict[str, str] = Field(default_factory=dict)
    historySubmitted: bool = False
    injuries: list[dict[str, Any]] = Field(default_factory=list)
    concussion: dict[str, Any] = Field(default_factory=dict)
    reviewed: bool = False
    exam: dict[str, str] = Field(default_factory=dict)
    examNotes: dict[str, str] = Field(default_factory=dict)
    baseline: dict[str, str] = Field(default_factory=dict)
    baselineNotes: dict[str, str] = Field(default_factory=dict)
    vitals: dict[str, str] = Field(default_factory=dict)
    sportNotes: str = ""
    decision: str = "pending_evaluation"
    restrictions: str = ""
    plan: str = ""
    reviewDate: str = ""
    rationale: str = ""
    signature: str = ""
    finalized: bool = False
    careReview: dict[str, str] | None = None
    reassessmentRequestIds: list[str] = Field(default_factory=list)


class PPEStartRequest(BaseModel):
    athlete_id: str


class PPEBulkDeleteRequest(BaseModel):
    assessment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class PPEPhysioReviewRequest(BaseModel):
    status: Literal["not_required", "pending", "reviewed", "complete"] = "reviewed"
    note: str = Field(default="", max_length=2000)


class PPEEncounterResponse(PPEAssessmentPayload):
    id: str
    athleteId: str
    date: str
    certificateCode: str | None = None
    certificateIssuedAt: datetime | None = None
    physioStatus: str = "not_required"
    physioNote: str = ""


class PPEAthleteResponse(BaseModel):
    id: str
    firstName: str
    lastName: str
    dateOfBirth: str
    age: int
    gender: str = "other"
    currentOrganization: dict[str, Any] | None = None
    currentTeam: dict[str, Any] | None = None
    currentSport: dict[str, Any] | None = None
    eligibilityStatus: str = "pending_evaluation"
    readiness: str = "under_review"
    nextReview: str | None = None
    organizations: list[dict[str, Any]] = Field(default_factory=list)
    teams: list[dict[str, Any]] = Field(default_factory=list)
    guardians: list[dict[str, Any]] = Field(default_factory=list)
    ppeAssessments: list[dict[str, Any]] = Field(default_factory=list)
    incidents: list[dict[str, Any]] = Field(default_factory=list)
    screenings: list[dict[str, Any]] = Field(default_factory=list)
    referrals: list[dict[str, Any]] = Field(default_factory=list)
    eligibilityHistory: list[dict[str, Any]] = Field(default_factory=list)
    createdAt: str
    updatedAt: str


class PPENoticeResponse(BaseModel):
    id: str
    role: str
    title: str
    path: str
    read: bool = False
    date: str


class PPEWorkspaceResponse(BaseModel):
    athletes: list[PPEAthleteResponse]
    consents: dict[str, PPEConsentResponse]
    encounters: list[PPEEncounterResponse]
    notices: list[PPENoticeResponse]


class CertificateVerifyResponse(BaseModel):
    valid: bool
    code: str
    athlete_name: str
    athlete_id: str
    institution: str
    sport: str
    eligibility: str
    restrictions: str
    review_date: str
    clinician_signature: str
    issued_at: datetime | None
