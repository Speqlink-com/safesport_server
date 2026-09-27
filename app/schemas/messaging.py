from datetime import datetime
from pydantic import BaseModel


class MessageUser(BaseModel):
    id: str
    name: str
    role: str
    institution_id: str | None = None


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender: MessageUser
    body: str
    attachment_url: str | None = None
    attachment_name: str | None = None
    attachment_type: str | None = None
    created_at: datetime


class ConversationResponse(BaseModel):
    id: str
    kind: str
    title: str
    institution_id: str | None = None
    members: list[MessageUser]
    messages: list[MessageResponse]


class MessagingWorkspaceResponse(BaseModel):
    current_user: MessageUser
    people: list[MessageUser]
    conversations: list[ConversationResponse]
