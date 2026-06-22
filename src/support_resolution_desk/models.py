from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Decision:
    agent: str
    decision_type: str
    call_value: str
    confidence: float
    reasoning: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceEvent:
    agent: str
    step_type: str
    outcome: str
    created_at: str
    latency_ms: int
    tokens_input: int
    tokens_output: int
    payload: dict[str, Any]


@dataclass
class EvalResult:
    agent: str
    eval_name: str
    layer: int
    score: float
    passed: bool
    threshold: float
    reasoning: str


@dataclass
class WorkflowResult:
    session_id: str
    ticket_id: str
    decisions: list[Decision]
    traces: list[TraceEvent]
    evals: list[EvalResult]
    final_action: str
    expected_action: str
    outcome_status: str
    outcome_score: float
    satisfaction_score: float
    cost_usd: float
    summary: str

