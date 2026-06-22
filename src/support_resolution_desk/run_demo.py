from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from .argus_client import ArgusClient
from .fix_state import load_fix_state
from .workflow import run_ticket


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "tickets.json"
RUNS = ROOT / "runs"


def load_tickets() -> list[dict]:
    return json.loads(DATA.read_text())


def select_tickets(tickets: list[dict], ticket_id: str, limit: int, sample: str, seed: int | None) -> list[dict]:
    if ticket_id:
        return [t for t in tickets if t["id"] == ticket_id]

    if sample == "random":
        rng = random.Random(seed)
        pool = tickets[:]
        rng.shuffle(pool)
        return pool[:limit]

    return tickets[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run support triage sessions and optionally send them to Argus.")
    parser.add_argument("--limit", type=int, default=10, help="Number of tickets to process.")
    parser.add_argument("--ticket-id", default="", help="Run a single ticket by id.")
    parser.add_argument("--sample", default="sequential", choices=["sequential", "random"], help="How to choose tickets when --ticket-id is omitted.")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed for reproducible sampling.")
    parser.add_argument("--defect-mode", default="mixed", choices=["mixed", "none", "policy_miss", "risk_miss"], help="Simulate realistic agent mistakes.")
    parser.add_argument("--trace-format", default="otlp", choices=["otlp", "direct"], help="How to send agent traces when Argus is enabled.")
    parser.add_argument("--no-send", action="store_true", help="Never send to Argus, even if env vars are set.")
    args = parser.parse_args()

    tickets = select_tickets(load_tickets(), args.ticket_id, args.limit, args.sample, args.seed)

    RUNS.mkdir(exist_ok=True)
    client = ArgusClient()
    if args.no_send:
        client.enabled = False

    output_path = RUNS / "latest.jsonl"
    otlp_path = RUNS / "latest_otlp.json"
    successes = 0
    otlp_spans: list[dict] = []
    fixed = load_fix_state()
    with output_path.open("w") as out:
        for ticket in tickets:
            result = run_ticket(ticket, defect_mode=args.defect_mode, fixed=fixed)
            otlp_spans.extend(client.otlp_payload(result)["resourceSpans"][0]["scopeSpans"][0]["spans"])
            if client.enabled:
                client.send(result, traces=args.trace_format)
            out.write(json.dumps(client.serialize(result)) + "\n")
            successes += 1
            print(f"{result.ticket_id}: {result.final_action} expected={result.expected_action} outcome={result.outcome_status}")

    otlp_path.write_text(json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": otlp_spans}]}]}, indent=2))

    mode = f"sent to Argus ({args.trace_format} traces)" if client.enabled else "dry-run"
    print(f"\nProcessed {successes} ticket sessions ({mode}).")
    print(f"Saved local artifact: {output_path}")
    print(f"Saved OTLP artifact: {otlp_path}")


if __name__ == "__main__":
    main()
