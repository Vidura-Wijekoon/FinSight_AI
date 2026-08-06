"""
FinSight AI — Rate Limiting

Protects the two endpoints whose cost is unbounded by the caller: /query, which
triggers local 7B inference, and /documents/ingest, which encrypts and embeds a
whole document. Both are reachable by any authenticated user, so a handful of
concurrent requests is enough to saturate the host.

Limits are held in process memory. That is a deliberate fit for a single-node
deployment and a real limitation of a multi-instance one, where each replica
would enforce the limit separately. Introducing a shared store would mean an
external dependency, which the deployment model does not have.
"""
from jose import JWTError
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.security.auth import decode_access_token


def user_key(request: Request) -> str:
    """
    Rate limit per authenticated user rather than per source address.

    Address-based limiting is wrong for this system: behind a reverse proxy
    every user shares one address, so one heavy user would throttle everyone.
    The token is decoded here rather than read from a dependency because the
    limiter runs before endpoint dependencies resolve.

    Unauthenticated or unparseable requests fall back to the client address, so
    a caller cannot escape limiting by omitting a token.
    """
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            return f"user:{decode_access_token(token).username}"
        except (JWTError, AttributeError, ValueError):
            pass
    client = request.client
    return f"addr:{client.host if client else 'unknown'}"


limiter = Limiter(key_func=user_key)


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Return 429 with Retry-After, so a well-behaved client knows when to return
    rather than retrying immediately and compounding the load.
    """
    retry_after = getattr(exc, "retry_after", None) or 60
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Slow down and retry.",
            "limit": str(exc.detail) if getattr(exc, "detail", None) else None,
        },
        headers={"Retry-After": str(retry_after)},
    )
