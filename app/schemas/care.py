from typing import Any, Literal

from pydantic import BaseModel, Field

CareCollection = Literal[
    "referrals",
    "incidents",
    "plans",
    "sessions",
    "reviews",
    "events",
    "tasks",
    "documents",
]


class CareRecordPayload(BaseModel):
    id: str | None = None
    athleteId: str | None = None
    title: str = Field(min_length=1, max_length=200)
    status: str = Field(min_length=1, max_length=60)
    date: str = Field(default="", max_length=40)
    notes: str = ""
    assigned: str = Field(default="", max_length=200)
    kind: str = Field(default="", max_length=80)
    outcome: str = ""
    coordination: str = ""
    urgency: str = Field(default="", max_length=40)
    progress: int | None = Field(default=None, ge=0, le=100)
    parentId: str | None = None
    encounterId: str | None = None
    referralId: str | None = None
    reviewedEncounterId: str | None = None
    file: str | None = None
    fileName: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class CareRecordResponse(CareRecordPayload):
    id: str


class CareNoticeResponse(BaseModel):
    id: str
    role: str
    title: str
    path: str
    read: bool = False
    date: str


class CareWorkspaceResponse(BaseModel):
    records: dict[str, list[CareRecordResponse]]
    notices: list[CareNoticeResponse]
