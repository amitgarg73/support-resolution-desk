# Support Resolution Desk

This tenant simulates a customer support workflow for refund, replacement, and escalation decisions.

The goal is to give Argus a natural business workflow where an agent can complete every step but still make the wrong decision.

## Workflow

Agents:

- `intake` reads the customer ticket and classifies the issue.
- `policy` applies refund, replacement, warranty, SLA, and VIP rules.
- `risk` checks fraud, abuse, chargeback, compliance, and VIP risk.
- `resolution` makes the final action decision.
- `qa` reviews whether the final action matches policy and customer context.

Decisions:

- issue category
- policy eligibility
- risk level
- final action
- QA verdict

Outcomes:

- whether the final action matched the expected action
- whether escalation was handled correctly
- estimated customer satisfaction
- estimated cost
- policy violation flag

## Quick Start

```bash
python3 run.py --limit 10
```

Output files are written to `runs/`.

To randomly choose tickets, including both passing and failing cases:

```bash
python3 run.py --limit 10 --sample random
```

For reproducible random selection:

```bash
python3 run.py --limit 10 --sample random --seed 42
```

The default mode is `mixed`, which intentionally creates a few realistic failures so Argus has incidents and outcomes to analyze. For a clean control run:

```bash
python3 run.py --limit 10 --defect-mode none
```

## Argus Integration

The demo posts to Argus when these environment variables are set:

```bash
ARGUS_URL=https://argusobs-v2.vercel.app
ARGUS_INGEST_KEY=argus_YOUR_FLEET_KEY_HERE
```

The ingest key is bound to one Argus Agent Fleet. Argus derives the tenant and workflow from that key, so this project does not send tenant or workflow IDs.

By default, agent steps are sent as OTLP JSON traces:

```bash
python3 run.py --limit 10
```

The hybrid send path is:

- direct ingest: session open
- OTLP: agent decision spans to `/api/otlp/v1/traces`
- direct ingest: L4 evals and L5 business outcome eval
- direct ingest: session close

For the older direct trace endpoint instead of OTLP:

```bash
python3 run.py --limit 10 --trace-format direct
```

If the variables are missing, it runs in dry-run mode. Dry-run still writes a standard OTLP JSON payload to `runs/latest_otlp.json`.

## Applying Fixes From Argus

Argus should stay generic: it sends the root cause agent, failed evals, reasoning, suggested fix, and checkpoint id. This tenant maps that generic payload to local behavior changes in `fix_mapper.py`.

Show current fix state:

```bash
python3 apply_fix.py --show
```

Apply an example policy fix:

```bash
cat examples/argus_policy_fix.json | python3 apply_fix.py
```

Apply an example risk fix:

```bash
cat examples/argus_risk_fix.json | python3 apply_fix.py
```

Reset local fixes:

```bash
python3 apply_fix.py --reset
```

After a fix is applied, future `mixed` runs skip that failure mode. For example, after the policy warranty fix, warranty-window failures stop happening, while risk escalation failures can still occur.

For local webhook testing:

```bash
PYTHONPATH=src python3 -m support_resolution_desk.webhook_server
curl -X POST http://127.0.0.1:8787 \
  -H "Content-Type: application/json" \
  --data @examples/argus_policy_fix.json
```

## Why This Is Useful

This workflow creates understandable Argus narratives:

- “The policy agent missed the VIP replacement rule.”
- “The resolution agent denied a valid refund with high confidence.”
- “QA caught the problem, but the final decision still went out incorrectly.”
- “The same high-confidence denial pattern predicts low satisfaction.”
