import uuid

from pydantic import BaseModel, EmailStr, Field


class SportResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool


class InstitutionResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    city: str
    country: str
    contact_email: EmailStr | None
    logo_url: str | None
    is_active: bool
    sports: list[SportResponse]


class SportCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)

