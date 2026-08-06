"""
FinSight AI — Health and Readiness Routes

Two endpoints with deliberately different contracts:

  GET /health  liveness  — is the process running? No dependency checks, so an
                           orchestrator does not restart a healthy process
                           merely because a dependency is briefly unavailable.
  GET /ready   readiness — can this instance serve a query right now? Checks
                           every dependency the query path needs, so a failing
                           dependency removes the instance from a load balancer
                           without killing it.

Neither requires authentication: a probe runs before credentials exist, and
neither returns information an unauthenticated caller could not obtain by
sending a request and observing the failure.
"""
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request, Response, status

router = APIRouter(tags=["Health"])

# A readiness probe must answer faster than the interval it runs on. Ollama is
# the slowest check and the most likely to hang, so it is bounded explicitly.
_DEPENDENCY_TIMEOUT_SECONDS = 3.0


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """Return 200 whenever the process is running. Checks nothing else."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def ready(request: Request, response: Response) -> dict[str, Any]:
    """
    Return 200 only if every dependency of the query path is usable, otherwise
    503 with a per-dependency breakdown so the failing component is named
    rather than inferred.
    """
    state = request.app.state
    checks: dict[str, dict[str, Any]] = {}

    # Each check is passed as a factory, not an awaitable, so that resolving the
    # service off app.state happens inside _check's try block. A service missing
    # because startup did not complete is exactly the condition this endpoint
    # exists to report, and it must produce a 503 rather than a 500.
    checks["vector_store"] = await _check(
        lambda: asyncio.to_thread(state.chroma_store.heartbeat)
    )
    checks["embedding_model"] = await _check(
        lambda: asyncio.to_thread(lambda: state.embedding_service.dimension)
    )
    checks["llm"] = await _check(lambda: state.llm_service.health())

    ready_now = all(c["ok"] for c in checks.values())
    if not ready_now:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {"status": "ready" if ready_now else "not_ready", "checks": checks}


async def _check(factory: Callable[[], Awaitable[Any]]) -> dict[str, Any]:
    """
    Run one dependency check, converting any failure into a reported status.

    A readiness probe that raises is a probe that tells the operator nothing, so
    every exception type is caught here on purpose. The exception text is
    returned because these endpoints expose no secrets and a probe is far more
    useful when it says why.
    """
    try:
        result = await asyncio.wait_for(factory(), timeout=_DEPENDENCY_TIMEOUT_SECONDS)
    except TimeoutError:
        return {"ok": False, "error": f"timed out after {_DEPENDENCY_TIMEOUT_SECONDS}s"}
    except AttributeError:
        # Service missing from app.state — startup did not complete.
        return {"ok": False, "error": "not initialised"}
    except Exception as exc:  # noqa: BLE001 — see docstring
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "detail": result if isinstance(result, int) else None}
