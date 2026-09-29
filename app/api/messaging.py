import uuid
from collections import defaultdict
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import current_user, verify_csrf
from app.db.session import SessionLocal, get_db
from app.models.auth import User
from app.models.institution import Institution
from app.models.messaging import Conversation, ConversationMember, Message
from app.schemas.messaging import ConversationResponse, MessageResponse, MessageUser, MessagingWorkspaceResponse
from app.services.auth_service import ACCESS_COOKIE, get_access_user
from app.services.cloudinary_service import upload_message_attachment

router = APIRouter(prefix="/messaging", tags=["messaging"])
GLOBAL_ROLES = {"clinician", "physiotherapist", "sys-admin"}
INSTITUTION_LOCAL_ROLES = {"athlete", "guardian", "coach", "institution"}
COACH_DIRECT_GLOBAL_ROLES = {"clinician", "physiotherapist", "sys-admin"}
GLOBAL_DIRECT_ROLES = {"coach", "clinician", "physiotherapist", "sys-admin"}
TOP_GROUP_ROLES = {"clinician", "physiotherapist", "sys-admin", "operations"}
connections: dict[str, set[WebSocket]] = defaultdict(set)


def _name(user: User) -> str: return f"{user.first_name} {user.last_name}".strip()

def _institution_id(user: User, db: Session) -> uuid.UUID | None:
    raw = (user.profile_data or {}).get("institution_id") or (user.profile_data or {}).get("organization_id")
    if raw:
        try: return uuid.UUID(str(raw))
        except ValueError: return None
    if user.role == "institution":
        inst = db.scalar(select(Institution).where(Institution.contact_email == user.email))
        return inst.id if inst else None
    return None

def _user_response(user: User) -> MessageUser:
    return MessageUser(id=str(user.id), name=_name(user), role=user.role, institution_id=str((user.profile_data or {}).get("organization_id") or (user.profile_data or {}).get("institution_id") or "") or None)

def _same_institution(user: User, other: User, db: Session) -> bool:
    inst = _institution_id(user, db)
    other_inst = _institution_id(other, db)
    if inst and other_inst:
        return inst == other_inst
    if user.role == "institution" and not inst:
        # Prototype fallback for institution admin accounts not yet linked to one institution.
        return other.role in INSTITUTION_LOCAL_ROLES
    return False


def _allowed_people(user: User, db: Session) -> list[User]:
    users = list(db.scalars(select(User).where(User.is_active.is_(True), User.id != user.id).order_by(User.first_name, User.last_name)).all())
    allowed: list[User] = []
    for other in users:
        same_institution = _same_institution(user, other, db)
        if user.role == "athlete":
            if same_institution and other.role in {"athlete", "coach"}:
                allowed.append(other)
            continue
        if user.role == "guardian":
            if same_institution and other.role in {"guardian", "coach", "institution"}:
                allowed.append(other)
            continue
        if user.role == "coach":
            if other.role in COACH_DIRECT_GLOBAL_ROLES or (same_institution and other.role in INSTITUTION_LOCAL_ROLES):
                allowed.append(other)
            continue
        if user.role in GLOBAL_ROLES:
            if other.role in GLOBAL_DIRECT_ROLES:
                allowed.append(other)
            continue
        if user.role == "institution":
            if same_institution and other.role in {"coach", "guardian", "institution"}:
                allowed.append(other)
            continue
        if user.role == "operations":
            if other.role in {"coach", "institution", "clinician", "physiotherapist", "sys-admin"}:
                allowed.append(other)
    return allowed

def _is_member(db: Session, conversation_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return bool(db.scalar(select(ConversationMember.id).where(ConversationMember.conversation_id == conversation_id, ConversationMember.user_id == user_id)))

def _conversation_response(conv: Conversation, db: Session) -> ConversationResponse:
    members=[m.user for m in conv.members]
    messages=list(db.scalars(select(Message).where(Message.conversation_id==conv.id).order_by(Message.created_at.asc()).limit(100)).all())
    return ConversationResponse(id=str(conv.id), kind=conv.kind, title=conv.title, institution_id=str(conv.institution_id) if conv.institution_id else None, members=[_user_response(u) for u in members], messages=[_message_response(m) for m in messages])

def _message_response(message: Message) -> MessageResponse:
    return MessageResponse(id=str(message.id), conversation_id=str(message.conversation_id), sender=_user_response(message.sender), body=message.body, attachment_url=message.attachment_url or None, attachment_name=message.attachment_name or None, attachment_type=message.attachment_type or None, created_at=message.created_at)

def _direct_conversation(db: Session, user: User, recipient: User) -> Conversation:
    mine=set(db.scalars(select(ConversationMember.conversation_id).where(ConversationMember.user_id==user.id)).all())
    theirs=set(db.scalars(select(ConversationMember.conversation_id).where(ConversationMember.user_id==recipient.id)).all())
    for cid in mine & theirs:
        conv=db.get(Conversation,cid)
        if conv and conv.kind=="direct" and len(conv.members)==2: return conv
    conv=Conversation(kind="direct", title=f"{_name(user)} / {_name(recipient)}", institution_id=_institution_id(user, db) or _institution_id(recipient, db), created_by_user_id=user.id)
    db.add(conv); db.flush(); db.add_all([ConversationMember(conversation_id=conv.id,user_id=user.id), ConversationMember(conversation_id=conv.id,user_id=recipient.id)]); db.commit(); db.refresh(conv); return conv

def _group_title(institution: Institution | None) -> str:
    return f"{institution.name} family group" if institution else "Institution family group"


def _group_people(db: Session, institution_id: uuid.UUID | None, current_user: User) -> list[User]:
    users = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.first_name, User.last_name)).all())
    people: list[User] = []
    global_view = current_user.role in GLOBAL_ROLES
    for person in users:
        if global_view:
            if person.role in TOP_GROUP_ROLES:
                people.append(person)
            continue
        if person.role in TOP_GROUP_ROLES:
            people.append(person)
            continue
        if institution_id and str((person.profile_data or {}).get("organization_id") or (person.profile_data or {}).get("institution_id") or "") == str(institution_id):
            people.append(person)
        elif not institution_id and current_user.role == "institution" and person.role in INSTITUTION_LOCAL_ROLES:
            people.append(person)
    if current_user not in people:
        people.append(current_user)
    return people


def _ensure_group(db: Session, institution: Institution | None, user: User) -> Conversation:
    inst_id = institution.id if institution else None
    conv = db.scalar(select(Conversation).where(Conversation.kind == "institution_group", Conversation.institution_id == inst_id)) if inst_id else None
    if not conv:
        conv = Conversation(kind="institution_group", title=_group_title(institution), institution_id=inst_id, created_by_user_id=user.id)
        db.add(conv)
        db.flush()
    else:
        conv.title = _group_title(institution)
    for person in _group_people(db, inst_id, user):
        if not _is_member(db, conv.id, person.id):
            db.add(ConversationMember(conversation_id=conv.id, user_id=person.id))
    db.commit()
    db.refresh(conv)
    return conv


def _family_conversations(db: Session, user: User) -> list[Conversation]:
    if user.role in GLOBAL_ROLES:
        institutions = list(db.scalars(select(Institution).where(Institution.is_active.is_(True)).order_by(Institution.name)).all())
        return [_ensure_group(db, institution, user) for institution in institutions]
    inst = _institution_id(user, db)
    institution = db.get(Institution, inst) if inst else None
    if not institution and user.role != "institution":
        return []
    return [_ensure_group(db, institution, user)]

@router.get("/workspace", response_model=MessagingWorkspaceResponse)
def workspace(user: User = Depends(current_user), db: Session = Depends(get_db)) -> MessagingWorkspaceResponse:
    families = _family_conversations(db, user)
    family_ids = {conversation.id for conversation in families}
    convs = list(db.scalars(select(Conversation).join(ConversationMember).where(ConversationMember.user_id == user.id).order_by(Conversation.created_at.desc())).unique().all())
    allowed_ids = {person.id for person in _allowed_people(user, db)}
    direct = [
        conversation
        for conversation in convs
        if conversation.kind == "direct" and any(member.user_id in allowed_ids for member in conversation.members if member.user_id != user.id)
    ]
    ordered = families + direct if user.role in GLOBAL_ROLES else families[:1] + direct
    seen: set[uuid.UUID] = set()
    unique_ordered = []
    for conversation in ordered:
        if conversation.id not in seen:
            unique_ordered.append(conversation)
            seen.add(conversation.id)
    return MessagingWorkspaceResponse(current_user=_user_response(user), people=[_user_response(u) for u in _allowed_people(user, db)], conversations=[_conversation_response(c, db) for c in unique_ordered])

@router.post("/conversations/direct/{recipient_id}", response_model=ConversationResponse, dependencies=[Depends(verify_csrf)])
def start_direct(recipient_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> ConversationResponse:
    recipient=db.get(User, recipient_id)
    allowed_ids = {person.id for person in _allowed_people(user, db)}
    if not recipient or recipient.id not in allowed_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact is not available")
    return _conversation_response(_direct_conversation(db, user, recipient), db)

@router.post("/messages", response_model=MessageResponse, dependencies=[Depends(verify_csrf)])
async def send_message(conversation_id: uuid.UUID = Form(...), body: str = Form(default=""), attachment: UploadFile | None = File(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)) -> MessageResponse:
    if not _is_member(db, conversation_id, user.id): raise HTTPException(status.HTTP_403_FORBIDDEN, "Conversation is not available")
    if not body.strip() and not attachment: raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Message text or attachment is required")
    url=await upload_message_attachment(attachment)
    message=Message(conversation_id=conversation_id, sender_user_id=user.id, body=body.strip(), attachment_url=url or "", attachment_name=attachment.filename if attachment else "", attachment_type=attachment.content_type if attachment else "")
    db.add(message); db.commit(); db.refresh(message)
    payload=_message_response(message).model_dump(mode="json")
    for ws in list(connections[str(conversation_id)]):
        try: await ws.send_json({"type":"message", "message": payload})
        except Exception: connections[str(conversation_id)].discard(ws)
    return _message_response(message)

@router.websocket("/ws/{conversation_id}")
async def ws_messages(websocket: WebSocket, conversation_id: str):
    await websocket.accept()
    db=SessionLocal()
    try:
        token=websocket.cookies.get(ACCESS_COOKIE)
        if not token: await websocket.close(code=4401); return
        class Req:
            cookies={ACCESS_COOKIE: token}
        user=get_access_user(Req(), db)  # type: ignore[arg-type]
        cid=uuid.UUID(conversation_id)
        if not _is_member(db, cid, user.id): await websocket.close(code=4403); return
        connections[conversation_id].add(websocket)
        while True: await websocket.receive_text()
    except (WebSocketDisconnect, ValueError):
        pass
    finally:
        connections[conversation_id].discard(websocket)
        db.close()
