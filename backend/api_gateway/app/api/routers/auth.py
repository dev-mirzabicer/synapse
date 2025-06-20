from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from shared.app.db import get_db_session
from shared.app.schemas.auth import UserCreate
from shared.app.models.chat import User
from app.core.security import get_password_hash

router = APIRouter()

@router.post("/register", status_code=201)
async def register_user(user_in: UserCreate, db: AsyncSession = Depends(get_db_session)):
    # TODO (Phase 1): Check if user already exists
    hashed_password = get_password_hash(user_in.password)
    user = User(email=user_in.email, hashed_password=hashed_password)
    async with db() as session:
        session.add(user)
        await session.commit()
    return {"message": "User created successfully"}

# TODO (Phase 1): Implement /login endpoint that returns a JWT token