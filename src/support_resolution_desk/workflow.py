from __future__ import annotations

import random
import uuid

from .agents import IntakeAgent, PolicyAgent, QaAgent, ResolutionAgent, RiskAgent
from .evaluators import build_evals, outcome_from
from .fix_state import is_fixed, load_fix_state
from .models import Decision, TraceEvent, WorkflowResult, utc_now


def trace_for(decision: Decision) -> TraceEvent:
    text = f"{decision.call_value}. {decision.reasoning}"
    return TraceEvent(
        agent=decision.agent,
        step_type="decision",
        outcome="success",
        created_at=utc_now(),
        latency_ms=random.randint(180, 900),
        tokens_input=random.randint(120, 420),
        tokens_output=max(20, len(text.split()) * 2),
        payload={
            "agent_reasoning": decision.reasoning,
            "tool_output": {
                "call": decision.call_value,
                "confidence": decision.confidence,
                **decision.metadata,
            },
            "model": "rules-simulated-agent-v1",
        },
    )


def apply_defects(
    ticket: dict,
    decisions: dict[str, Decision],
    defect_mode: str,
    fixed: dict | None = None,
) -> None:
    if defect_mode == "none":
        return

    state = fixed if fixed is not None else load_fix_state()
    text = ticket["message"].lower()
    issue = decisions["intake"].call_value

    if (
        defect_mode in {"mixed", "policy_miss"}
        and not is_fixed("policy_warranty_window_miss", state)
        and issue == "warranty_failure"
        and ticket["days_since_purchase"] > 30
    ):
        decisions["policy"] = Decision(
            "policy",
            "eligibility",
            "not_eligible",
            0.84,
            "Mistakenly applied the 30-day refund window to a warranty failure.",
            {"recommended_action": "deny", "defect": "warranty_window_miss"},
        )

    if (
        defect_mode in {"mixed", "risk_miss"}
        and not is_fixed("risk_escalation_language_miss", state)
        and any(term in text for term in ["chargeback", "posting", "publicly", "unsafe"])
    ):
        decisions["risk"] = Decision(
            "risk",
            "risk_level",
            "low",
            0.79,
            "Missed escalation language and treated the ticket as routine.",
            {"triggers": [], "defect": "escalation_language_miss"},
        )


def run_ticket(ticket: dict, defect_mode: str = "mixed", fixed: dict | None = None) -> WorkflowResult:
    session_id = f"support-{ticket['id'].lower()}-{uuid.uuid4().hex[:8]}"

    intake = IntakeAgent().run(ticket)
    policy = PolicyAgent().run(ticket, intake.call_value)
    risk = RiskAgent().run(ticket, policy)
    decision_map = {"intake": intake, "policy": policy, "risk": risk}
    apply_defects(ticket, decision_map, defect_mode, fixed=fixed)
    resolution = ResolutionAgent().run(ticket, decision_map["policy"], decision_map["risk"])
    decisions = [decision_map["intake"], decision_map["policy"], decision_map["risk"], resolution]
    qa = QaAgent().run(ticket, decisions)
    decisions.append(qa)

    traces = [trace_for(d) for d in decisions]
    evals = build_evals(ticket, decisions)
    status, outcome_score, satisfaction, cost, summary = outcome_from(ticket, resolution.call_value, qa.call_value)

    return WorkflowResult(
        session_id=session_id,
        ticket_id=ticket["id"],
        decisions=decisions,
        traces=traces,
        evals=evals,
        final_action=resolution.call_value,
        expected_action=ticket["expected"]["final_action"],
        outcome_status=status,
        outcome_score=outcome_score,
        satisfaction_score=satisfaction,
        cost_usd=cost,
        summary=summary,
    )
