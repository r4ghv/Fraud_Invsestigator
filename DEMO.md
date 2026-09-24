# Demo script — 3 to 5 minutes, end to end

Record the screen with audio (light voiceover) or silent with these beats on screen.
Everything below is already running or runs on first try — **rehearse once, then record.**

## Pre-flight (1 min before recording)

```bash
cd ~/Projects/hh_goa
# 1. UI up:
.venv/bin/python fraud_agent/ui/serve.py --port 8111   # leave running
# 2. Tests (proof it's real):
.venv/bin/python -m pytest fraud_agent/tests/ -q        # → 82 passed
```

Open in the browser: `http://127.0.0.1:8111/` (starts on HHG-004, an undocumented
fraud case). Have a terminal ready.

## The takes

### 0:00–0:30 — The trigger
Show `fraud_agent/data/case_pack.csv` header row: `case_id, flagged_txn_id,
trigger_type(risk_score|customer_report|analyst_request), risk_score…`.
**Say:** "Three trigger types, twenty benchmark cases, one graph of 590k transactions
behind them."

### 0:30–1:15 — Investigate (terminal)
Run one case through the agent (fast — graph is loaded):

```bash
.venv/bin/python -m fraud_agent.src.agent --limit 1 --out /tmp/demo
```

Scroll the printed result: verdict, pattern, probability, final actions.
**Say:** "Five detectors, two guards, thresholds all read from policy.yaml, zero LLM
tokens. Decisions are deterministic — this rerun produces the same answer."

### 1:15–2:30 — The case in the UI (main segment)
Browser on `http://127.0.0.1:8111/`. Click through, narrating:

1. **Left rail** — 20 cases with verdict chips. "Fraud red, uncertain amber."
2. **HHG-004 header** — status/verdict/pattern chips + green **on graph: HHG-004**.
   "This case exists as a vertex on Savanna right now."
3. **"New pattern discovered" banner** — the undocumented pattern description with
   customer count, day span, amount band. "All five detectors missed; the device-sharing
   traversal didn't."
4. **Uncertainty panel** — probability meter, stop reason, exposure, prior cases
   retrieved (case memory).
5. **Recommendation before evidence** vs **after evidence** — "Before: verify, step-up,
   open a case. After the customer denial: block, file, monitor connected cards — each
   with its approval route: auto, L1, L2."
6. **Evidence panel** — three claims with `source: graph` and query refs. "Cited by
   query name and parameters, not vibes."
7. **Case progression timeline** — trigger → investigate → evidence → decision →
   **case written to graph**.
8. **Graph view** — live edges: FraudCase —CASE_ON→ Card, Txn —FROM_DEVICE→
   DeviceProfile. "Fetched live from REST++ while you watch."
9. Click **HHG-009** or **HHG-016** — SAR panel with the 6–12 sentence narrative.
   "Fired by policy: exposure over threshold or shared origin. Route L2."

### 2:30–3:15 — It's on the graph (terminal)

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$TIGERGRAPH_HOST/restpp/graph/Fraud/vertices/FraudCase/HHG-004" | python3 -m json.tool
```

(or just point at the UI's green chip + graph panel if curl auth is fiddly on camera).
Optional: rerun the full 20-case batch (≈35 s) and show all greens:

```bash
.venv/bin/python -m fraud_agent.src.agent | tail -3
```

### 3:15–4:00 — It's tested and honest
Terminal: `pytest -q` → **82 passed**. Mention: pyflakes-clean, validator runs before
every write, every threshold grep-proven to come from `policy.yaml`, `tokens: 0` in
every answer file.

### 4:00–4:30 — Close
Back to the UI, wide shot of the dashboard.
**Say:** "Policy-driven, graph-native, deterministic where it matters, and every case
it closes becomes memory for the next one — written back to the graph."

## Cut list (if you run long)
- Drop the pytest take (0:30).
- Drop case re-run in 2:30.
- Keep UI segment intact — it carries the story.

## After recording
- Upload, set as **unlisted/public**, grab URL.
- Put URL into `BLOG.md` header + `SOCIAL.md` placeholders.
- Publish blog → paste blog URL into `SOCIAL.md` → post on X + LinkedIn, tag
  `@TigerGraphDB`.
