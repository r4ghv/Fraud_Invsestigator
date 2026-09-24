# How We Built a Policy-Driven Fraud Investigation Agent on TigerGraph (Framework-Free)

> Submission for the TigerGraph HHGOA hackathon. Repo: https://github.com/r4ghv/Fraud_Invsestigator
> Demo video: _[3–5 min end-to-end walkthrough — link]_ · Dashboard screenshots: `fraud_agent/ui/`

## What we built

An agentic fraud investigation agent that takes a raw alert — a risk score, a customer
report, or an analyst request — and drives the full investigation loop on top of a
590,742-transaction graph in TigerGraph Savanna:

**trigger → investigate → gather evidence → assess uncertainty → request more evidence
(if needed) → next best actions → explain → write the case back to the graph.**

It produces the hackathon's 20 benchmark case files end to end, each containing the case
record, evidence claims, findings, decisions, actions, a before/after next-best-action
comparison with approval routes, and a 6–12 sentence SAR narrative when policy requires
one. Every case is then written back to the graph as a `FraudCase` vertex linked to the
card by a `CASE_ON` edge, so the next investigation can retrieve it as case memory.

Two numbers define the design:

- **`tokens: 0`** — an LLM never makes a decision. Every verdict, threshold, route, and
  SAR trigger is computed deterministically. The template explainer has an optional
  LLM-rephrase hook that is never enabled in submissions.
- **82 tests, pyflakes-clean** — detectors, guards, policy rules, answer validation,
  retrieval, and golden-case regressions run against synthetic rows only.

## Architecture

```
case_pack.csv (trigger: risk score | customer report | analyst)
        │
        ▼
┌─ agent.py — the 8-step loop (custom, framework-free) ───────────────┐
│ 1 store.flagged()          → anchor txn, no look-ahead (H4)         │
│ 2 card window ±60d         → 5 detectors on rows ≤ flagged ts       │
│ 3 guards                   → R7 monthly-rhythm, trip-guard drop     │
│ 4 fraud_probability        → 0.7·detectors + 0.3·bank, guards first │
│ 5 policy_engine R1–R10     → actions + approval routes (auto/L1/L2) │
│ 6 retrieval.similar()      → prior ClosedCase memory, case-specific │
│ 7 evidence + SAR           → deterministic claims + narrative gen   │
│ 8 case_writer.write_case() → FraudCase vertex + CASE_ON edge        │
└──────────────────────────────────────────────────────────────────────┘
        │                                   │
        ▼                                   ▼
 policies/policy.yaml              TigerGraph Savanna (graph "Fraud")
 (single threshold source)         Customer·Card·Txn·DeviceProfile·
                                   ClosedCase·FraudCase · 590k txns
        │                                   ▲
        ▼                                   │
 cases/HHG-001…020.json  ◄── validator.py ──┘  (fail-loud before write)
        │
        ▼
 ui/serve.py + ui/index.html — analyst console (live REST++ graph panel)
```

We deliberately used **no agent framework**. The loop is ~300 lines of Python you can
read top to bottom; tools are plain functions with a per-case call counter. When your
compliance requirement is "every decision must be reproducible," a framework's planner
and retry semantics are liabilities, not assets.

For tooling around the agent we did use the standard integration surface: the official
**TigerGraph MCP server** (`tigergraph-mcp`, 69 tools) is configured in `opencode.json`
and verified live against Savanna (`list_graphs → ["Fraud"]`,
`get_vertex_count(FraudCase) → 20`) — so an analyst working in an MCP-capable client
can interrogate the same graph the agent writes to, with schema, query, and loading
tools exposed under one protocol.

## How we used TigerGraph

**Graph-first evidence.** The loaded schema models the actual fraud domain: `Card —MADE→
Txn —FROM_DEVICE→ DeviceProfile`, `Txn —BILLED_IN→ BillingRegion`, `ClosedCase —ON_CARD→
Card`, `FraudCase —CASE_ON→ Card`. Four installed GSQL queries do the investigative work:

- `flagged_transaction(txn_id)` — pull the alert's attributes from the graph,
- `card_window(card_id, t, days)` — temporal traversal `Card → MADE → Txn` with a
  datetime-diff predicate (the CNP/card-testing/tempo detectors run over this),
- `device_neighbors(profile_id)` — reverse traversal
  `DeviceProfile ← FROM_DEVICE ← Txn ← MADE ← Card → OWNS → Customer`, i.e. *who else
  shares this device* — the shared-origin signal behind our undocumented-pattern rule,
- `connected_ring(card_id, t, days)` — multi-hop ring expansion (the card's window →
  its devices → every other card on those devices → their customers). This is the
  relationship-analysis query that powers connected-card monitoring and the
  two-confirmed-cards gate.

Evidence claims in the answer files cite these queries by name and parameters
(`ref: "query:device_neighbors(device_id=…)"`), and the dashboard fetches the
`CASE_ON`/`FROM_DEVICE`/`BILLED_IN` edges live from REST++ when rendering a case, so the
graph panel is never a mock.

**GraphRAG, concretely.** Retrieval is three-context, not one:

1. **graph evidence** — the four queries above, scoped to the case's card, device, and
   window (never a raw table dump),
2. **prior-case memory** — `retrieval.similar()` scores historical `ClosedCase`
   vertices by pattern, amount closeness, channel, region, note overlap, and connected
   cards, and the top matches ride along in `similar_prior_cases` and the SAR narrative,
3. **documents as context** — `policies/policy.yaml` and the typology mechanics in
   `agent.py` are the documentary corpus: rules R1–R10 and the pattern descriptions
   *are* the reason text attached to every recommended action.

The LLM-shaped slot in the architecture (explanation rephrase) consumes exactly this
context — and in the submission it consumes nothing, because `tokens: 0`.

**Case memory, closed loop.** A finished case is upserted as a `FraudCase` vertex
(status, verdict, prob, pattern) with a `CASE_ON` edge to the card. The next
investigation on that card family retrieves it. Writes are fail-loud: if Savanna is
unreachable, the run aborts rather than shipping `written_to_graph: true` with no vertex
behind it. All 20 benchmark cases are verifiably present on the graph
(`vertex HHG-001 … HHG-020`).

## Agentic capabilities

- **Triggers**: risk score, customer report, or analyst request via the case pack's
  `trigger_type` — each takes a different evidence branch (R2 denial settles a customer
  report; R4 simulates the no-reply path for model alerts).
- **Controlled evidence actions**: `evidence_requests` records *what* was asked
  (customer validation), *when* (after step 3), and *what was assumed* when no data
  exists — assumptions are declared, never silently folded into the probability.
- **Uncertainty, quantified**: `fraud_probability` with every threshold read from
  `policy.yaml` at runtime (a test greps the source tree to prove no threshold is
  hard-coded), plus a `stop_reason` for why the investigation ended there.
- **Permissions**: every action carries an approval route — `auto`, `L1` (single
  analyst), or `L2` (SAR/committee) — and `FILE_REPORT` is *required* to be `L2` by the
  validator. Recommendations are produced; execution is out of scope by policy.
- **New-pattern discovery**: when all five detectors miss but the customer denies and
  the device is shared across customers, the agent emits `pattern: "undocumented"` with
  a quantitative description (customer count, day span, amount band, transaction count)
  — 5 of the 8 fraud cases landed there.
- **Explanation**: per-action reason strings cite the exact rule (`"R2: customer
  denied"`, `"R4: no reply, monitor pending"`), and `explainer.py` renders the
  before/after decision diff the dashboard shows.

## What we learned

1. **The graph schema *is* the investigation.** Every question an analyst asks reduced
   to a traversal: "who else used this device" is one reverse edge; "is this burst
   different from history" is a datetime-filtered window. Changing a question meant
   editing a query, not a pipeline.
2. **Determinism is a feature, not a limit.** Regenerating all 20 answers twice
   produces byte-identical files (except `latency_s`). Reviewers can diff decisions;
   policy changes are one YAML edit with a failing test first.
3. **Guards before probability.** Our biggest correctness wins came from *dropping*
   signals (R7 monthly-rhythm disputes, trip-guard) before scoring, not from adding
   detectors. The probability is downstream of judgment calls, made explicit.
4. **Fail-loud beats fail-soft.** The validator runs before every file write and before
   every graph write. It caught real cross-field violations (exposure sums, SAR/verdict
   contradictions, BLOCK routes) during development — every fix started with a failing
   test.
5. **TigerGraph 4 schema scoping is worth understanding early.** Edge DDL is
   global-scope-only while schemas are graph-local; we designed the case-write path
   around `CASE_ON` after probing what the live graph would actually accept, rather
   than assuming DDL would work.

## What we would improve

- **Serve evidence live, not just cite it.** The answers' evidence claims are computed
  from the loaded dataset and cite the queries; the next step is executing the installed
  queries during `investigate()` and asserting CSV-vs-graph agreement as a test.
- **A real FraudCase ↔ Txn edge** (blocked by the DDL scoping above) plus a nightly job
  that closes cases and promotes analyst outcomes into the memory index.
- **Community/centrality algorithms** over the device-sharing graph (k-core or label
  propagation) to rank *which* shared devices matter before a human sees them.
- **An approval simulation loop**: have the UI's L1/L2 badges act on the case, feed the
  (simulated) decision back into the vertex, and show status transitions live.
- **Streaming triggers** — Kafka/REST webhook → `investigate()` instead of batch case
  packs.

---

*Built for the TigerGraph HHGOA challenge. All actions are recommendations or
simulated; no customer-facing effect. Data: HHGOA_IEEE dataset loaded into TigerGraph
Savanna (auto-stop outside hours).*
