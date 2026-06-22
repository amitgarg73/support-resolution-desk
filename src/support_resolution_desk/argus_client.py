from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict
from typing import Any

from .models import EvalResult, TraceEvent, WorkflowResult


class ArgusClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("ARGUS_URL", "").rstrip("/")
        # ARGUS_API_KEY is the name Argus's Connection panel uses; keep
        # ARGUS_INGEST_KEY as a fallback for older configs.
        self.ingest_key = os.getenv("ARGUS_API_KEY") or os.getenv("ARGUS_INGEST_KEY", "")
        self.enabled = bool(self.base_url and self.ingest_key)

    def _post(self, path: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "x-argus-key": self.ingest_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                res.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Argus POST {path} failed: {exc.code} {detail}") from exc

    def _sid(self, result: WorkflowResult) -> str:
        # Argus session id must be a UUID. Derive a stable one from the readable
        # session id (deterministic, so re-runs are idempotent); the readable id is
        # sent as external_id and metadata for display/joins.
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"support_resolution_desk:{result.session_id}"))

    def open_session(self, result: WorkflowResult) -> None:
        self._post("/api/ingest/session/open", {
            "session_id": self._sid(result),
            "external_id": result.session_id,
            "session_type": "support_refund_triage",
            "metadata": {"ticket_id": result.ticket_id, "external_id": result.session_id, "tenant_demo": "support_resolution_desk"},
        })

    def trace(self, result: WorkflowResult, event: TraceEvent) -> None:
        self._post("/api/ingest/trace", {
            "session_id": self._sid(result),
            "agent": event.agent,
            "step_type": event.step_type,
            "outcome": event.outcome,
            "latency_ms": event.latency_ms,
            "tokens_input": event.tokens_input,
            "tokens_output": event.tokens_output,
            "payload": event.payload,
        })

    def otlp_payload(self, result: WorkflowResult) -> dict[str, Any]:
        base = time.time_ns()
        sid = self._sid(result)
        trace_id = sid.replace("-", "")[:32].ljust(32, "0")
        spans: list[dict[str, Any]] = []

        for index, event in enumerate(result.traces, start=1):
            start_ns = base + index * 10_000_000
            end_ns = start_ns + max(event.latency_ms, 1) * 1_000_000
            tool_output = event.payload.get("tool_output") if isinstance(event.payload, dict) else None
            tool_input = event.payload.get("tool_input") if isinstance(event.payload, dict) else None
            reasoning = event.payload.get("agent_reasoning") if isinstance(event.payload, dict) else None
            model = event.payload.get("model") if isinstance(event.payload, dict) else None

            attrs = [
                {"key": "argus.session_id", "value": {"stringValue": sid}},
                {"key": "argus.agent", "value": {"stringValue": event.agent}},
                {"key": "argus.step_type", "value": {"stringValue": event.step_type}},
                {"key": "llm.token_count.input", "value": {"intValue": event.tokens_input}},
                {"key": "llm.token_count.output", "value": {"intValue": event.tokens_output}},
                {"key": "argus.sequence", "value": {"intValue": index}},
            ]
            if reasoning is not None:
                attrs.append({"key": "argus.agent_reasoning", "value": {"stringValue": str(reasoning)}})
            if tool_input is not None:
                attrs.append({"key": "argus.tool_input", "value": {"stringValue": json.dumps(tool_input)}})
            if tool_output is not None:
                attrs.append({"key": "argus.tool_output", "value": {"stringValue": json.dumps(tool_output)}})
            if model is not None:
                attrs.append({"key": "argus.model", "value": {"stringValue": str(model)}})

            spans.append({
                "traceId": trace_id,
                "spanId": f"{index:016x}",
                "parentSpanId": f"{index - 1:016x}" if index > 1 else "",
                "name": f"{event.agent}:{event.step_type}",
                "startTimeUnixNano": str(start_ns),
                "endTimeUnixNano": str(end_ns),
                "status": {"code": 1 if event.outcome == "success" else 2},
                "attributes": attrs,
            })

        return {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}

    def send_otlp_traces(self, result: WorkflowResult) -> None:
        self._post("/api/otlp/v1/traces", self.otlp_payload(result))

    def eval(self, result: WorkflowResult, item: EvalResult) -> None:
        self._post("/api/ingest/eval", {
            "session_id": self._sid(result),
            "agent": item.agent,
            "eval_name": item.eval_name,
            "layer": item.layer,
            "score": item.score,
            "passed": item.passed,
            "threshold": item.threshold,
            "detail": {"reasoning": item.reasoning},
        })

    def outcome(self, result: WorkflowResult) -> None:
        self._post("/api/ingest/eval", {
            "session_id": self._sid(result),
            "agent": "workflow",
            "eval_name": "business_outcome",
            "layer": 5,
            "score": result.outcome_score,
            "passed": result.outcome_score >= 0.7,
            "threshold": 0.7,
            "detail": {
                "status": result.outcome_status,
                "satisfaction_score": result.satisfaction_score,
                "cost_usd": result.cost_usd,
                "reasoning": result.summary,
            },
        })

    def close_session(self, result: WorkflowResult) -> None:
        quality = sum(e.score for e in result.evals) / len(result.evals) if result.evals else None
        self._post("/api/ingest/session/close", {
            "session_id": self._sid(result),
            "result_summary": result.summary,
            "terminal_reason": "completed" if result.outcome_status != "failed" else "business_failure",
            "quality_score": quality,
            "total_cost_usd": result.cost_usd,
            "metadata": {
                "ticket_id": result.ticket_id,
                "final_action": result.final_action,
                "expected_action": result.expected_action,
                "outcome_status": result.outcome_status,
            },
        })

    def send(self, result: WorkflowResult, traces: str = "direct") -> None:
        self.open_session(result)
        if traces == "otlp":
            self.send_otlp_traces(result)
        else:
            for trace in result.traces:
                self.trace(result, trace)
        for item in result.evals:
            self.eval(result, item)
        self.outcome(result)
        self.close_session(result)

    def serialize(self, result: WorkflowResult) -> dict[str, Any]:
        return asdict(result)
