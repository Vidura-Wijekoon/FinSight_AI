"""
FinSight AI — JWT Authentication Module
Handles user model, password hashing, and JWT token lifecycle.
Users are stored in-memory seeded from settings (production: replace with DB).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from config.settings import get_settings

# ---------------------------------------------------------------------------
# Compatibility patch: passlib 1.7.4 reads bcrypt.__version__ which was
# removed in bcrypt 4.0.  Inject a shim so passlib doesn't raise AttributeError.
# ---------------------------------------------------------------------------
import bcrypt as _bcrypt
if not hasattr(_bcrypt, "__version__"):
    _bcrypt.__version__ = "4.0.0"

settings = get_settings()

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# User models
# ---------------------------------------------------------------------------
class UserInDB(BaseModel):
    username: str
    hashed_password: str
    role: str = "viewer"   # admin | analyst | viewer
    disabled: bool = False


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: str
    role: str


# ---------------------------------------------------------------------------
# In-memory user store (seed admin from settings)
# ---------------------------------------------------------------------------
_USERS_DB: dict[str, UserInDB] = {}


def _seed_admin() -> None:
    """Create the admin user from settings if not already present."""
    if settings.ADMIN_USERNAME not in _USERS_DB:
        _USERS_DB[settings.ADMIN_USERNAME] = UserInDB(
            username=settings.ADMIN_USERNAME,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            role="admin",
        )


# Seed on module import
_seed_admin()


def get_user(username: str) -> Optional[UserInDB]:
    return _USERS_DB.get(username)


def add_user(username: str, password: str, role: str = "viewer") -> UserInDB:
    """Add a new user to the in-memory store."""
    user = UserInDB(
        username=username,
        hashed_password=hash_password(password),
        role=role,
    )
    _USERS_DB[username] = user
    return user


def authenticate_user(username: str, password: str) -> Optional[UserInDB]:
    """Validate credentials; return UserInDB or None."""
    user = get_user(username)
    if user is None or user.disabled:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ---------------------------------------------------------------------------
# JWT token lifecycle
# ---------------------------------------------------------------------------
def create_access_token(username: str, role: str, expires_delta: Optional[timedelta] = None) -> str:
    """Encode a signed JWT containing username and role."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRY_MINUTES)
    )
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> TokenData:
    """Decode and validate a JWT; raises JWTError on invalid/expired tokens."""
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    username: str = payload.get("sub")
    role: str = payload.get("role", "viewer")
    if username is None:
        raise JWTError("Missing 'sub' claim in token")
    return TokenData(username=username, role=role)
