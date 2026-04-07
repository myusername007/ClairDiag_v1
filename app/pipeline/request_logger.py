# ── Request Logger — ClairDiag (п.18) ────────────────────────────────────────
import logging
import json
from datetime import datetime, timezone

_log = logging.getLogger("clairdiag.requests")


def log_request(
    input_text: str,
    normalized: list[str],
    parsed: list[str],
    confidence: str,
    decision: str,
    session_id: str | None = None,
    context: dict | None = None,
    trace_id: str = "",
) -> None:
    entry = {
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "input":      input_text[:200],
        "normalized": normalized,
        "parsed":     parsed,
        "context":    {k: v for k, v in (context or {}).items()
                       if k != "flags" and v and v is not False},
        "confidence": confidence,
        "decision":   decision,
        "trace_id":   trace_id,
        "session_id": session_id,
    }
    _log.info(json.dumps(entry, ensure_ascii=False))