"""
FinSight AI — Immutable Audit Logger
Writes JSONL (one JSON object per line) to the audit log file.
Designed for SOC 2 / GDPR compliance — append-only, rotating file.
"""
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class AuditLogger:
    """Thread-safe, append-only structured JSON audit logger."""

    def __init__(self, log_path: str) -> None:
        self._log_path = Path(log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        # Configure Python logging with a rotating file handler
        self._logger = logging.getLogger("finsight.audit")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False  # Don't bubble up to root logger

        if not self._logger.handlers:
            handler = RotatingFileHandler(
                self._log_path,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def log(
        self,
        event: str,
        user: str,
        detail: dict[str, Any] | None = None,
        level: str = "INFO",
    ) -> None:
        """Write a structured audit event record."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": str(uuid.uuid4()),
            "event": event,
            "user": user,
            "level": level,
            "detail": detail or {},
        }
        with self._lock:
            self._logger.info(json.dumps(record, default=str))

    def get_recent_logs(self, n: int = 100) -> list[dict]:
        """Return the last N log entries as parsed dicts."""
        if not self._log_path.exists():
            return []
        lines = self._log_path.read_text(encoding="utf-8").splitlines()
        # Take from end, parse JSON
        result = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(result) >= n:
                break
        return list(reversed(result))

    def search_logs(
        self,
        query: str,
        field: str = "event",
        limit: int = 200,
    ) -> list[dict]:
        """Search log entries where field contains query (case-insensitive)."""
        if not self._log_path.exists():
            return []
        query_lower = query.lower()
        results: list[dict] = []
        lines = self._log_path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            value = str(entry.get(field, "")).lower()
            if query_lower in value:
                results.append(entry)
            if len(results) >= limit:
                break
        return list(reversed(results))

    def get_stats(self) -> dict:
        """Return basic stats about the audit log."""
        if not self._log_path.exists():
            return {"total_entries": 0, "log_size_bytes": 0}
        content = self._log_path.read_text(encoding="utf-8")
        lines = [l for l in content.splitlines() if l.strip()]
        return {
            "total_entries": len(lines),
            "log_size_bytes": self._log_path.stat().st_size,
            "log_path": str(self._log_path),
        }
