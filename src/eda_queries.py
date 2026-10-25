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


# Query constants end in _Q; templates use str.format placeholders ({t}, {p}, ...).
# Every query has an ORDER BY (or a pandas sort) so refreshed CSVs are byte-identical.
NODE_COUNTS_Q = (
    "MATCH (n) RETURN labels(n)[0] AS label, size(labels(n)) AS n_labels, count(*) AS n "
    "ORDER BY label"
)
REL_TYPES_Q = "CALL db.relationshipTypes() YIELD relationshipType AS t RETURN t ORDER BY t"
EDGE_COUNTS_Q = (
    "MATCH (a)-[r:`{t}`]->(b) RETURN '{t}' AS rel_type, labels(a)[0] AS src, "
    "labels(b)[0] AS dst, count(r) AS n, "
    "sum(CASE WHEN r.unbiased THEN 1 ELSE 0 END) AS n_unbiased ORDER BY src, dst"
)
DEGREES_Q = (
    "MATCH (n) RETURN labels(n)[0] AS label, toString(n.identifier) AS id, n.name AS name, "
    "size((n)--()) AS degree ORDER BY label, id"
)
REL_COVERAGE_Q = (
    "MATCH (a)-[r:{t}]->(b) RETURN '{t}' AS rel_type, labels(a)[0] AS src, labels(b)[0] AS dst, "
    "count(DISTINCT a) AS n_src, count(DISTINCT b) AS n_dst ORDER BY src, dst"
)
NODE_PROPS_Q = (
    "MATCH (n) UNWIND keys(n) AS k RETURN labels(n)[0] AS label, k AS property, "
    "count(*) AS n_present, sum(CASE WHEN n[k] = '' THEN 1 ELSE 0 END) AS n_empty "
    "ORDER BY label, property"
)
NODE_SOURCES_Q = (
    "MATCH (n) RETURN labels(n)[0] AS label, n.source AS source, n.license AS license, "
    "count(*) AS n ORDER BY label, source, license"
)
EDGE_SOURCES_Q = (
    "MATCH ()-[r:{t}]->() UNWIND coalesce(r.sources, [r.source]) AS source "
    "RETURN '{t}' AS rel_type, source, r.unbiased AS unbiased, count(*) AS n "
    "ORDER BY source, unbiased"
)
TREATMENTS_Q = (
    "MATCH (c:Compound)-[r:TREATS_CtD|PALLIATES_CpD]->(d:Disease) "
    "RETURN c.identifier AS compound, c.name AS compound_name, d.identifier AS disease, "
    "d.name AS disease_name, type(r) AS rel_type ORDER BY rel_type, compound, disease"
)
DISEASE_PROFILE_Q = (
    "MATCH (d:Disease) RETURN d.identifier AS disease, d.name AS name, "
    "size((d)-[:ASSOCIATES_DaG]->()) AS genes, size((d)<-[:TREATS_CtD]-()) AS treats, "
    "size((d)<-[:PALLIATES_CpD]-()) AS palliates, size((d)-[:PRESENTS_DpS]->()) AS symptoms, "
    "size((d)-[:LOCALIZES_DlA]->()) AS anatomies, size((d)-[:RESEMBLES_DrD]-()) AS similar "
    "ORDER BY disease"
)
COMPOUND_PROFILE_Q = (
    "MATCH (c:Compound) RETURN c.identifier AS compound, c.name AS name, "
    "size((c)-[:BINDS_CbG]->()) AS binds, size((c)-[:CAUSES_CcSE]->()) AS side_effects, "
    "size((c)-[:TREATS_CtD]->()) AS treats, size((c)-[:PALLIATES_CpD]->()) AS palliates, "
    "size((c)-[:RESEMBLES_CrC]-()) AS resembles, size((c)<-[:INCLUDES_PCiC]-()) AS classes, "
    "size((c)-[:UPREGULATES_CuG]->()) AS up, size((c)-[:DOWNREGULATES_CdG]->()) AS down "
    "ORDER BY compound"
)
GENE_PROFILE_Q = (
    "MATCH (g:Gene) RETURN toString(g.identifier) AS gene, g.name AS name, "
    "g.chromosome AS chromosome, size((g)-[:INTERACTS_GiG]-()) AS interacts, "
    "size((g)<-[:BINDS_CbG]-()) AS bound_by, size((g)<-[:ASSOCIATES_DaG]-()) AS diseases, "
    "size((g)-[:PARTICIPATES_GpBP]->()) AS processes ORDER BY gene"
)
SELF_LOOPS_Q = "MATCH (a)-[r:{t}]->(a) RETURN count(r) AS v"
RECIPROCAL_Q = "MATCH (a)-[:{t}]->(b)-[:{t}]->(a) WHERE id(a) < id(b) RETURN count(*) AS v"
PARALLEL_Q = "MATCH (a)-[r:{t}]->(b) WITH a, b, count(r) AS k WHERE k > 1 RETURN count(*) AS v"
CONFLICTING_Q = (
    "MATCH (x)-[:UPREGULATES_{x}uG]->(g)<-[:DOWNREGULATES_{x}dG]-(x) "
    "RETURN count(*) AS pairs, count(DISTINCT x) AS entities"
)
EDGE_NUMERIC_Q = (
    "MATCH ()-[r:{t}]->() RETURN '{t}' AS rel_type, '{p}' AS property, r.{p} AS value "
    "ORDER BY value"
)
PHARM_CLASSES_Q = (
    "MATCH (p:PharmacologicClass) RETURN p.name AS name, p.class_type AS class_type, "
    "size((p)-[:INCLUDES_PCiC]->()) AS n_compounds ORDER BY name"
)
CBGAD_PATHS_Q = (
    "MATCH (c:Compound)-[:BINDS_CbG]->(g:Gene)<-[:ASSOCIATES_DaG]-(d:Disease) "
    "RETURN c.identifier AS compound, d.identifier AS disease, count(DISTINCT g) AS paths "
    "ORDER BY compound, disease"
)
CRCTD_PATHS_Q = (
    "MATCH (c:Compound)-[:RESEMBLES_CrC]-(c2:Compound)-[:TREATS_CtD]->(d:Disease) "
    "WHERE c <> c2 RETURN c.identifier AS compound, d.identifier AS disease, "
    "count(DISTINCT c2) AS paths ORDER BY compound, disease"
)

SYMMETRIC_TYPES = [
    "INTERACTS_GiG", "COVARIES_GcG", "REGULATES_GrG", "RESEMBLES_CrC", "RESEMBLES_DrD",
]
CONFLICT_SOURCES = {"C": "Compound", "D": "Disease", "A": "Anatomy"}
NUMERIC_EDGE_PROPS = [
    ("RESEMBLES_CrC", "similarity"),
    ("UPREGULATES_CuG", "z_score"),
    ("DOWNREGULATES_CdG", "z_score"),
    ("UPREGULATES_DuG", "log2_fold_change"),
    ("DOWNREGULATES_DdG", "log2_fold_change"),
]


def _simple(query: str) -> Callable[[], pd.DataFrame]:
    return lambda: cypher(query)


def _rel_types() -> list[str]:
    # One query per relationship type: a single scan of all 2.25M edges is too heavy.
    return sorted(cypher(REL_TYPES_Q)["t"])


def _per_type(template: str) -> Callable[[], pd.DataFrame]:
    def build() -> pd.DataFrame:
        return pd.concat([cypher(template.format(t=t)) for t in _rel_types()], ignore_index=True)

    return build


def node_counts() -> pd.DataFrame:
    return cypher(NODE_COUNTS_Q)


edge_counts = _per_type(EDGE_COUNTS_Q)


def degrees() -> pd.DataFrame:
    return cypher(DEGREES_Q)


def symmetry() -> pd.DataFrame:
    rows = []
    for t in SYMMETRIC_TYPES:
        vals = [cypher(q.format(t=t)).iat[0, 0] for q in (SELF_LOOPS_Q, RECIPROCAL_Q, PARALLEL_Q)]
        rows.append(dict(zip(["rel_type", "self_loops", "reciprocal_pairs", "parallel_pairs"],
                             [t, *vals])))
    return pd.DataFrame(rows)


def conflicting_regulation() -> pd.DataFrame:
    # Global aggregates always return one row (zeros if no match); the label is added here.
    frames = [
        cypher(CONFLICTING_Q.format(x=x)).assign(source_label=label)
        for x, label in CONFLICT_SOURCES.items()
    ]
    return pd.concat(frames, ignore_index=True)[["source_label", "pairs", "entities"]]


def edge_numeric() -> pd.DataFrame:
    return pd.concat(
        [cypher(EDGE_NUMERIC_Q.format(t=t, p=p)) for t, p in NUMERIC_EDGE_PROPS],
        ignore_index=True,
    )


DATASETS: dict[str, Callable[[], pd.DataFrame]] = {
    "node_counts": node_counts,
    "edge_counts": edge_counts,
    "degrees": degrees,
    "rel_coverage": _per_type(REL_COVERAGE_Q),
    "node_props": _simple(NODE_PROPS_Q),
    "node_sources": _simple(NODE_SOURCES_Q),
    "edge_sources": _per_type(EDGE_SOURCES_Q),
    "treatments": _simple(TREATMENTS_Q),
    "disease_profile": _simple(DISEASE_PROFILE_Q),
    "compound_profile": _simple(COMPOUND_PROFILE_Q),
    "gene_profile": _simple(GENE_PROFILE_Q),
    "symmetry": symmetry,
    "conflicting_regulation": conflicting_regulation,
    "edge_numeric": edge_numeric,
    "pharm_classes": _simple(PHARM_CLASSES_Q),
    "cbgad_paths": _simple(CBGAD_PATHS_Q),
    "crctd_paths": _simple(CRCTD_PATHS_Q),
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
