from datetime import date, datetime
from pydantic import BaseModel, Field


class TermReportGenerateRequest(BaseModel):
    title: str = Field(default="Termly athlete progress report", max_length=200)
    period_start: date
    period_end: date


class ReportSummary(BaseModel):
    id: str
    athlete_id: str
    athlete_name: str
    title: str
    period_start: date
    period_end: date
    status: str
    created_at: datetime
