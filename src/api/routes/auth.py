"""
FinSight AI — Auth Routes
POST /auth/login    — issue JWT
POST /auth/refresh  — extend token
GET  /auth/me       — current user profile
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from config.settings import get_settings
from src.security.auth import Token, UserInDB, authenticate_user, create_access_token
from src.api.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


class UserProfile(BaseModel):
    username: str
    role: str
    disabled: bool


@router.post("/login", response_model=Token, summary="Obtain JWT access token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate with username + password and receive a Bearer JWT token."""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        username=user.username,
        role=user.role,
        expires_delta=timedelta(minutes=settings.JWT_EXPIRY_MINUTES),
    )
    return Token(access_token=token)


@router.post("/refresh", response_model=Token, summary="Refresh JWT token")
async def refresh_token(current_user: UserInDB = Depends(get_current_user)):
    """Issue a fresh JWT token using the existing valid token."""
    token = create_access_token(
        username=current_user.username,
        role=current_user.role,
        expires_delta=timedelta(minutes=settings.JWT_EXPIRY_MINUTES),
    )
    return Token(access_token=token)


@router.get("/me", response_model=UserProfile, summary="Get current user profile")
async def get_me(current_user: UserInDB = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return UserProfile(
        username=current_user.username,
        role=current_user.role,
        disabled=current_user.disabled,
    )
