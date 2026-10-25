"""Pure-pandas analysis functions over the cached EDA datasets (no DB access)."""
from collections.abc import Sequence

import numpy as np
import pandas as pd

PUNCT = ",()[]/'"


def gini(values: Sequence[float]) -> float:
    """Gini coefficient of non-negative values (0 = equal, ->1 = one holds all)."""
    x = np.sort(np.asarray(values, dtype=float))
    n, total = len(x), x.sum()
    if n == 0 or total == 0:
        return 0.0
    ranks = np.arange(1, n + 1)
    return float((2 * (ranks * x).sum()) / (n * total) - (n + 1) / n)


def auroc(pos: Sequence[float], neg: Sequence[float]) -> float:
    """Mann-Whitney U / (n_pos * n_neg) using average ranks for ties."""
    n_pos, n_neg = len(pos), len(neg)
    ranks = pd.Series(list(pos) + list(neg)).rank(method="average")
    u = ranks.iloc[:n_pos].sum() - n_pos * (n_pos + 1) / 2
    return float(u / (n_pos * n_neg))


def spearman(x: pd.Series, y: pd.Series) -> float:
    """Spearman rank correlation: Pearson on average ranks (no scipy)."""
    return float(x.rank().corr(y.rank()))


def degree_summary(degrees: pd.DataFrame) -> pd.DataFrame:
    def one(g: pd.DataFrame) -> pd.Series:
        d = g["degree"]
        return pd.Series({
            "n": len(d), "isolated": int((d == 0).sum()), "median": d.median(),
            "mean": d.mean(), "p99": d.quantile(0.99), "max": d.max(), "gini": gini(d),
        })

    out = pd.DataFrame({label: one(g) for label, g in degrees.groupby("label")}).T
    out.index.name = "label"
    return out.astype({"n": int, "isolated": int})


def top_hubs(degrees: pd.DataFrame, label: str, k: int = 10, col: str = "degree") -> pd.DataFrame:
    sub = degrees[degrees["label"] == label]
    return sub.sort_values([col, "name"], ascending=[False, True]).head(k).reset_index(drop=True)


def coverage(rel_coverage: pd.DataFrame, node_counts: pd.DataFrame) -> pd.DataFrame:
    totals = node_counts.set_index("label")["n"]
    out = rel_coverage.copy()
    out["src_frac"] = out["n_src"] / out["src"].map(totals)
    out["dst_frac"] = out["n_dst"] / out["dst"].map(totals)
    return out


def completeness(node_props: pd.DataFrame, node_counts: pd.DataFrame) -> pd.DataFrame:
    totals = node_counts.set_index("label")["n"]
    df = node_props.copy()
    df["frac"] = (df["n_present"] - df["n_empty"]) / df["label"].map(totals)
    return df.pivot(index="label", columns="property", values="frac")


def name_quirks(degrees: pd.DataFrame) -> pd.DataFrame:
    rows = {}
    for label, g in degrees.groupby("label"):
        names = g["name"].dropna().astype(str)
        rows[label] = {
            "n": len(names),
            "all_lower": int((names == names.str.lower()).sum()),
            "starts_upper": int(names.str[:1].str.isupper().sum()),
            "non_ascii": int((~names.map(str.isascii)).sum()),
            "has_punct": int(names.map(lambda s: any(c in PUNCT for c in s)).sum()),
            "dup_names": int(names.duplicated().sum()),
        }
    out = pd.DataFrame(rows).T
    out.index.name = "label"
    return out


def cross_label_names(degrees: pd.DataFrame) -> pd.DataFrame:
    df = degrees.dropna(subset=["name"]).copy()
    df["name_lower"] = df["name"].astype(str).str.lower()
    grouped = df.groupby("name_lower")["label"].agg(lambda s: sorted(set(s)))
    grouped = grouped[grouped.map(len) >= 2]
    out = pd.DataFrame({"name_lower": grouped.index, "labels": grouped.map("|".join).values})
    return out.sort_values("name_lower").reset_index(drop=True)


def pair_scores(
    paths: pd.DataFrame,
    treatments: pd.DataFrame,
    compounds: Sequence[str],
    diseases: Sequence[str],
) -> pd.DataFrame:
    grid = pd.MultiIndex.from_product([compounds, diseases], names=["compound", "disease"])
    grid = grid.to_frame(index=False)
    counts = paths.groupby(["compound", "disease"], as_index=False)["paths"].sum()
    out = grid.merge(counts, on=["compound", "disease"], how="left")
    out["paths"] = out["paths"].fillna(0).astype(int)
    treats = treatments[treatments["rel_type"] == "TREATS_CtD"]
    treated = set(zip(treats["compound"], treats["disease"]))
    out["treated"] = [(c, d) in treated for c, d in zip(out["compound"], out["disease"])]
    return out


def metapath_auroc(paths: pd.DataFrame, treatments: pd.DataFrame, degrees: pd.DataFrame) -> float:
    """AUROC of path counts separating treated from untreated Compound x Disease pairs."""
    compounds = degrees.loc[degrees["label"] == "Compound", "id"].tolist()
    diseases = degrees.loc[degrees["label"] == "Disease", "id"].tolist()
    ps = pair_scores(paths, treatments, compounds, diseases)
    return auroc(ps.loc[ps["treated"], "paths"], ps.loc[~ps["treated"], "paths"])
