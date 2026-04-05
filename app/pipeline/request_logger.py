# ── Request Logger — ClairDiag (п.14 ТЗ) ────────────────────────────────────
# Логирует каждый запрос: input → normalized → parsed → confidence → decision
# Использование: вызвать log_request() в routes.py после получения result

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
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input": input_text[:200],
        "normalized": normalized,
        "parsed": parsed,
        "confidence": confidence,
        "decision": decision,
        "session_id": session_id,
    }
    _log.info(json.dumps(entry, ensure_ascii=False))