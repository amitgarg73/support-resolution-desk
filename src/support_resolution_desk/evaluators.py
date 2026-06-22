from __future__ import annotations

from .models import Decision, EvalResult


def score_match(actual: str, expected: str) -> float:
    return 1.0 if actual == expected else 0.0


def build_evals(ticket: dict, decisions: list[Decision]) -> list[EvalResult]:
    expected = ticket["expected"]
    by_agent = {d.agent: d for d in decisions}

    checks = [
        ("intake", "issue_classification_correct", by_agent["intake"].call_value, expected["issue_category"]),
        ("policy", "policy_eligibility_correct", by_agent["policy"].call_value, "eligible" if expected["policy_eligible"] else "not_eligible"),
        ("risk", "risk_level_correct", by_agent["risk"].call_value, expected["risk_level"]),
        ("resolution", "final_action_correct", by_agent["resolution"].call_value, expected["final_action"]),
        ("qa", "qa_caught_policy_mismatch", by_agent["qa"].call_value, "approved" if by_agent["resolution"].call_value == expected["final_action"] else "rejected"),
    ]

    evals: list[EvalResult] = []
    for agent, name, actual, exp in checks:
        score = score_match(actual, exp)
        evals.append(EvalResult(
            agent=agent,
            eval_name=name,
            layer=4,
            score=score,
            passed=score >= 0.7,
            threshold=0.7,
            reasoning=f"{agent} produced {actual}; expected {exp}.",
        ))
    return evals


def outcome_from(ticket: dict, final_action: str, qa_verdict: str) -> tuple[str, float, float, float, str]:
    expected = ticket["expected"]
    correct_action = final_action == expected["final_action"]
    escalation_ok = (final_action == "escalate") == bool(expected["requires_escalation"]) or final_action == expected["final_action"]

    if correct_action:
        status = "successful"
        score = 1.0
    elif escalation_ok and qa_verdict == "approved":
        status = "partial"
        score = 0.65
    else:
        status = "failed"
        score = 0.15

    base_cost = 8.0
    action_cost = {"refund": ticket["order_value"], "replace": ticket["order_value"] * 0.55, "escalate": 35.0, "deny": 3.0}.get(final_action, 5.0)
    cost = round(base_cost + float(action_cost), 2)

    if status == "successful":
        satisfaction = 0.88
    elif status == "partial":
        satisfaction = 0.58
    else:
        satisfaction = 0.18 if ticket["customer_tier"] == "vip" else 0.28

    summary = f"Final action {final_action}; expected {expected['final_action']}; outcome {status}."
    return status, score, satisfaction, cost, summary

