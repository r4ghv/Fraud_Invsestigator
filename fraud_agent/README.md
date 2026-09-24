# Fraud Agent — deterministic-first

Target: TigerGraph HHGOA Agentic Fraud Investigation.

Rule: ALL policy, risk, NBA, SAR, and approval decisions are deterministic code.
LLM is allowed ONLY for phrasing explanations, never for decisions (`tokens: 0`
in every answer file).

## Layout
- `policies/policy.yaml` — versioned YAML, the only source of truth for thresholds
- `src/policy_engine.py` — deterministic R1–R10 evaluator, no LLM calls
- `src/pattern_detectors.py` — five pattern detectors (pure functions over graph windows)
- `src/agent.py` — the 8-step investigation loop
- `src/retrieval.py` — case memory: prior-case similarity (graph ClosedCase)
- `src/data_loader.py` — window/card/device access over the loaded dataset
- `src/case_writer.py` — writes each finished case to the graph (fail-loud)
- `src/graph_queries.py` — installs the investigation queries on Savanna
- `src/validator.py` — answer-format validator (runs before every file/graph write)
- `src/explainer.py` — template explanation, optional LLM rephrase (disabled)
- `src/tigergraph/` — `schema.gsql`, `load.gsql`, `queries.gsql`
- `ui/` — analyst console (`serve.py` + `index.html`)
- `cases/` — the 20 benchmark answer files
- `tests/` — 82 tests, synthetic rows only (no big CSVs)

## Quickstart
```bash
python -m venv .venv && .venv/bin/pip install pyTigerGraph requests pyyaml pytest pyflakes
.venv/bin/python -m pytest fraud_agent/tests/ -q          # 82 passed
.venv/bin/python -m fraud_agent.src.agent                 # regenerate + validate 20 answers
.venv/bin/python fraud_agent/ui/serve.py --port 8111      # analyst console
```
The agent run needs `fraud_agent/.env` (Savanna creds) and the loaded graph; without
creds it still produces answers but leaves `written_to_graph: false` and prints a warning.

## Analyst console (UI)
`http://127.0.0.1:8111/` — case rail with verdict chips, case-progression timeline
(trigger → investigate → evidence → decision → written-to-graph), evidence claims with
query refs, uncertainty meter, next-best-actions **before and after evidence** with
approval routes (auto/L1/L2), SAR narrative, and a **live graph panel** that fetches
`CASE_ON` / `FROM_DEVICE` / `BILLED_IN` edges from REST++ on every view.

## Graph, queries, algorithms
Graph `Fraud` on Savanna: `Customer · Card · Txn · DeviceProfile · BillingRegion ·
ClosedCase · FraudCase · EmailDomain` (590,742 txns loaded).

Installed GSQL (`src/tigergraph/queries.gsql`, installer: `python -m
fraud_agent.src.graph_queries --install`):
- `flagged_transaction(txn_id)` — alert attributes from the graph
- `card_window(card_id, t, days)` — temporal traversal `Card → MADE → Txn`
- `device_neighbors(profile_id)` — reverse traversal to sharing customers
- `connected_ring(card_id, t, days)` — multi-hop ring expansion (device-sharing
  relationship analysis behind connected-card monitoring)
- `ring_reach(txn_id)` — 4-layer BFS graph algorithm: seeded from the flagged txn,
  each SELECT is one frontier, so the layer a vertex lands in *is* its shortest-hop
  distance (txn → device → other txns → cards → customers)

Every case is written back as a `FraudCase` vertex + `CASE_ON → Card` edge — case
memory that `src/retrieval.py` feeds into the next investigation.

## GraphRAG
Evidence is retrieved as context, never as raw tables:
1. **graph evidence** — the five queries above, scoped to the case,
2. **prior-case memory** — `retrieval.similar()` over historical closed cases,
3. **documents** — `policy.yaml` rules and typology mechanics become the reason
   text on every recommended action.

## TigerGraph MCP
`tigergraph-mcp` (69 tools) is configured in `opencode.json` for this workspace:

```bash
.venv/bin/pip install tigergraph-mcp
cp fraud_agent/mcp.env.example fraud_agent/mcp.env   # fill TG_* values (gitignored)
```

Verified live: `tigergraph__list_graphs → ["Fraud"]`,
`tigergraph__get_vertex_count(FraudCase) → 20`. OpenCode exposes the tools as
`tigergraph_*` in any session (`opencode mcp list` shows the connection).

## Wiring Savanna / dataset
1. `fraud_agent/.env`: `TIGERGRAPH_HOST`, `TIGERGRAPH_SECRET` (see `.env.example`).
2. Load schema + data: `python -m fraud_agent.src.load_tigergraph --run`.
3. Install queries: `python -m fraud_agent.src.graph_queries --install`.
4. Regenerate answers: `python -m fraud_agent.src.agent` (writes all 20 cases to
   the graph; aborts loudly on validation or graph-write failure).

## Submission deliverables
- 20 answer files — `cases/HHG-001.json` … `HHG-020.json` (validated, on graph)
- Blog — [`../BLOG.md`](../BLOG.md)
- Demo script (3–5 min) — [`../DEMO.md`](../DEMO.md)
- Social copy (X/LinkedIn, tags `@TigerGraphDB`) — [`../SOCIAL.md`](../SOCIAL.md)
