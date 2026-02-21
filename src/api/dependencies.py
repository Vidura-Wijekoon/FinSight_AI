"""
FinSight AI — FastAPI Dependency Injection
Provides reusable dependencies for auth, service access, and RBAC.
"""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from jose import JWTError

from src.security.auth import TokenData, UserInDB, decode_access_token, get_user

# OAuth2 scheme — token URL matches the login endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------
async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserInDB:
    """Validate JWT and return the authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token_data: TokenData = decode_access_token(token)
    except JWTError:
        raise credentials_exception

    user = get_user(token_data.username)
    if user is None or user.disabled:
        raise credentials_exception
    return user


def require_role(min_role: str):
    """
    Dependency factory that enforces a minimum role.
    Usage: Depends(require_role("admin"))
    """
    _HIERARCHY = {"viewer": 0, "analyst": 1, "admin": 2}

    async def _inner(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
        user_rank = _HIERARCHY.get(current_user.role, -1)
        required_rank = _HIERARCHY.get(min_role, 99)
        if user_rank < required_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {min_role}",
            )
        return current_user

    return _inner


# ---------------------------------------------------------------------------
# Service accessor dependencies
# ---------------------------------------------------------------------------
def get_rag_pipeline(request: Request):
    return request.app.state.rag_pipeline


def get_file_handler(request: Request):
    return request.app.state.file_handler


def get_audit_logger(request: Request):
    return request.app.state.audit_logger


def get_chroma_store(request: Request):
    return request.app.state.chroma_store
