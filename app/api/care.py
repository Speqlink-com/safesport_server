import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import current_user, verify_csrf
from app.db.session import get_db
from app.models.auth import User
from app.models.care import CareRecord
from app.models.ppe import PPEAssessment
from app.schemas.care import CareCollection, CareNoticeResponse, CareRecordPayload, CareRecordResponse, CareWorkspaceResponse

router = APIRouter(prefix="/care", tags=["care records"])
ALL_COLLECTIONS = ["referrals", "incidents", "plans", "sessions", "reviews", "events", "tasks", "documents"]
CLINICAL_ROLES = {"clinician", "physiotherapist", "operations", "institution", "coach", "sys-admin"}
MUTATE_ROLES = {"clinician", "physiotherapist", "operations", "institution", "coach"}


def _visible_athlete_ids(db: Session, user: User) -> list[uuid.UUID]:
    if user.role == "athlete":
        return [user.id]
    if user.role == "guardian":
        try:
            return [uuid.UUID(str((user.profile_data or {}).get("athlete_id") or ""))]
        except ValueError:
            return []
    if user.role in CLINICAL_ROLES:
        return list(db.scalars(select(User.id).where(User.role == "athlete", User.is_active.is_(True))).all())
    return []


def _require_collection_access(collection: str, user: User, write: bool = False) -> None:
    if write and user.role not in MUTATE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Care record updates require an authorized staff role")
    if user.role == "guardian" and collection not in {"incidents", "plans", "sessions", "reviews", "events", "documents"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Guardian access is limited to linked child progress and permitted documents")
    if user.role == "athlete" and write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Athletes cannot update clinical care records")


def _uuid_or_none(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Linked record id is invalid") from exc


def _athlete_uuid(payload: CareRecordPayload, user: User, visible_ids: list[uuid.UUID]) -> uuid.UUID | None:
    athlete_id = _uuid_or_none(payload.athleteId)
    if athlete_id and athlete_id not in visible_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Athlete is not in your permitted scope")
    if not athlete_id and visible_ids:
        athlete_id = visible_ids[0]
    return athlete_id


def _response(record: CareRecord) -> CareRecordResponse:
    return CareRecordResponse(
        id=str(record.id),
        athleteId=str(record.athlete_user_id) if record.athlete_user_id else None,
        title=record.title,
        status=record.status,
        date=record.date,
        notes=record.notes,
        assigned=record.assigned,
        kind=record.kind,
        outcome=record.outcome,
        coordination=record.coordination,
        urgency=record.urgency,
        progress=record.progress,
        parentId=str(record.parent_id) if record.parent_id else None,
        encounterId=str(record.encounter_id) if record.encounter_id else None,
        referralId=str(record.referral_id) if record.referral_id else None,
        reviewedEncounterId=str(record.reviewed_encounter_id) if record.reviewed_encounter_id else None,
        file=record.file_url or None,
        fileName=record.file_name or None,
        extra=record.extra or {},
    )


def _apply(record: CareRecord, collection: str, payload: CareRecordPayload, user: User, visible_ids: list[uuid.UUID]) -> None:
    athlete_id = _athlete_uuid(payload, user, visible_ids)
    record.collection = collection
    record.athlete_user_id = athlete_id
    record.title = payload.title.strip()
    record.status = payload.status
    record.date = payload.date
    record.notes = payload.notes.strip()
    record.assigned = payload.assigned.strip()
    record.kind = payload.kind or collection
    record.outcome = payload.outcome.strip()
    record.coordination = payload.coordination.strip()
    record.urgency = payload.urgency
    record.progress = payload.progress
    record.parent_id = _uuid_or_none(payload.parentId)
    record.encounter_id = _uuid_or_none(payload.encounterId)
    record.referral_id = _uuid_or_none(payload.referralId)
    record.reviewed_encounter_id = _uuid_or_none(payload.reviewedEncounterId)
    record.file_url = payload.file or ""
    record.file_name = payload.fileName or ""
    record.extra = payload.extra
    record.created_by_user_id = record.created_by_user_id or user.id


def _notices(records: list[CareRecord], user: User) -> list[CareNoticeResponse]:
    notices: list[CareNoticeResponse] = []
    role = user.role
    for record in records:
        date = record.updated_at.isoformat()
        if role in {"athlete", "guardian"}:
            if record.collection == "incidents":
                notices.append(CareNoticeResponse(id=f"care-injury-{record.id}", role=role, title=f"Injury update: {record.title}", path="health", date=date))
            if record.collection in {"plans", "sessions", "reviews"} and record.status != "completed":
                notices.append(CareNoticeResponse(id=f"care-rehab-{record.id}", role=role, title=f"Rehabilitation progress: {record.title}", path="health?tab=rehabilitation", date=date))
            if record.collection == "reviews" and record.status == "reassessment_requested":
                notices.append(CareNoticeResponse(id=f"care-rtp-{record.id}", role=role, title="Return-to-play reassessment requested", path="eligibility", date=date))
        elif role == "physiotherapist" and record.collection in {"referrals", "plans", "sessions", "reviews"}:
            notices.append(CareNoticeResponse(id=f"care-physio-{record.id}", role=role, title=f"Care task: {record.title}", path="rehabilitation", date=date))
        elif role == "clinician" and record.collection in {"incidents", "reviews", "referrals"}:
            path = "incidents" if record.collection == "incidents" else "rehabilitation"
            notices.append(CareNoticeResponse(id=f"care-clinician-{record.id}", role=role, title=f"Clinical update: {record.title}", path=path, date=date))
    return notices[:20]


@router.get("/workspace", response_model=CareWorkspaceResponse)
def workspace(user: User = Depends(current_user), db: Session = Depends(get_db)) -> CareWorkspaceResponse:
    visible_ids = _visible_athlete_ids(db, user)
    records = list(db.scalars(select(CareRecord).where(CareRecord.athlete_user_id.in_(visible_ids)).order_by(CareRecord.updated_at.desc())).all()) if visible_ids else []
    if user.role == "guardian":
        records = [r for r in records if r.collection in {"incidents", "plans", "sessions", "reviews", "events", "documents"}]
    if user.role == "athlete":
        records = [r for r in records if r.collection != "tasks"]
    if user.role == "coach":
        records = [r for r in records if r.collection in {"incidents", "events", "tasks"}]
    if user.role == "physiotherapist":
        records = [r for r in records if r.collection in {"referrals", "plans", "sessions", "reviews", "events", "documents", "incidents"}]
    grouped = {collection: [] for collection in ALL_COLLECTIONS}
    for record in records:
        grouped.setdefault(record.collection, []).append(_response(record))
    return CareWorkspaceResponse(records=grouped, notices=_notices(records, user))


@router.post("/{collection}", response_model=CareRecordResponse, dependencies=[Depends(verify_csrf)])
def create_record(collection: CareCollection, payload: CareRecordPayload, user: User = Depends(current_user), db: Session = Depends(get_db)) -> CareRecordResponse:
    _require_collection_access(collection, user, write=True)
    visible_ids = _visible_athlete_ids(db, user)
    record = CareRecord(collection=collection, title=payload.title, status=payload.status)
    _apply(record, collection, payload, user, visible_ids)
    db.add(record)
    db.commit()
    db.refresh(record)
    return _response(record)


@router.put("/{collection}/{record_id}", response_model=CareRecordResponse, dependencies=[Depends(verify_csrf)])
def update_record(collection: CareCollection, record_id: uuid.UUID, payload: CareRecordPayload, user: User = Depends(current_user), db: Session = Depends(get_db)) -> CareRecordResponse:
    _require_collection_access(collection, user, write=True)
    visible_ids = _visible_athlete_ids(db, user)
    record = db.get(CareRecord, record_id)
    if not record or record.collection != collection or (record.athlete_user_id and record.athlete_user_id not in visible_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Care record not found")
    _apply(record, collection, payload, user, visible_ids)
    if collection == "sessions" and record.parent_id and record.progress is not None:
        plan = db.get(CareRecord, record.parent_id)
        if plan and plan.collection == "plans":
            plan.progress = record.progress
            if record.progress >= 100:
                plan.status = "completed"
    if collection == "reviews" and record.status == "reassessment_requested" and record.athlete_user_id:
        latest = db.scalar(select(PPEAssessment).where(PPEAssessment.athlete_user_id == record.athlete_user_id, PPEAssessment.finalized.is_(True)).order_by(PPEAssessment.updated_at.desc()))
        record.reviewed_encounter_id = latest.id if latest else None
    db.commit()
    db.refresh(record)
    return _response(record)
