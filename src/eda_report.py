"""Generate reports/eda/REPORT.md from the cached EDA datasets.

Every number in the report is computed here from data/eda/*.csv; nothing is typed in by hand.
Run from the repo root:  uv run python src/eda_report.py   (offline; needs the cache).
"""
import datetime
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

import eda_stats as st
from eda_plots import make_all
from eda_queries import load_all

REPORT_DIR = Path("reports/eda")
FIG_DIR = REPORT_DIR / "figures"
REPORT_PATH = REPORT_DIR / "REPORT.md"
SERVER = "Hetionet v1.0 on Neo4j 3.5 (neo4j.het.io)"
COMMANDS = "`uv run python src/eda_queries.py` then `uv run python src/eda_report.py`"


# ---------------------------------------------------------------- promoted exploration findings
@dataclass(frozen=True)
class Finding:
    """A probe result promoted from EXPLORATION.md; `summarize` returns one sentence with a number."""
    slug: str
    title: str
    kind: Literal["data error", "modelling artefact", "real biology", "unexplained"]
    dataset: str  # a finding_<slug> key in eda_queries.DATASETS
    summarize: Callable[[pd.DataFrame], str]


def _drug_causes_indication(df: pd.DataFrame) -> str:
    t = df[df["treaters"] > 0]
    n, obs = int(t["treaters"].sum()), int(t["treaters_causing"].sum())
    n_compounds = int(df["n_compounds"].iloc[0])
    expected = float((t["treaters"] * t["causers"] / n_compounds).sum())
    return (
        f"Of the {_n(n)} TREATS edges into the {len(t)} treated diseases that share their name with "
        f"a side effect, {_n(obs)} ({_pct(obs / n)}) come from a compound also listed as causing that "
        f"side effect, {obs / expected:.1f} times the {expected:.1f} expected if treating compounds "
        f"caused it as often as all {_n(n_compounds)} compounds do."
    )


def _x_and_y_genes(df: pd.DataFrame) -> str:
    names = sorted(df["name"])
    return (
        f"{_n(len(df))} genes are listed on both chromosomes X and Y (`X|Y`), e.g. "
        f"{' and '.join(names[:2])}, so an exact filter such as `chromosome = 'X'` misses them."
    )


def _loc_placeholder_genes(df: pd.DataFrame) -> str:
    iso = df[df["isolated"]]
    loc = df[df["loc_name"]]
    loc_iso = int(iso.loc[iso["loc_name"], "genes"].sum())
    n_iso, n_loc = int(iso["genes"].sum()), int(loc["genes"].sum())
    return (
        f"{_n(loc_iso)} of the {_n(n_iso)} isolated genes ({_pct(loc_iso / n_iso)}) are uncharacterised "
        f"`LOC` placeholder records, and {_pct(loc_iso / n_loc)} of all {_n(n_loc)} `LOC` genes have "
        f"no edge at all."
    )


MAX_FINDINGS = 3
FINDINGS: list[Finding] = [
    Finding("drug_causes_indication", "Drugs listed as causing the disease they treat", "unexplained",
            "finding_drug_causes_indication", _drug_causes_indication),
    Finding("nonstandard_chromosomes", "Genes listed on both X and Y", "real biology",
            "finding_nonstandard_chromosomes", _x_and_y_genes),
    Finding("loc_placeholder_genes", "Isolated genes are mostly LOC placeholders", "modelling artefact",
            "finding_loc_placeholder_genes", _loc_placeholder_genes),
]
assert len(FINDINGS) <= MAX_FINDINGS


# ---------------------------------------------------------------- formatting helpers
def _cell(v: Any) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return "-"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    if isinstance(v, (float, np.floating)):
        return f"{v:,.0f}" if abs(v) >= 1000 or v == int(v) else f"{v:.3g}"
    return str(v).replace("|", "\\|")


def _md_table(df: pd.DataFrame) -> str:
    """GitHub-flavoured Markdown table; a named or non-default index becomes the first column."""
    if df.index.name is not None or not isinstance(df.index, pd.RangeIndex):
        df = df.reset_index()
    head = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = ["| " + " | ".join(_cell(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([head, sep, *rows])


def _pct(x: float) -> str:
    return f"{x:.1%}"


def _n(x: float) -> str:
    return f"{x:,.0f}"


def _names(items: list[str], k: int = 5) -> str:
    shown = ", ".join(items[:k])
    return shown + (", ..." if len(items) > k else "")


def _ranked(s: pd.Series, descending: bool = True) -> list[tuple[Any, float]]:
    """(key, value) pairs ordered by value, ties broken alphabetically by key."""
    sign = -1 if descending else 1
    return sorted(s.items(), key=lambda kv: (sign * kv[1], str(kv[0])))


def _extreme(ranked: list[tuple[Any, float]], fmt, what: str = "types") -> str:
    """Describe the first value of a ranking, naming the ties if several keys share it."""
    top = ranked[0][1]
    tied = [str(k) for k, v in ranked if v == top]
    if len(tied) == 1:
        return f"{fmt(top)} ({tied[0]})"
    return f"{fmt(top)} for {len(tied)} {what} ({_names(tied, 3)})"


def _frac(cov: pd.DataFrame, rel: str, side: str) -> float:
    return float(cov.loc[cov["rel_type"] == rel, side].iloc[0])


# ---------------------------------------------------------------- facts
def compute_facts(data: dict[str, pd.DataFrame]) -> dict[str, Any]:
    deg, ec = data["degrees"], data["edge_counts"]
    by_rel = ec.groupby("rel_type")["n"].sum()
    top2 = _ranked(by_rel)[:2]
    summ = st.degree_summary(deg)
    cov = st.coverage(data["rel_coverage"], data["node_counts"])
    dp, tr, sym = data["disease_profile"], data["treatments"], data["symmetry"]
    no_treat = dp[(dp["treats"] + dp["palliates"]) == 0]
    kinds = tr.groupby(["compound", "disease"])["rel_type"].nunique()
    gene_deg = deg[deg["label"] == "Gene"]["degree"]
    hubs = st.top_hubs(deg, "Gene", 5)
    inter = sym[sym["rel_type"] == "INTERACTS_GiG"]
    gp = data["gene_profile"]
    return {
        "n_nodes": int(data["node_counts"]["n"].sum()),
        "n_edges": int(ec["n"].sum()),
        "n_labels": int(data["node_counts"]["label"].nunique()),
        "n_rel_types": int(by_rel.size),
        "top2_rel_share": float(sum(v for _, v in top2) / by_rel.sum()),
        "top2_rel_types": [k for k, _ in top2],
        "gene_gini": st.gini(gene_deg),
        "gene_median_degree": float(gene_deg.median()),
        "isolated_by_label": {k: int(v) for k, v in sorted(summ["isolated"].items())},
        "top_genes": hubs["name"].tolist(),
        "top_gene_degree": int(hubs["degree"].iloc[0]),
        "pct_genes_bound": _frac(cov, "BINDS_CbG", "dst_frac"),
        "pct_compounds_treating": _frac(cov, "TREATS_CtD", "src_frac"),
        "n_diseases": int(len(dp)),
        "diseases_no_treatment": int(len(no_treat)),
        "diseases_no_treatment_names": sorted(no_treat["name"]),
        "treat_palliate_overlap": int((kinds > 1).sum()),
        "interacts_self_loops": int(inter["self_loops"].sum()),
        "interacts_reciprocal": int(inter["reciprocal_pairs"].sum()),
        "conflicting_regulation": {
            r.source_label: int(r.pairs)
            for r in data["conflicting_regulation"].sort_values("source_label").itertuples()
        },
        "genes_missing_chromosome": int(gp["chromosome"].isna().sum()),
        "cross_label_name_count": int(len(st.cross_label_names(deg))),
        "study_bias_rho": st.spearman(gp["bound_by"], gp["interacts"]),
        "auroc_cbgad": st.metapath_auroc(data["cbgad_paths"], tr, deg),
        "auroc_crctd": st.metapath_auroc(data["crctd_paths"], tr, deg),
    }


def _strength(rho: float) -> str:
    return "strong" if abs(rho) >= 0.6 else "moderate" if abs(rho) >= 0.3 else "weak"


def takeaways(f: dict[str, Any]) -> list[str]:
    iso = f["isolated_by_label"]
    iso_total = sum(iso.values())
    iso_txt = ", ".join(f"{k} {_n(v)}" for k, v in iso.items() if v) or "none"
    conflicts = sum(f["conflicting_regulation"].values())
    return [
        f"The graph has {_n(f['n_nodes'])} nodes in {f['n_labels']} labels and "
        f"{_n(f['n_edges'])} edges in {f['n_rel_types']} relationship types.",
        f"The two largest relationship types ({', '.join(f['top2_rel_types'])}) hold "
        f"{_pct(f['top2_rel_share'])} of all edges.",
        f"Gene degree is highly unequal (Gini {f['gene_gini']:.2f}, median degree "
        f"{f['gene_median_degree']:.0f}); the top hubs are {_names(f['top_genes'])}, "
        f"led by {f['top_genes'][0]} with {_n(f['top_gene_degree'])} edges.",
        f"{_n(iso_total)} nodes have no edges at all (by label: {iso_txt}).",
        f"Only {_pct(f['pct_genes_bound'])} of genes are bound by any compound, and "
        f"{_pct(f['pct_compounds_treating'])} of compounds treat any disease.",
        f"{f['diseases_no_treatment']} of {f['n_diseases']} diseases have neither a treating nor "
        f"a palliating compound, so questions about them have empty gold answers.",
        f"{_n(f['treat_palliate_overlap'])} compound-disease pairs carry both a TREATS and a "
        f"PALLIATES edge.",
        f"INTERACTS_GiG has {_n(f['interacts_self_loops'])} self-loops and "
        f"{_n(f['interacts_reciprocal'])} reciprocal pairs, and {_n(conflicts)} "
        f"compound/disease/anatomy-gene pairs both up- and down-regulate the same gene.",
        f"{_n(f['genes_missing_chromosome'])} genes lack a chromosome, and "
        f"{_n(f['cross_label_name_count'])} names (case-insensitive) are shared by nodes of "
        f"different labels.",
        f"Gene interaction degree and number of binding compounds have a {_strength(f['study_bias_rho'])} "
        f"rank correlation (Spearman rho {f['study_bias_rho']:.2f}).",
        f"Metapath counts separate treated from untreated pairs (AUROC {f['auroc_cbgad']:.3f} for "
        f"CbGaD, {f['auroc_crctd']:.3f} for CrCtD).",
    ]


# ---------------------------------------------------------------- sections
def _fig(figs: dict[str, Path], key: str, alt: str) -> str:
    return f"![{alt}](figures/{figs[key].name})"


def _basic(data, f, figs) -> list[str]:
    ec, nc, deg = data["edge_counts"], data["node_counts"], data["degrees"]
    rel_rank = _ranked(ec.groupby("rel_type")["n"].sum())
    top_label = nc.sort_values(["n", "label"], ascending=[False, True]).iloc[0]
    pairs = ec[["src", "dst"]].drop_duplicates()
    (ds, dd), dn = _ranked(ec.groupby(["src", "dst"])["n"].sum())[0]
    cov = st.coverage(data["rel_coverage"], nc)
    comp = st.completeness(data["node_props"], nc)
    stacked = comp.stack()
    partial = stacked[stacked < 1]
    lowest = _ranked(partial, descending=False)[:3]
    low_txt = ", ".join(f"{lab}.{prop} ({_pct(v)})" for (lab, prop), v in lowest)
    unb = ec.groupby("rel_type")[["n", "n_unbiased"]].sum()
    unb_share = unb["n_unbiased"] / unb["n"]
    es = data["edge_sources"]
    summ = st.degree_summary(deg)
    return [
        "## 1. Basic properties", "",
        "### B1. Size", "",
        _fig(figs, "counts", "Nodes per label and edges per relationship type"), "",
        f"{top_label['label']} is the largest label with {_n(top_label['n'])} of {_n(f['n_nodes'])} "
        f"nodes. {rel_rank[0][0]} is the largest relationship type with {_n(rel_rank[0][1])} edges; "
        f"the smallest is {rel_rank[-1][0]} with {_n(rel_rank[-1][1])}.", "",
        "### B2. Metagraph", "",
        _fig(figs, "metagraph_heatmap", "Edges between node labels"), "",
        f"{len(pairs)} directed label pairs are connected by at least one relationship type. "
        f"The densest is {ds} -> {dd} with {_n(dn)} edges.", "",
        "### B3. Degrees", "",
        _fig(figs, "degree_ccdf", "Degree CCDF per label"), "",
        f"Gene degree has Gini {f['gene_gini']:.2f} and median {f['gene_median_degree']:.0f}, "
        f"but the top hub, {f['top_genes'][0]}, has {_n(f['top_gene_degree'])} edges. "
        f"Top 5 genes by degree (ties alphabetical): {', '.join(f['top_genes'])}.", "",
        _md_table(summ), "",
        "### B4. Coverage", "",
        _fig(figs, "coverage_heatmap", "Share of nodes with an edge, per relationship type"), "",
        f"{_pct(f['pct_genes_bound'])} of genes are bound by a compound (BINDS_CbG) and "
        f"{_pct(f['pct_compounds_treating'])} of compounds treat a disease (TREATS_CtD). "
        f"The lowest source-side coverage is "
        f"{_extreme(_ranked(cov.set_index('rel_type')['src_frac'], descending=False), _pct)}.", "",
        "### B5. Completeness", "",
        _fig(figs, "completeness_heatmap", "Property completeness per label"), "",
        f"{len(partial)} of {len(stacked)} label-property combinations are less than fully "
        f"populated" + (f"; the emptiest are {low_txt}." if len(partial) else "."), "",
        "### B6. Provenance", "",
        _fig(figs, "unbiased_share", "Unbiased share of edges per relationship type"), "",
        f"Edges come from {es['source'].nunique()} distinct sources. The share of edges flagged "
        f"unbiased ranges from {_extreme(_ranked(unb_share, descending=False), _pct)} to "
        f"{_extreme(_ranked(unb_share), _pct)}.", "",
    ]


def _quirks(data, f, figs) -> list[str]:
    dp, deg, cp = data["disease_profile"], data["degrees"], data["compound_profile"]
    top = dp.assign(total=dp["treats"] + dp["palliates"]).sort_values(
        ["total", "name"], ascending=[False, True]).head(5)
    en = data["edge_numeric"].groupby(["rel_type", "property"])["value"].agg(
        n="count", min="min", median="median", max="max")
    pc = data["pharm_classes"]
    by_type = pc.groupby("class_type").agg(classes=("name", "size"), median_compounds=("n_compounds", "median"))
    no_class = int((cp["classes"] == 0).sum())
    xl = st.cross_label_names(deg)
    nd = f["diseases_no_treatment_names"]
    return [
        "## 2. Data quirks", "",
        "### Q1. Treatments", "",
        _fig(figs, "treatments_per_disease", "Compounds treating or palliating each disease"), "",
        f"{f['diseases_no_treatment']} of {f['n_diseases']} diseases have no treating or palliating "
        f"compound: {', '.join(nd) if nd else 'none'}. {_n(f['treat_palliate_overlap'])} "
        f"compound-disease pairs carry both TREATS and PALLIATES. Most-treated diseases: "
        + ", ".join(f"{r.name} ({r.total})" for r in top.itertuples()) + ".", "",
        "### Q2. Graph structure", "",
        "Self-loops, reciprocal pairs and parallel edges in same-label relationship types:", "",
        _md_table(data["symmetry"]), "",
        "### Q3. Contradictions", "",
        "Entities that both up- and down-regulate the same gene (pairs of entity and gene):", "",
        _md_table(data["conflicting_regulation"]), "",
        "### Q4. Names", "",
        "Counts are over named nodes per label. `all_lower` = name equals its lowercase form; "
        "`has_punct` = contains any of `" + st.PUNCT + "`.", "",
        _md_table(st.name_quirks(deg)), "",
        f"{len(xl)} lowercased names occur under more than one label. First 15:", "",
        _md_table(xl.head(15)), "",
        "### Q5. Study bias", "",
        _fig(figs, "gene_study_bias", "Gene interactions versus binding compounds"), "",
        f"Interaction degree and number of binding compounds have a {_strength(f['study_bias_rho'])} "
        f"rank correlation (Spearman rho {f['study_bias_rho']:.2f}). {_n(f['genes_missing_chromosome'])} genes have "
        f"no chromosome value.", "",
        "### Q6. Edge weights", "",
        _fig(figs, "edge_numeric", "Distributions of numeric edge properties"), "",
        _md_table(en), "",
        "### Q7. Drug classes", "",
        _fig(figs, "compound_profile", "Side effects per compound and pharmacologic classes"), "",
        f"{_n(no_class)} of {_n(len(cp))} compounds belong to no pharmacologic class.", "",
        _md_table(by_type), "",
    ]


def _signal(f, figs) -> list[str]:
    return [
        "## 3. Repurposing signal", "",
        _fig(figs, "metapath_signal", "Metapath path counts for treated versus untreated pairs"), "",
        f"Over all Compound x Disease pairs, path counts separate treated from untreated pairs with "
        f"AUROC {f['auroc_cbgad']:.3f} for CbGaD (compound-binds-gene-associates-disease) and "
        f"{f['auroc_crctd']:.3f} for CrCtD (compound-resembles-compound-treats-disease).", "",
        "Caveat: the AUROC describes association within the 2017 snapshot and does not validate "
        "predictions.", "",
    ]


def _implications(data, f) -> list[str]:
    q = st.name_quirks(data["degrees"])
    xl = st.cross_label_names(data["degrees"])
    nd = f["diseases_no_treatment_names"]

    def row(label: str, col: str) -> str:
        return f"{_n(q.loc[label, col])} of {_n(q.loc[label, 'n'])}" if label in q.index else "0 of 0"

    return [
        "## 4. Implications for the agent benchmark", "",
        f"- **Trap questions.** {f['diseases_no_treatment']} diseases have no treating or palliating "
        f"compound (e.g. {_names(nd, 4) if nd else 'none'}); asking which compounds treat them has an "
        f"empty gold answer, so a correct agent must say nothing was found rather than guess.",
        f"- **Casing.** {row('Disease', 'all_lower')} disease names are fully lowercase (the rest contain capitals) while "
        f"{row('Compound', 'starts_upper')} compound names start with a capital, so exact-match "
        f"filters such as `name = 'Metformin'` fail on the wrong case.",
        f"- **Punctuation and encoding.** {row('Compound', 'has_punct')} compound names contain "
        f"punctuation ({st.PUNCT}) and {_n(q['non_ascii'].sum())} names across all labels contain "
        f"non-ASCII characters, which exact string matches must reproduce character for character.",
        f"- **Shared names.** {_n(f['cross_label_name_count'])} names occur under more than one label"
        + (f" (e.g. {_names(xl['name_lower'].tolist(), 3)})" if len(xl) else "")
        + ", and "
        f"{_n(q['dup_names'].sum())} names are duplicated within their own label, so queries "
        f"without a label or `DISTINCT` can return extra rows.",
        f"- **Hub bias.** Questions about top genes ({_names(f['top_genes'], 3)}) return very large "
        f"result sets: {f['top_genes'][0]} alone has {_n(f['top_gene_degree'])} edges against a "
        f"median gene degree of {f['gene_median_degree']:.0f}, far beyond the row cap an agent sees.",
        f"- **Repurposing questions.** Path counts are an informative but far from decisive signal "
        f"(AUROC {f['auroc_cbgad']:.3f} for CbGaD, {f['auroc_crctd']:.3f} for CrCtD), so agent "
        f"rankings built on them are not a substitute for the gold answer; gold rankings "
        f"tie-break alphabetically by name.", "",
    ]


def _findings(sentences: list[tuple[Finding, str]]) -> list[str]:
    if not sentences:
        return []
    lines = [
        "## 5. Unexpected findings", "",
        f"Promoted from a bounded open-ended exploration (at most {MAX_FINDINGS} findings; the full "
        "probe log, including dead ends, is in `EXPLORATION.md` and `probes.jsonl`).", "",
    ]
    for f, sentence in sentences:
        lines += [f"### {f.title}", "", f"*Classification: {f.kind}.* {sentence}", ""]
    return lines


def render(data: dict[str, pd.DataFrame], facts: dict[str, Any], figures: dict[str, Path]) -> str:
    found = [(f, f.summarize(data[f.dataset])) for f in FINDINGS]
    lines = [
        "# Hetionet v1.0 — Exploratory Data Analysis", "",
        f"{SERVER}; generated {datetime.date.today().isoformat()}; reproduce with {COMMANDS}.", "",
        "## Key takeaways", "",
        *[f"- {t}" for t in takeaways(facts)],
        *[f"- {s}" for _, s in found], "",
        *_basic(data, facts, figures),
        *_quirks(data, facts, figures),
        *_signal(facts, figures),
        *_implications(data, facts),
        *_findings(found),
    ]
    return "\n".join(lines)


def main() -> None:
    data = load_all()  # fails first (with the fetch command) if the cache is missing
    figures = make_all(data, FIG_DIR)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render(data, compute_facts(data), figures), encoding="utf-8")
    print(f"wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
