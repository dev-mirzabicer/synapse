import sys, pathlib, os
root = pathlib.Path(__file__).resolve().parents[1]
sys.path.extend([
    str(root/"backend"),
    str(root/"backend/shared"),
])
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from shared.app.models.base import Base
from shared.app.models.chat import User, ChatGroup, Message

@pytest.mark.asyncio
async def test_models_crud():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        user = User(email="a@b.com", hashed_password="h")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        group = ChatGroup(owner_id=user.id, name="g")
        session.add(group)
        await session.commit()
        await session.refresh(group)
        msg = Message(group_id=group.id, turn_id=group.id, sender_alias="User", content="hi")
        session.add(msg)
        await session.commit()
        await session.refresh(msg)
        assert msg.id is not None
