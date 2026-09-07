"""
Authentication and authorization using JWT
Provides token generation, validation, and role-based access control
"""

import os
from datetime import datetime, timedelta
from typing import Optional, Dict
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session
import logging

from db import User

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenData(BaseModel):
    username: Optional[str] = None
    exp: Optional[datetime] = None
    role: str = "viewer"


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str = "operator"


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """Verify JWT token and extract claims"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role", "viewer")
        if username is None:
            return None
        token_data = TokenData(username=username, role=role)
        return token_data
    except JWTError as e:
        logger.error(f"Token verification failed: {e}")
        return None


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """Authenticate user by username and password"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(
    db: Session, username: str, email: str, password: str, role: str = "operator"
) -> User:
    """Create a new user"""
    hashed_password = get_password_hash(password)
    user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def is_admin(token_data: TokenData) -> bool:
    """Check if user is admin"""
    return token_data.role == "admin"


def is_operator(token_data: TokenData) -> bool:
    """Check if user is operator or admin"""
    return token_data.role in ["admin", "operator"]


def is_viewer(token_data: TokenData) -> bool:
    """Check if user can view (all roles can)"""
    return token_data.role in ["admin", "operator", "viewer"]
