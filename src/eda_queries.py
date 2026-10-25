"""Cached Cypher datasets for the Hetionet exploratory analysis.

Each dataset is built by a query function, saved to data/eda/<name>.csv and
read back from there, so stats and plots never touch the live server.
"""
import argparse
import os
from collections.abc import Callable, Iterable
from pathlib import Path

import pandas as pd

from db import run_cypher

CACHE_DIR = Path("data/eda")
# Identifier columns are always written and read as strings (no int/float coercion).
ID_COLUMNS = {"id", "compound", "disease", "gene"}


def cypher(query: str) -> pd.DataFrame:
    """Run a read-only query over the full result and return it as a DataFrame."""
    res = run_cypher(query, max_rows=None)
    if "error" in res:
        raise RuntimeError(res["error"])
    for row in res["rows"]:
        for value in row.values():
            if isinstance(value, (list, dict)):
                raise TypeError("CSV cannot store list/dict cells; UNWIND them in the query")
    return pd.DataFrame(res["rows"], columns=res["columns"])


def node_counts() -> pd.DataFrame:
    return cypher(
        "MATCH (n) RETURN labels(n)[0] AS label, size(labels(n)) AS n_labels, count(*) AS n"
    )


def edge_counts() -> pd.DataFrame:
    # One query per relationship type: a single scan of all 2.25M edges is too heavy.
    types = cypher("CALL db.relationshipTypes() YIELD relationshipType AS t RETURN t")["t"]
    frames = [
        cypher(
            f"MATCH (a)-[r:`{t}`]->(b) RETURN '{t}' AS rel_type, labels(a)[0] AS src, "
            "labels(b)[0] AS dst, count(r) AS n, "
            "sum(CASE WHEN r.unbiased THEN 1 ELSE 0 END) AS n_unbiased"
        )
        for t in sorted(types)
    ]
    return pd.concat(frames, ignore_index=True)


DATASETS: dict[str, Callable[[], pd.DataFrame]] = {
    "node_counts": node_counts,
    "edge_counts": edge_counts,
}


def _path(name: str) -> Path:
    return CACHE_DIR / f"{name}.csv"


def read_cached(name: str) -> pd.DataFrame:
    return pd.read_csv(
        _path(name),
        dtype={c: str for c in ID_COLUMNS},
        keep_default_na=False,
        na_values=[""],
        encoding="utf-8",
    )


def fetch(name: str, refresh: bool = False) -> pd.DataFrame:
    """Return the cached dataset, building and caching it first if needed."""
    path = _path(name)
    if path.exists() and not refresh:
        return read_cached(name)
    df = DATASETS[name]()
    for col in ID_COLUMNS & set(df.columns):
        df[col] = df[col].astype(str)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8")
    os.replace(tmp, path)
    return df


def load_all(names: Iterable[str] | None = None) -> dict[str, pd.DataFrame]:
    """Read datasets from the cache only; never queries the server."""
    out = {}
    for name in names if names is not None else DATASETS:
        if not _path(name).exists():
            raise FileNotFoundError(
                f"Dataset '{name}' is not cached at {_path(name)}. "
                "Run: uv run python src/eda_queries.py"
            )
        out[name] = read_cached(name)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch and cache Hetionet EDA datasets.")
    ap.add_argument("--refresh", action="store_true", help="rebuild even if cached")
    ap.add_argument("--only", help="comma-separated dataset names (default: all)")
    args = ap.parse_args()
    names = args.only.split(",") if args.only else list(DATASETS)
    for name in names:
        print(f"{name}: {len(fetch(name, refresh=args.refresh))} rows")


if __name__ == "__main__":
    main()
