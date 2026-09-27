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
    email: EmailStr
    first_name: str
    last_name: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime


class AdminUserCreateRequest(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: AdminRole
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True


class AdminUserUpdateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: AdminRole
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool = True


class AdminOverviewResponse(BaseModel):
    total_users: int
    active_users: int
    institutions: int
    active_institutions: int
    sports: int
    active_sports: int
