from pydantic import BaseModel, EmailStr
import uuid # Added for UserRead

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserRead(BaseModel):
    """Schema for reading user information."""
    id: uuid.UUID
    email: EmailStr
    # Add other non-sensitive fields if needed in the future, e.g., name, created_at

    class Config:
        from_attributes = True