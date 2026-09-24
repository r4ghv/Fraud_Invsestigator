# Social posts (X + LinkedIn)

Publish after the blog + demo video URLs exist, then paste the real links.

## X / Twitter (≤280 chars)

```
Built a fraud investigation agent on @TigerGraphDB for the HHGOA challenge 🕵️
590k txns in Savanna, GSQL traversals for evidence, policy-driven decisions
(tokens: 0), every case written back to the graph as memory.
Blog: <BLOG_URL>
Demo (4 min): <VIDEO_URL>
#TigerGraph #FraudDetection #AIagents
```

Variant B (shorter):

```
Graph-first fraud agent on @TigerGraphDB: investigate → evidence → decide →
explain → write the case back to the graph. 20/20 cases on Savanna,
deterministic decisions, framework-free.
<BLOG_URL> · demo: <VIDEO_URL>
```

## LinkedIn

```
What do you build when the challenge says "investigate fraud on a knowledge graph" —
and you want every decision to survive a compliance review?

For the TigerGraph HHGOA challenge I built a fraud investigation agent that runs the
full loop on a 590k-transaction graph in Savanna:

→ Trigger (risk score / customer report / analyst request)
→ Investigate via GSQL traversals (card windows, device-sharing rings, prior cases)
→ Evidence claims cited by query name + parameters
→ Uncertainty quantified — every threshold from one policy.yaml
→ Next best actions with approval routes (auto / L1 / L2), shown before AND after
   evidence is requested
→ Deterministic SAR narrative when policy requires one
→ Case written back to the graph as a FraudCase vertex — memory for the next case

Two design calls worth calling out:
1. tokens: 0 — an LLM never makes a decision here. The explainer slot exists but stays
   cold. Determinism is what let me regenerate all 20 benchmark cases byte-identically.
2. No agent framework — the loop is ~300 readable Python lines, 82 tests, pyflakes-clean.
   When reproducibility is the requirement, a planner in the middle is a liability.

The fun part: when all five known detectors miss but the customer denies the charge and
the device is shared across customers, the agent coins an "undocumented" pattern with a
quantitative description — 5 of the 8 fraud cases landed there.

📖 Blog: <BLOG_URL>
🎬 4-min end-to-end demo: <VIDEO_URL>
🐙 Code: https://github.com/r4ghv/Fraud_Invsestigator

#TigerGraphDB #GraphAI #FraudDetection #CyberSecurity
```
