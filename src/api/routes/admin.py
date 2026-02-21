"""
FinSight AI — Admin Routes (admin role required)
GET  /admin/stats         — System statistics
GET  /admin/logs          — Recent audit log entries (paginated)
GET  /admin/logs/search   — Search audit logs
"""
from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_audit_logger, get_chroma_store, get_file_handler, require_role

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats", summary="System statistics (admin only)")
async def get_stats(
    current_user=Depends(require_role("admin")),
    file_handler=Depends(get_file_handler),
    chroma_store=Depends(get_chroma_store),
    audit_logger=Depends(get_audit_logger),
):
    """Return document count, chunk count, vector DB size, and audit log stats."""
    docs = file_handler.list_documents()
    vector_stats = chroma_store.get_stats()
    audit_stats = audit_logger.get_stats()

    # Breakdown by status
    status_counts: dict[str, int] = {}
    for doc in docs:
        s = doc.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "documents": {
            "total": len(docs),
            "by_status": status_counts,
        },
        "vector_store": vector_stats,
        "audit_log": audit_stats,
    }


@router.get("/logs", summary="Recent audit log entries (admin only)")
async def get_logs(
    n: int = Query(100, ge=1, le=1000, description="Number of recent entries to return"),
    current_user=Depends(require_role("admin")),
    audit_logger=Depends(get_audit_logger),
):
    """Return the last N audit log entries in reverse-chronological order."""
    logs = audit_logger.get_recent_logs(n=n)
    return {"total": len(logs), "logs": logs}


@router.get("/logs/search", summary="Search audit logs (admin only)")
async def search_logs(
    query: str = Query(..., min_length=1, description="Search term"),
    field: str = Query("event", description="Log field to search: event | user | level"),
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(require_role("admin")),
    audit_logger=Depends(get_audit_logger),
):
    """Search audit log entries by event type, username, or log level."""
    results = audit_logger.search_logs(query=query, field=field, limit=limit)
    return {"query": query, "field": field, "total": len(results), "logs": results}
