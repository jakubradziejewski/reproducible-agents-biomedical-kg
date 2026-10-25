"""Budgeted probe queries for open-ended exploration of Hetionet.

Every probe states its hypothesis before it runs and is appended to LOG_PATH,
including failed ones, so the budget record shows dead ends as well as hits.
Use from the repo root, e.g.:
    uv run python -c "from eda_probe import probe; print(probe('slug', 'hypothesis', 'MATCH ...'))"
(with src/ on the path, e.g. PYTHONPATH=src).
"""
import datetime
import json
from pathlib import Path

import pandas as pd

import eda_queries

MAX_PROBES = 25
PROBE_DIR = Path("data/eda/probes")
LOG_PATH = Path("reports/eda/probes.jsonl")


def _log_entries() -> list[dict]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _append(entry: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def probe(slug: str, hypothesis: str, query: str) -> pd.DataFrame:
    """Run one logged, budgeted exploration query and cache its result as PROBE_DIR/<slug>.csv."""
    entries = _log_entries()
    if len(entries) >= MAX_PROBES:
        raise RuntimeError("probe budget exhausted")
    if not hypothesis.strip():
        raise ValueError("a probe needs a hypothesis written before it runs")
    if any(e["slug"] == slug for e in entries):
        raise ValueError(f"duplicate probe slug: {slug}")
    entry = {"slug": slug, "hypothesis": hypothesis, "query": query, "rows": None,
             "ts": datetime.datetime.now().isoformat(timespec="seconds")}
    try:
        df = eda_queries.cypher(query)
    except Exception as exc:  # a failed probe still costs budget
        _append({**entry, "error": str(exc)})
        raise
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROBE_DIR / f"{slug}.csv", index=False, encoding="utf-8")
    _append({**entry, "rows": len(df)})
    return df
