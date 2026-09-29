import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

AdminRole = Literal[
    "athlete",
    "guardian",
    "clinician",
    "physiotherapist",
    "coach",
    "institution",
    "operations",
    "sys-admin",
]


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    safesport_id: str
    email: EmailStr
    first_name: str
    last_name: str
    role: str
    is_active: bool
    is_verified: bool
    profile_data: dict[str, str] = {}
    created_at: datetime


class AdminUserCreateRequest(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: AdminRole
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True
    institution_id: str | None = Field(default=None, max_length=100)


class AdminUserUpdateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: AdminRole
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool = True
    institution_id: str | None = Field(default=None, max_length=100)


class AdminOverviewResponse(BaseModel):
    total_users: int
    active_users: int
    institutions: int
    active_institutions: int
    sports: int
    active_sports: int
