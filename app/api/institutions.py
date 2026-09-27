import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_system_admin, verify_csrf
from app.core.config import get_settings
from app.db.session import get_db
from app.models.institution import Institution, Sport
from app.schemas.institution import InstitutionResponse, SportCreateRequest, SportResponse
from app.services.cloudinary_service import upload_institution_logo

catalog_router = APIRouter(prefix="/catalog", tags=["catalog"])
admin_router = APIRouter(
    prefix="/admin",
    tags=["system administration"],
    dependencies=[Depends(require_system_admin)],
)
settings = get_settings()


def _sport_response(sport: Sport) -> SportResponse:
    return SportResponse(id=sport.id, name=sport.name, is_active=sport.is_active)


def _institution_response(institution: Institution) -> InstitutionResponse:
    logo_url = _logo_url(institution.logo_path)
    return InstitutionResponse(
        id=institution.id,
        name=institution.name,
        type=institution.type,
        city=institution.city,
        country=institution.country,
        contact_email=institution.contact_email,
        logo_url=logo_url,
        is_active=institution.is_active,
        sports=sorted((_sport_response(sport) for sport in institution.sports), key=lambda item: item.name),
    )


def _logo_url(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    return f"{settings.backend_public_url.rstrip('/')}/{value.lstrip('/')}"


def _load_sports(db: Session, sport_ids: list[str]) -> list[Sport]:
    try:
        ids = [uuid.UUID(value) for value in sport_ids]
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "One or more sports are invalid") from exc
    sports = list(db.scalars(select(Sport).where(Sport.id.in_(ids), Sport.is_active.is_(True))))
    if len(sports) != len(set(ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "One or more sports are unavailable")
    return sports


@catalog_router.get("/institutions", response_model=list[InstitutionResponse])
def public_institutions(search: str = "", db: Session = Depends(get_db)) -> list[InstitutionResponse]:
    statement = select(Institution).where(Institution.is_active.is_(True))
    if search.strip():
        statement = statement.where(Institution.name.ilike(f"%{search.strip()}%"))
    institutions = db.scalars(statement.order_by(Institution.name).limit(50)).unique().all()
    return [_institution_response(item) for item in institutions]


@catalog_router.get("/sports", response_model=list[SportResponse])
def public_sports(db: Session = Depends(get_db)) -> list[SportResponse]:
    sports = db.scalars(select(Sport).where(Sport.is_active.is_(True)).order_by(Sport.name)).all()
    return [_sport_response(item) for item in sports]


@admin_router.get("/institutions", response_model=list[InstitutionResponse])
def admin_institutions(db: Session = Depends(get_db)) -> list[InstitutionResponse]:
    institutions = db.scalars(select(Institution).order_by(Institution.name)).unique().all()
    return [_institution_response(item) for item in institutions]


@admin_router.post(
    "/institutions",
    response_model=InstitutionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def create_institution(
    name: str = Form(min_length=2, max_length=200),
    type: str = Form(pattern=r"^(school|club|academy|professional|medical)$"),
    city: str = Form(min_length=2, max_length=100),
    country: str = Form(min_length=2, max_length=100),
    contact_email: str | None = Form(default=None, max_length=320),
    is_active: bool = Form(default=True),
    sport_ids: list[str] = Form(default=[]),
    logo: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> InstitutionResponse:
    institution = Institution(
        name=name.strip(),
        type=type,
        city=city.strip(),
        country=country.strip(),
        contact_email=contact_email.strip().lower() if contact_email else None,
        is_active=is_active,
        sports=_load_sports(db, sport_ids),
        logo_path=await upload_institution_logo(logo),
    )
    db.add(institution)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This institution already exists") from exc
    db.refresh(institution)
    return _institution_response(institution)


@admin_router.put(
    "/institutions/{institution_id}",
    response_model=InstitutionResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_institution(
    institution_id: uuid.UUID,
    name: str = Form(min_length=2, max_length=200),
    type: str = Form(pattern=r"^(school|club|academy|professional|medical)$"),
    city: str = Form(min_length=2, max_length=100),
    country: str = Form(min_length=2, max_length=100),
    contact_email: str | None = Form(default=None, max_length=320),
    is_active: bool = Form(default=True),
    sport_ids: list[str] = Form(default=[]),
    logo: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> InstitutionResponse:
    institution = db.get(Institution, institution_id)
    if not institution:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Institution not found")
    institution.name = name.strip()
    institution.type = type
    institution.city = city.strip()
    institution.country = country.strip()
    institution.contact_email = contact_email.strip().lower() if contact_email else None
    institution.is_active = is_active
    institution.sports = _load_sports(db, sport_ids)
    new_logo = await upload_institution_logo(logo)
    if new_logo:
        institution.logo_path = new_logo
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This institution already exists") from exc
    db.refresh(institution)
    return _institution_response(institution)


@admin_router.get("/sports", response_model=list[SportResponse])
def admin_sports(db: Session = Depends(get_db)) -> list[SportResponse]:
    return [_sport_response(item) for item in db.scalars(select(Sport).order_by(Sport.name)).all()]


@admin_router.post(
    "/sports",
    response_model=SportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
def create_sport(payload: SportCreateRequest, db: Session = Depends(get_db)) -> SportResponse:
    name = " ".join(payload.name.split())
    existing = db.scalar(select(Sport).where(func.lower(Sport.name) == name.lower()))
    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.commit()
        return _sport_response(existing)
    sport = Sport(name=name)
    db.add(sport)
    db.commit()
    db.refresh(sport)
    return _sport_response(sport)
