import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

# TODO (Phase 1): Create a separate user.py for the User model
class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)

class GroupMember(Base):
    __tablename__ = "group_members"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_groups.id"), index=True)
    alias: Mapped[str] = mapped_column(String(100))
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    tools: Mapped[list[str] | None] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(50), default="openai")
    model: Mapped[str] = mapped_column(String(100), default="gpt-4o")
    temperature: Mapped[float] = mapped_column(default=0.1)

    group: Mapped["ChatGroup"] = relationship(back_populates="members")

class ChatGroup(Base):
    __tablename__ = "chat_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    members: Mapped[list["GroupMember"]] = relationship(back_populates="group")
    messages: Mapped[list["Message"]] = relationship(back_populates="group")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_groups.id"), index=True)
    turn_id: Mapped[uuid.UUID] = mapped_column(index=True)
    sender_alias: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(String)
    parent_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    meta: Mapped[dict | None] = mapped_column(JSON)

    group: Mapped["ChatGroup"] = relationship(back_populates="messages")