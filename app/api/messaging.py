import uuid
from collections import defaultdict
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from sqlalchemy import and_, select
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

def _allowed_people(user: User, db: Session) -> list[User]:
    stmt = select(User).where(User.is_active.is_(True), User.id != user.id)
    users = list(db.scalars(stmt.order_by(User.first_name, User.last_name)).all())
    if user.role in GLOBAL_ROLES or user.role == "sys-admin": return users
    inst = _institution_id(user, db)
    def visible(other: User) -> bool:
        if other.role in GLOBAL_ROLES: return True
        if not inst and user.role == "institution": return other.role == "athlete" or other.role in {"guardian", "coach", "institution"}
        return str((other.profile_data or {}).get("organization_id") or (other.profile_data or {}).get("institution_id") or "") == str(inst)
    return [u for u in users if visible(u)]

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

def _family_conversation(db: Session, user: User) -> Conversation:
    inst=_institution_id(user, db)
    title="Institution family group"
    conv=db.scalar(select(Conversation).where(Conversation.kind=="institution_group", Conversation.institution_id==inst)) if inst else None
    if not conv:
        conv=Conversation(kind="institution_group", title=title, institution_id=inst, created_by_user_id=user.id); db.add(conv); db.flush()
    people=[user]+_allowed_people(user, db)
    for person in people:
        if not _is_member(db, conv.id, person.id): db.add(ConversationMember(conversation_id=conv.id,user_id=person.id))
    db.commit(); db.refresh(conv); return conv

@router.get("/workspace", response_model=MessagingWorkspaceResponse)
def workspace(user: User = Depends(current_user), db: Session = Depends(get_db)) -> MessagingWorkspaceResponse:
    _family_conversation(db, user)
    convs=list(db.scalars(select(Conversation).join(ConversationMember).where(ConversationMember.user_id==user.id).order_by(Conversation.created_at.desc())).unique().all())
    return MessagingWorkspaceResponse(current_user=_user_response(user), people=[_user_response(u) for u in _allowed_people(user, db)], conversations=[_conversation_response(c, db) for c in convs])

@router.post("/conversations/direct/{recipient_id}", response_model=ConversationResponse, dependencies=[Depends(verify_csrf)])
def start_direct(recipient_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> ConversationResponse:
    recipient=db.get(User, recipient_id)
    if not recipient or recipient not in _allowed_people(user, db): raise HTTPException(status.HTTP_404_NOT_FOUND, "Contact is not available")
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
