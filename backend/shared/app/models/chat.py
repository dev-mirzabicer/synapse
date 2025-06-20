import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

class ChatGroup(Base):
    __tablename__ = "chat_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True) # Will be a FK to a User table later
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    members: Mapped[list["GroupMember"]] = relationship(back_populates="group")
    messages: Mapped[list["Message"]] = relationship(back_populates="group")

# ... other models like GroupMember, Message, etc. will follow this pattern ...