"""Figures for the Hetionet exploratory analysis (matplotlib, Agg backend, PNG at 150 dpi).

Style follows the dataviz skill's reference palette (light mode): categorical hues are
assigned in fixed order, magnitude uses one blue ramp, text stays in ink colours.
Zeros on log axes are handled explicitly: log1p transforms, or zeros dropped and counted
in the legend/caption. Every figure function takes the dataset dict and an output
directory, and returns the PNG path.
"""
from collections.abc import Callable
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, LogNorm  # noqa: E402

from eda_stats import auroc, coverage, completeness, pair_scores  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
# Categorical slots 1-8 (blue, orange, aqua, yellow, magenta, green, violet, red).
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUE, ORANGE = CAT[0], CAT[1]
SEQ = LinearSegmentedColormap.from_list(
    "seq_blue", ["#cde2fb", "#6da7ec", "#256abf", "#0d366b"]
).with_extremes(bad=SURFACE)
DPI = 150


def _style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": INK_2, "axes.labelcolor": INK_2, "axes.titlecolor": INK,
        "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.labelsize": 9, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "xtick.color": INK_2, "ytick.color": INK_2, "xtick.labelsize": 8, "ytick.labelsize": 8,
        "text.color": INK, "legend.frameon": False, "legend.fontsize": 8,
        "font.family": "DejaVu Sans", "figure.dpi": 100, "savefig.dpi": DPI,
        "figure.constrained_layout.use": True,
    })


def _fig(w: float, h: float, **kw):
    return plt.subplots(figsize=(w, h), **kw)


def _save(fig, out_dir: Path, key: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{key}.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def _fmt(n: float) -> str:
    return f"{n:,.0f}"


def _label_colors(labels) -> dict[str, str]:
    """Color follows the entity: fixed by sorted label name, not by rank or panel."""
    return {lab: CAT[i % len(CAT)] for i, lab in enumerate(sorted(labels))}


def _heatmap(ax, mat: pd.DataFrame, norm, fmt: Callable[[float], str], rot: int = 45) -> None:
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    vals = np.ma.masked_invalid(mat.to_numpy(dtype=float))
    ax.imshow(vals, cmap=SEQ, norm=norm, aspect="auto")
    ax.set_xticks(range(mat.shape[1]), mat.columns, rotation=rot, ha="right" if rot else "center")
    ax.set_yticks(range(mat.shape[0]), mat.index)
    ax.tick_params(length=0)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat.iat[i, j]
            if pd.isna(v):
                continue
            dark = norm(v) > 0.55
            ax.text(j, i, fmt(v), ha="center", va="center", fontsize=7,
                    color=SURFACE if dark else INK)


def _bars(ax, names, values, fmt, log=False, color=BLUE, pad_factor=1.0):
    bars = ax.barh(names, values, color=color, height=0.65)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    if log:
        ax.set_xscale("log")
        ax.set_xlim(left=1, right=max(values) * 12)
    else:
        ax.set_xlim(right=max(values) * 1.15 * pad_factor)
    ax.bar_label(bars, labels=[fmt(v) for v in values], padding=3, fontsize=7, color=INK_2)


def fig_counts(data, out_dir: Path) -> Path:
    nodes = data["node_counts"].sort_values(["n", "label"], ascending=[False, True])
    edges = data["edge_counts"].groupby("rel_type")["n"].sum().reset_index()
    edges = edges.sort_values(["n", "rel_type"], ascending=[False, True])
    fig, (a, b) = plt.subplots(
        1, 2, figsize=(11, 0.28 * max(len(nodes), len(edges)) + 1.6),
    )
    _bars(a, nodes["label"], nodes["n"], _fmt, log=True)
    a.set_title("Nodes per label")
    a.set_xlabel("count (log scale)")
    _bars(b, edges["rel_type"], edges["n"], _fmt, log=True)
    b.set_title("Edges per relationship type")
    b.set_xlabel("count (log scale)")
    return _save(fig, out_dir, "counts")


def fig_metagraph_heatmap(data, out_dir: Path) -> Path:
    ec = data["edge_counts"]
    labels = sorted(set(ec["src"]) | set(ec["dst"]) | set(data["node_counts"]["label"]))
    mat = ec.pivot_table(index="src", columns="dst", values="n", aggfunc="sum")
    mat = mat.reindex(index=labels, columns=labels)  # absent pairs stay NaN = blank
    fig, ax = _fig(10, 8)
    _heatmap(ax, mat, LogNorm(vmin=mat.min().min(), vmax=mat.max().max()), _fmt)
    ax.set_xlabel("destination label")
    ax.set_ylabel("source label")
    ax.set_title("Edges between node labels (summed over relationship types, log colour)")
    return _save(fig, out_dir, "metagraph_heatmap")


def fig_degree_ccdf(data, out_dir: Path) -> Path:
    deg = data["degrees"]
    colors = _label_colors(deg["label"].unique())
    fig, ax = _fig(8, 6)
    for i, (label, g) in enumerate(sorted(deg.groupby("label"))):
        d = g["degree"].to_numpy()
        pos = d[d > 0]  # degree 0 cannot sit on a log axis; counted in the legend instead
        x, counts = np.unique(pos, return_counts=True)
        y = counts[::-1].cumsum()[::-1] / len(pos)
        ax.step(x, y, where="post", color=colors[label], lw=1.6,
                ls="-" if i < len(CAT) else "--",
                label=f"{label} (n={len(d):,}, 0-degree: {int((d == 0).sum()):,})")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("degree k (log scale; degree-0 nodes excluded)")
    ax.set_ylabel("P(degree >= k)  (log scale)")
    ax.set_title("Degree distribution (CCDF) per node label")
    ax.legend(loc="lower left")
    return _save(fig, out_dir, "degree_ccdf")


def fig_coverage_heatmap(data, out_dir: Path) -> Path:
    cov = coverage(data["rel_coverage"], data["node_counts"])
    cov = cov.assign(rel=cov["rel_type"] + " (" + cov["src"] + "->" + cov["dst"] + ")")
    mat = cov.set_index("rel")[["src_frac", "dst_frac"]]
    mat.columns = ["source side", "destination side"]
    fig, ax = _fig(7, 0.3 * len(mat) + 1.8)
    _heatmap(ax, mat, plt.Normalize(0, 1), lambda v: f"{v:.0%}", rot=0)
    ax.set_title("Share of nodes with an edge", loc="center")
    return _save(fig, out_dir, "coverage_heatmap")


def fig_completeness_heatmap(data, out_dir: Path) -> Path:
    mat = completeness(data["node_props"], data["node_counts"])
    fig, ax = _fig(0.55 * mat.shape[1] + 3, 0.45 * mat.shape[0] + 2.5)
    _heatmap(ax, mat, plt.Normalize(0, 1), lambda v: f"{v:.0%}", rot=60)
    ax.set_title("Property completeness (present and non-empty); blank = label lacks property")
    return _save(fig, out_dir, "completeness_heatmap")


def fig_unbiased_share(data, out_dir: Path) -> Path:
    # edge_counts, not edge_sources: UNWIND there counts multi-source edges repeatedly.
    ec = data["edge_counts"].groupby("rel_type")[["n", "n_unbiased"]].sum()
    share = (ec["n_unbiased"] / ec["n"]).rename("share").reset_index()
    share = share.sort_values(["share", "rel_type"], ascending=[False, True])
    fig, ax = _fig(8, 0.3 * len(share) + 1.4)
    _bars(ax, share["rel_type"], share["share"], lambda v: f"{v:.1%}")
    ax.set_xlim(0, 1.12)
    ax.set_xlabel("share of edges flagged unbiased (n_unbiased / n)")
    ax.set_title("Unbiased share of edges per relationship type")
    return _save(fig, out_dir, "unbiased_share")


def fig_treatments_per_disease(data, out_dir: Path) -> Path:
    dp = data["disease_profile"].copy()
    dp["total"] = dp["treats"] + dp["palliates"]
    dp = dp.sort_values(["total", "name"], ascending=[False, True]).reset_index(drop=True)
    fig, ax = _fig(8, 0.15 * len(dp) + 1.5)
    y = np.arange(len(dp))
    ax.barh(y, dp["treats"], color=BLUE, height=0.75, edgecolor=SURFACE, lw=0.6, label="treats")
    ax.barh(y, dp["palliates"], left=dp["treats"], color=ORANGE, height=0.75,
            edgecolor=SURFACE, lw=0.6, label="palliates")
    zero = dp["total"] == 0
    ax.scatter(np.zeros(zero.sum()), y[zero], marker="x", s=14, color=INK, lw=1, zorder=3,
               label=f"no treatment or palliation (n={int(zero.sum())})")
    ax.set_yticks(y, dp["name"], fontsize=5.5)
    ax.set_ylim(len(dp) - 0.5, -0.5)
    ax.set_xlim(left=-0.5)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("number of compounds")
    ax.set_title("Compounds treating or palliating each disease")
    ax.legend(loc="lower right")
    return _save(fig, out_dir, "treatments_per_disease")


def _spearman(x: pd.Series, y: pd.Series) -> float:
    return float(x.rank().corr(y.rank()))  # Pearson on ranks; no scipy needed


def fig_gene_study_bias(data, out_dir: Path) -> Path:
    g = data["gene_profile"]
    rho = _spearman(g["bound_by"], g["interacts"])
    fig, ax = _fig(8, 6.5)
    ax.scatter(np.log1p(g["bound_by"]), np.log1p(g["interacts"]), s=6, color=BLUE,
               alpha=0.25, linewidths=0)
    hubs = g.sort_values(["interacts", "name"], ascending=[False, True]).head(5)
    ax.scatter(np.log1p(hubs["bound_by"]), np.log1p(hubs["interacts"]), s=22, color=ORANGE,
               edgecolor=SURFACE, linewidths=0.8, zorder=3)
    for k, (_, r) in enumerate(hubs.iterrows()):
        ax.annotate(r["name"], (np.log1p(r["bound_by"]), np.log1p(r["interacts"])),
                    xytext=(6, -3 - 9 * k if k else 6), textcoords="offset points",
                    fontsize=8, color=INK, arrowprops={"arrowstyle": "-", "color": INK_2, "lw": 0.6})
    ax.set_xlabel("log1p(compounds binding the gene)")
    ax.set_ylabel("log1p(gene-gene interactions)")
    ax.set_title(f"Gene study bias (Spearman rho = {rho:.2f}); top 5 hubs labelled")
    return _save(fig, out_dir, "gene_study_bias")


def fig_edge_numeric(data, out_dir: Path) -> Path:
    groups = list(data["edge_numeric"].groupby(["rel_type", "property"]))
    ncols = min(3, len(groups))
    nrows = -(-len(groups) // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.2 * nrows), squeeze=False)
    for ax, ((rel, prop), g) in zip(axes.flat, groups):
        v = g["value"].to_numpy(dtype=float)
        lo, hi = np.quantile(v, [0.005, 0.995])
        if hi <= lo:
            lo, hi = lo - 0.5, hi + 0.5
        ax.hist(v, bins=50, range=(lo, hi), color=BLUE, edgecolor=SURFACE, lw=0.3)
        ax.set_title(f"{rel}.{prop}", fontsize=9)
        ax.set_xlabel(f"{prop} (axis spans 0.5-99.5th pct; max {v.max():.3g})")
        ax.set_ylabel("edges")
    for ax in list(axes.flat)[len(groups):]:
        ax.set_visible(False)
    return _save(fig, out_dir, "edge_numeric")


def fig_compound_profile(data, out_dir: Path) -> Path:
    cp, pc = data["compound_profile"], data["pharm_classes"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [3, 2]})
    a.hist(np.log1p(cp["side_effects"]), bins=40, color=BLUE, edgecolor=SURFACE, lw=0.3)
    a.set_xlabel("log1p(side effects per compound)")
    a.set_ylabel("compounds")
    a.set_title("Side effects per compound")
    counts = pc.groupby("class_type").size().sort_values(ascending=False)
    bars = b.bar(counts.index, counts.values, color=BLUE, width=0.6)
    b.bar_label(bars, padding=2, fontsize=8, color=INK_2)
    b.grid(axis="x", visible=False)
    b.set_ylim(top=counts.max() * 1.12)
    b.set_ylabel("pharmacologic classes")
    b.set_title("Pharmacologic classes per class type")
    b.tick_params(axis="x", labelsize=7)
    b.set_xticks(range(len(counts)), [t.replace(" ", "\n", 1) for t in counts.index])
    return _save(fig, out_dir, "compound_profile")


def fig_metapath_signal(data, out_dir: Path) -> Path:
    deg = data["degrees"]
    compounds = deg.loc[deg["label"] == "Compound", "id"].tolist()
    diseases = deg.loc[deg["label"] == "Disease", "id"].tolist()
    panels = [("cbgad_paths", "CbGaD (compound-binds-gene-associates-disease)"),
              ("crctd_paths", "CrCtD (compound-resembles-compound-treats-disease)")]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for ax, (key, name) in zip(axes, panels):
        ps = pair_scores(data[key], data["treatments"], compounds, diseases)
        auc = auroc(ps.loc[ps["treated"], "paths"], ps.loc[~ps["treated"], "paths"])
        for treated, color, lab in [(True, BLUE, "treated"), (False, ORANGE, "untreated")]:
            x = np.sort(np.log1p(ps.loc[ps["treated"] == treated, "paths"].to_numpy()))
            ax.step(x, np.arange(1, len(x) + 1) / len(x), where="post", color=color, lw=1.8,
                    label=f"{lab} pairs (n={len(x):,})")
        ax.set_xlabel("log1p(path count); 0 = no path")
        ax.set_title(f"{name}\nAUROC = {auc:.3f}", fontsize=9)
        ax.legend(loc="lower right")
    axes[0].set_ylabel("cumulative share of pairs")
    return _save(fig, out_dir, "metapath_signal")


FIGURES: dict[str, Callable[[dict[str, pd.DataFrame], Path], Path]] = {
    "counts": fig_counts,
    "metagraph_heatmap": fig_metagraph_heatmap,
    "degree_ccdf": fig_degree_ccdf,
    "coverage_heatmap": fig_coverage_heatmap,
    "completeness_heatmap": fig_completeness_heatmap,
    "unbiased_share": fig_unbiased_share,
    "treatments_per_disease": fig_treatments_per_disease,
    "gene_study_bias": fig_gene_study_bias,
    "edge_numeric": fig_edge_numeric,
    "compound_profile": fig_compound_profile,
    "metapath_signal": fig_metapath_signal,
}


def make_all(data: dict[str, pd.DataFrame], out_dir: Path) -> dict[str, Path]:
    _style()
    return {key: fn(data, Path(out_dir)) for key, fn in FIGURES.items()}
