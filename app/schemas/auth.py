import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class MessageResponse(BaseModel):
    detail: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    first_name: str
    last_name: str
    role: str
    profile_data: dict[str, str] = {}


class SessionResponse(BaseModel):
    user: UserResponse


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class OtpRequest(BaseModel):
    code: str = Field(pattern=r"^\d{4}$")


class UpdateMeRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=40)


class RegistrationStartRequest(BaseModel):
    role: Literal["athlete", "guardian"]
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    date_of_birth: date | None = None
    organization_id: str | None = Field(default=None, max_length=100)
    organization_name: str | None = Field(default=None, max_length=200)
    sport_id: str | None = Field(default=None, max_length=100)
    relationship: Literal["parent", "legal_guardian", "other"] | None = None
    athlete_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_role_fields(self) -> "RegistrationStartRequest":
        if self.role == "athlete" and (not self.date_of_birth or not self.organization_id or not self.sport_id):
            raise ValueError("Athlete date of birth, institution and sport are required")
        if self.role == "guardian" and (not self.relationship or not self.athlete_id):
            raise ValueError("Guardian relationship and athlete are required")
        return self


class PendingRegistrationResponse(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    role: str
    profile_data: dict[str, str]
    is_verified: bool


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)
