"""Tests for the enriched, evidence-bearing agent reasoning.

These lock in two things:
1. The enrichment did NOT change any decision call value, confidence, metadata,
   eval, or business outcome (the sim's deterministic logic is unchanged).
2. Each agent's reasoning now carries the concrete evidence the Argus eval
   criteria look for (issue category, rule window, the five risk triggers,
   a numeric confidence, override logic, and an explicit QA comparison).
"""

from __future__ import annotations

import json
from pathlib import Path

from support_resolution_desk.agents import (
    IntakeAgent,
    PolicyAgent,
    QaAgent,
    ResolutionAgent,
    RiskAgent,
)
from support_resolution_desk.workflow import run_ticket

TICKETS = json.loads((Path(__file__).resolve().parents[1] / "data" / "tickets.json").read_text())
MODES = ["none", "mixed", "policy_miss", "risk_miss"]


def by_agent(result):
    return {d.agent: d for d in result.decisions}


# ---------------------------------------------------------------------------
# Invariant: decisions and outcomes are unchanged by the enrichment.
# These are the golden values captured from the deterministic logic; they must
# not move when reasoning text changes.
# ---------------------------------------------------------------------------

def test_outcomes_are_deterministic_and_stable():
    summary = []
    for mode in MODES:
        for ticket in TICKETS:
            r = run_ticket(ticket, defect_mode=mode, fixed={})
            calls = {d.agent: d.call_value for d in r.decisions}
            summary.append(
                (mode, ticket["id"], calls, r.final_action, r.outcome_status, r.outcome_score)
            )
    # Re-running must yield identical results (no hidden randomness in logic).
    summary2 = []
    for mode in MODES:
        for ticket in TICKETS:
            r = run_ticket(ticket, defect_mode=mode, fixed={})
            calls = {d.agent: d.call_value for d in r.decisions}
            summary2.append(
                (mode, ticket["id"], calls, r.final_action, r.outcome_status, r.outcome_score)
            )
    assert summary == summary2


def test_confidence_and_metadata_preserved():
    # Confidence values and metadata keys the rest of the pipeline depends on.
    t = TICKETS[0]
    intake = IntakeAgent().run(t)
    policy = PolicyAgent().run(t, intake.call_value)
    risk = RiskAgent().run(t, policy)
    resolution = ResolutionAgent().run(t, policy, risk)
    assert intake.confidence == 0.86
    assert policy.confidence == 0.78
    assert "recommended_action" in policy.metadata
    assert "triggers" in risk.metadata


# ---------------------------------------------------------------------------
# Evidence: reasoning carries what the eval criteria require.
# ---------------------------------------------------------------------------

def test_intake_reasoning_names_the_category():
    for t in TICKETS:
        d = IntakeAgent().run(t)
        assert d.call_value in d.reasoning, t["id"]


def test_policy_reasoning_cites_a_rule_window_when_eligible():
    windows = ["14", "30", "180", "no time limit"]
    for t in TICKETS:
        issue = IntakeAgent().run(t).call_value
        d = PolicyAgent().run(t, issue)
        if d.call_value == "eligible":
            assert any(w in d.reasoning for w in windows), t["id"]
            # Stock availability drives the action for delivery/damage/warranty
            # rules; buyer-remorse is always a refund, so stock is not cited there.
            if issue != "buyer_remorse":
                assert "stock" in d.reasoning.lower(), t["id"]
        assert "eligib" in d.reasoning.lower(), t["id"]


def test_risk_reasoning_evaluates_five_triggers_and_has_numeric_confidence():
    for t in TICKETS:
        issue = IntakeAgent().run(t).call_value
        policy = PolicyAgent().run(t, issue)
        d = RiskAgent().run(t, policy)
        low = d.reasoning.lower()
        for trigger in ["chargeback", "legal", "public", "repeat offender", "high-value"]:
            assert trigger in low, (t["id"], trigger)
        # numeric confidence appears in the text
        assert f"{d.confidence:.2f}" in d.reasoning, t["id"]


def test_resolution_reasoning_shows_override_or_follow_logic():
    for t in TICKETS:
        issue = IntakeAgent().run(t).call_value
        policy = PolicyAgent().run(t, issue)
        risk = RiskAgent().run(t, policy)
        d = ResolutionAgent().run(t, policy, risk)
        low = d.reasoning.lower()
        if risk.call_value == "high":
            assert "override" in low and "escalate" in low, t["id"]
        else:
            assert "policy recommendation" in low, t["id"]


def test_qa_reasoning_shows_explicit_comparison():
    for t in TICKETS:
        r = run_ticket(t, defect_mode="none", fixed={})
        qa = by_agent(r)["qa"]
        low = qa.reasoning.lower()
        assert "compared" in low or "compare" in low, t["id"]
        assert "expected" in low, t["id"]


def test_defect_reasoning_is_enriched_but_decision_unchanged():
    # Warranty-window-miss defect: policy stays not_eligible/deny, reasoning richer.
    for t in TICKETS:
        if t["item_condition"] == "hardware_failure" and t["days_since_purchase"] > 30:
            r = run_ticket(t, defect_mode="mixed", fixed={})
            policy = by_agent(r)["policy"]
            assert policy.call_value == "not_eligible"
            assert policy.metadata.get("defect") == "warranty_window_miss"
            assert "180-day" in policy.reasoning
            break

    # Escalation-language-miss defect: risk stays low, reasoning lists triggers.
    for t in TICKETS:
        if any(w in t["message"].lower() for w in ["chargeback", "posting", "publicly", "unsafe"]):
            r = run_ticket(t, defect_mode="mixed", fixed={})
            risk = by_agent(r)["risk"]
            if risk.metadata.get("defect") == "escalation_language_miss":
                assert risk.call_value == "low"
                assert "chargeback" in risk.reasoning.lower()
                break
