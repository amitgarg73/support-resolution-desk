from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .fix_state import apply_fix, load_fix_state, reset_fixes


FIX_POLICY_WARRANTY = "policy_warranty_window_miss"
FIX_RISK_ESCALATION = "risk_escalation_language_miss"


def text_blob(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("agent", "root_cause_agent", "pattern_name", "root_cause", "suggested_fix", "description"):
        value = payload.get(key)
        if value is not None:
            parts.append(str(value))
    for item in payload.get("failed_evals", []) or []:
        if isinstance(item, dict):
            for key in ("agent", "eval_name", "reasoning"):
                value = item.get(key)
                if value is not None:
                    parts.append(str(value))
    return " ".join(parts).lower()


def map_argus_fix(payload: dict[str, Any]) -> str | None:
    """Map a generic Argus fix payload to a local support-desk fix key.

    Argus remains generic: it sends root cause agent, failed evals, reasoning,
    and suggested fix text. This adapter owns the domain-specific translation.
    """
    blob = text_blob(payload)
    agent = str(payload.get("agent") or payload.get("root_cause_agent") or "").lower()

    if "policy" in agent or "policy" in blob:
        if any(term in blob for term in ("warranty", "eligible", "eligibility", "30-day", "180-day", "hardware")):
            return FIX_POLICY_WARRANTY

    if "risk" in agent or "risk" in blob:
        if any(term in blob for term in ("chargeback", "public", "publicly", "legal", "unsafe", "escalation")):
            return FIX_RISK_ESCALATION

    return None


def apply_argus_payload(payload: dict[str, Any]) -> str | None:
    fix_key = map_argus_fix(payload)
    if not fix_key:
        return None
    apply_fix(fix_key, payload)
    return fix_key


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply an Argus fix webhook payload to local support-desk fix state.")
    parser.add_argument("--payload", help="JSON payload string. If omitted, reads stdin.")
    parser.add_argument("--show", action="store_true", help="Print current fix state.")
    parser.add_argument("--reset", action="store_true", help="Clear all local fixes.")
    args = parser.parse_args()

    if args.reset:
        reset_fixes()
        print("Reset local fix state.")
        return

    if args.show:
        print(json.dumps(load_fix_state(), indent=2, sort_keys=True))
        return

    raw = args.payload if args.payload else sys.stdin.read()
    payload = json.loads(raw)
    fix_key = apply_argus_payload(payload)
    if not fix_key:
        # No matching local fix is a clean no-op, not a failure: Argus dispatched a
        # valid payload that this tenant has no mapping for. Exit 0 so the run stays
        # green; a red run should mean a real apply error, not "nothing matched".
        print("No local fix mapping matched this Argus payload; nothing to apply.")
        return
    print(f"Applied local fix: {fix_key}")


if __name__ == "__main__":
    main()

