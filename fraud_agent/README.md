# Fraud Agent — deterministic-first

Target: TigerGraph HHGOA Agentic Fraud Investigation.

Rule: ALL policy, risk, NBA, SAR, and approval decisions are deterministic code.
LLM is allowed ONLY for phrasing explanations, never for decisions.

## Layout
- `policies/` — versioned YAML, the only source of truth for actions
- `src/policy_engine.py` — deterministic evaluator, no LLM calls
- `src/pattern_detectors.py` — GSQL-backed graph pattern checks (pure functions)
- `src/evidence_collector.py` — TigerGraph MCP/GSQL interface (mock fallback)
- `src/agent.py` — 8-step orchestration
- `src/explainer.py` — template explanation, optional LLM rephrase
- `src/validator.py` — answer-format validator (fail-loud before any write)
- `src/tigergraph/` — schema + GSQL queries
- `ui/` — analyst dashboard (to be added)
- `cases/` — per-case answer files for the 20 benchmark cases

## Quickstart (no dataset yet)
```bash
python -m pytest fraud_agent/tests/ -q
python -m fraud_agent.src.agent --help
```

## Wiring Savanna / dataset
1. Paste HHGOA_IEEE link/zip path (not found locally).
2. Provide Savanna endpoint + credentials via env (see `.env.example`).
3. Load data per `src/tigergraph/schema.gsql`, then run `agent.py`.
