# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A benchmark of how accurately and how *reproducibly* LLM agents answer drug-repurposing questions by writing Cypher against Hetionet v1.0 (a frozen 2017 biomedical knowledge graph on the public Neo4j server `neo4j.het.io`, no credentials). Results feed a research comparison across models, so fairness (same prompt, same tools, same scoring for every model) matters more than agent cleverness.

## Commands

Uses uv (Python >=3.12). Tests run with `uv run pytest`; no linter is configured.

```bash
uv sync
uv run python src/explore_schema.py     # check DB connection; regenerates data/schema.md
uv run python src/build_gold.py         # re-run gold Cypher on the live server; regenerates data/questions.jsonl
uv run python src/evaluate.py           # self-test of the scorer against the gold answers
uv run python src/run_experiments.py --models qwen3.8-27b --only q01            # single question
uv run python src/run_experiments.py --models a,b --reps 3 --max-steps 6        # full run
uv run python src/check_log.py [results/pilot_*.jsonl]   # re-check faithfulness offline (default: newest log)
uv run python src/eda_queries.py [--refresh]   # fills the data/eda/ cache from the live server
uv run python src/eda_report.py         # offline: figures plus reports/eda/REPORT.md
uv run python src/eda_pdf.py            # offline: 2-page summary reports/eda/REPORT.pdf
uv run pytest                           # unit tests
```

Always run from the repo root: modules import each other flatly (`from db import run_cypher`, scripts live in `src/`) and open `data/...`/`results/...` by relative path. Running agents needs `.env` with `LLM_BASE_URL` and `LLM_API_KEY` (see `.env.example`); DB-only scripts don't.

## Architecture

Pipeline per (model, question, rep) in `src/run_experiments.py`:

1. `agent.run_agent` — plain OpenAI-compatible tool-calling loop with a single `run_cypher` tool, `temperature=0`, `seed=0` (dropped automatically if the provider rejects it; `seed_used` records this). Records every Cypher step, token usage and latency.
2. `final_query` picks the **last non-erroring Cypher** the agent ran; it is re-executed with `max_rows=None` so scoring uses the full result, not the 50-row cap the agent saw.
3. `evaluate.score` compares those rows to `gold_result`. Column names are ignored (aliases differ); values are normalised (lowercased strings, rounded floats); if the agent returned extra columns, the best-matching k-column subset is used. `ordered` questions require exact order; `trap` questions are correct only when the result is empty **and** the answer text matches the `NOT_FOUND` regex.
4. `faithfulness.faithfulness` checks the natural-language `final_answer` against the rows (bulleted items not backed by the result = `unsupported`; result values absent from the text = `missing`).
5. `result_sig` (hash of normalised rows) and `final_cypher` are used by `summarize` to measure repeatability across reps.

Each run writes one JSONL line to `results/pilot_<timestamp>.jsonl` (flushed per record). Network/provider failures are stored as `infra_error` and **excluded** from accuracy rather than counted as wrong; a 402/credit error stops the whole run.

Key shared pieces:
- `db.py` — the only DB access path. Enforces read-only via regex (string literals stripped first), retries with backoff, and raises `ConnectionError` on infra failure so it is never scored as a model mistake. `explore_schema.py` has its own duplicate HTTP client.
- `prompt.py` — `SYSTEM_PROMPT` shared by all models; it embeds the schema summary and the Neo4j 3.5 dialect warning.
- `models.py` — registry mapping CLI keys to model ids; all share one endpoint from env.
- `build_gold.py` — the source of truth for questions. Edit `QUESTIONS` there and regenerate; don't hand-edit `data/questions.jsonl`.

## Domain gotchas

- Server is **Neo4j 3.5**: no `EXISTS { ... }` subqueries or other 4.x+ syntax.
- Disease names are lowercase (`'multiple sclerosis'`), compound names capitalised (`'Metformin'`). Only 137 diseases exist.
- Relationship types encode direction in the suffix (`TREATS_CtD` = Compound→Disease); full list in `data/schema.md`.
- Rankings must tie-break alphabetically by name for deterministic gold answers.
- Source files are UTF-8 with BOM; read data with `encoding="utf-8"`.
