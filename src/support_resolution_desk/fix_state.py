from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FIXES_PATH = ROOT / "data" / "fixes.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_fix_state(path: Path = FIXES_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"fixes": {}}
    data = json.loads(path.read_text())
    if "fixes" not in data or not isinstance(data["fixes"], dict):
        data["fixes"] = {}
    return data


def save_fix_state(state: dict[str, Any], path: Path = FIXES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def is_fixed(fix_key: str, state: dict[str, Any] | None = None) -> bool:
    data = state if state is not None else load_fix_state()
    fix = data.get("fixes", {}).get(fix_key)
    return bool(fix and fix.get("fixed") is True)


def apply_fix(
    fix_key: str,
    source_payload: dict[str, Any],
    path: Path = FIXES_PATH,
) -> dict[str, Any]:
    state = load_fix_state(path)
    state["fixes"][fix_key] = {
        "fixed": True,
        "applied_at": utc_now(),
        "source": "argus",
        "agent": source_payload.get("agent") or source_payload.get("root_cause_agent"),
        "pattern_name": source_payload.get("pattern_name"),
        "checkpoint_id": source_payload.get("checkpoint_id") or source_payload.get("fix_id"),
        "suggested_fix": source_payload.get("suggested_fix") or source_payload.get("description"),
    }
    save_fix_state(state, path)
    return state


def reset_fixes(path: Path = FIXES_PATH) -> None:
    save_fix_state({"fixes": {}}, path)

