from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from shared.app.db import get_db_session
from shared.app.schemas.auth import UserCreate, Token, UserRead # Added UserRead
from shared.app.models.chat import User
from app.core.security import get_password_hash, verify_password, create_access_token, get_current_user # Added get_current_user

router = APIRouter()
logger = structlog.get_logger(__name__)

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user_in: UserCreate, db: AsyncSession = Depends(get_db_session)):
    logger.info("register_user.start", email=user_in.email)
    async with db() as session:
        try:
            result = await session.execute(select(User).where(User.email == user_in.email))
            if result.scalars().first():
                logger.warn("register_user.email_exists", email=user_in.email)
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

            hashed_password = get_password_hash(user_in.password)
            user = User(email=user_in.email, hashed_password=hashed_password)
            session.add(user)
            await session.commit()
            logger.info("register_user.success", user_id=str(user.id))
        except HTTPException:
            raise
        except Exception as e:
            if hasattr(session, "rollback"):
                await session.rollback()
            logger.error("register_user.error", error=str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {e}")
    return {"message": "User created successfully"}

@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db_session)
):
    logger.info("login.start", username=form_data.username)
    async with db() as session:
        try:
            result = await session.execute(select(User).where(User.email == form_data.username))
            user = result.scalars().first()
        except Exception as e:
            logger.error("login.db_error", error=str(e), exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {e}")

    if not user or not verify_password(form_data.password, user.hashed_password):
        logger.warn("login.auth_failed", username=form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    logger.info("login.success", user_id=str(user.id))
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserRead)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Get current logged-in user details.
    """
    logger.info("read_users_me.accessed", user_id=str(current_user.id))
    return current_user