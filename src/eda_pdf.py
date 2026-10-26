"""Build reports/eda/REPORT.pdf, a 2-page plain-language summary of reports/eda/REPORT.md.

The figures are compact redraws of the report figures, made from the data/eda cache. The prose
quotes numbers from REPORT.md by hand, so re-check it if the cache changes.
Run from the repo root:  uv run python src/eda_pdf.py   (offline; needs the cache).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate,
                                Spacer, Table)


D = Path("data/eda")
OUT = Path("reports/eda/REPORT.pdf")
FIG = Path("reports/eda/pdf_figures")

BLUE, ORANGE, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#222222", "#666666", "#e3e3e3"
plt.rcParams.update({
    "font.size": 7, "axes.titlesize": 7.5, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": INK,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.5, "axes.axisbelow": True, "figure.dpi": 300, "savefig.dpi": 300,
})
CM = 1 / 2.54


def fig_counts():
    nodes = pd.read_csv(D / "node_counts.csv").sort_values("n")
    edges = pd.read_csv(D / "edge_counts.csv").sort_values("n")
    fig, (a, b) = plt.subplots(1, 2, figsize=(17.4 * CM, 7.7 * CM),
                               gridspec_kw={"width_ratios": [1, 1.25], "wspace": 0.55})
    for ax, df, col, title in [(a, nodes, "label", "Figure 1a. Nodes per kind"),
                               (b, edges, "rel_type", "Figure 1b. Edges per type")]:
        ax.barh(df[col], df.n, color=BLUE, height=0.7)
        ax.set_xscale("log")
        ax.grid(axis="y", visible=False)
        ax.set_title(title)
        ax.set_xlabel("count (log scale)")
        ax.tick_params(axis="y", length=0, labelsize=6.3)
        for y, v in enumerate(df.n):
            ax.text(v * 1.15, y, f"{v:,}", va="center", fontsize=5.6, color=MUTED)
        ax.set_xlim(1, df.n.max() * 12)
        ax.margins(y=0.01)
    for lbl in b.get_yticklabels():
        if lbl.get_text() in ("TREATS_CtD", "PALLIATES_CpD"):
            lbl.set_color(ORANGE); lbl.set_fontweight("bold")
    for lbl in a.get_yticklabels():
        if lbl.get_text() in ("Disease", "Compound"):
            lbl.set_color(ORANGE); lbl.set_fontweight("bold")
    fig.savefig(FIG / "counts.png", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def fig_treatments():
    d = pd.read_csv(D / "disease_profile.csv")
    d["total"] = d.treats + d.palliates
    bins = [(0, 0, "0"), (1, 4, "1–4"), (5, 9, "5–9"), (10, 19, "10–19"), (20, 39, "20–39"), (40, 999, "≥40")]
    counts = [((d.total >= lo) & (d.total <= hi)).sum() for lo, hi, _ in bins]
    fig, (a, b) = plt.subplots(1, 2, figsize=(17.4 * CM, 4.4 * CM),
                               gridspec_kw={"width_ratios": [1.15, 1.2], "wspace": 0.7})
    cols = [ORANGE] + [BLUE] * (len(bins) - 1)
    a.bar([x for *_, x in bins], counts, color=cols, width=0.7)
    a.tick_params(axis="x", labelsize=6.3)
    for x, c in enumerate(counts):
        a.text(x, c + 1, str(c), ha="center", fontsize=6.5, color=INK)
    a.set_title("Figure 2a. Diseases by number of drugs")
    a.set_xlabel("drugs that treat or palliate it")
    a.set_ylabel("diseases")
    a.grid(axis="x", visible=False)
    a.set_ylim(0, max(counts) * 1.18)

    top = d.sort_values(["total", "name"], ascending=[False, True]).head(10)[::-1]
    b.barh(top.name, top.treats, color=BLUE, height=0.7, label="treats")
    b.barh(top.name, top.palliates, left=top.treats, color=ORANGE, height=0.7, label="palliates")
    b.set_title("Figure 2b. Ten most-treated diseases")
    b.set_xlabel("number of compounds")
    b.grid(axis="y", visible=False)
    b.tick_params(axis="y", length=0)
    b.legend(frameon=False, loc="lower right", fontsize=6.5)
    fig.savefig(FIG / "treatments.png", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def fig_bias_and_completeness():
    g = pd.read_csv(D / "gene_profile.csv")
    fig, ax = plt.subplots(figsize=(8.4 * CM, 6.3 * CM))
    rng = np.random.default_rng(0)
    x = np.log1p(g.bound_by) + rng.uniform(-0.12, 0.12, len(g)) * (g.bound_by < 15)
    ax.scatter(x, np.log1p(g.interacts), s=1.5, color=BLUE, alpha=0.25, linewidths=0)
    ticks = [0, 1, 3, 10, 30, 100, 300]
    ax.set_xticks(np.log1p(ticks), ticks)
    ax.set_yticks(np.log1p([0, 10, 100, 1000, 9000]), [0, 10, 100, "1,000", "9,000"])
    for _, r in g.nlargest(3, "interacts").iterrows():
        ax.annotate(r["name"], (np.log1p(r.bound_by), np.log1p(r.interacts)), xytext=(6, -2),
                    textcoords="offset points", fontsize=8, color=INK)
    ax.set_xlabel("compounds binding the gene (log scale)")
    ax.set_ylabel("gene-gene interactions (log scale)")
    ax.set_title("Figure 3. Gene interactions vs. binding drugs")
    fig.savefig(FIG / "bias.png", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)

    p = pd.read_csv(D / "node_props.csv")
    nodes = pd.read_csv(D / "node_counts.csv").set_index("label").n
    p["share"] = (p.n_present - p.n_empty) / p.label.map(nodes)
    m = p.pivot(index="label", columns="property", values="share")
    fig, ax = plt.subplots(figsize=(8.8 * CM, 6.9 * CM))
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list("b", ["#cfe0f5", "#0d3569"])
    ax.imshow(m.values, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(m.shape[1]), m.columns, rotation=55, ha="right", fontsize=6.8)
    ax.set_yticks(range(m.shape[0]), m.index, fontsize=6.8)
    ax.grid(False)
    ax.set_xticks(np.arange(-.5, m.shape[1]), minor=True)
    ax.set_yticks(np.arange(-.5, m.shape[0]), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.2)
    ax.tick_params(which="both", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            if not np.isnan(v) and v < 0.9995:
                ax.text(j, i, f"{v*100:.1f}" if v > .99 else f"{v:.0%}", ha="center", va="center",
                        fontsize=6.8 if v < .99 else 5.6, color="white" if v > .5 else INK, fontweight="bold")
    ax.set_title("Figure 4. Share of nodes with each property")
    fig.savefig(FIG / "completeness.png", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def img(name, width_cm):
    path = FIG / name
    from PIL import Image as PI
    w, h = PI.open(path).size
    return Image(str(path), width=width_cm * cm, height=width_cm * cm * h / w)


def build():
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=8.8, leading=11.4, alignment=TA_JUSTIFY,
                          textColor=colors.HexColor(INK), spaceAfter=3)
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=18,
                        alignment=0, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=13,
                        textColor=colors.HexColor("#0d3569"), spaceBefore=6, spaceAfter=2, alignment=0)
    bul = ParagraphStyle("u", parent=base, leftIndent=9, bulletIndent=1, spaceAfter=1.8)

    P = lambda t, s=base: Paragraph(t, s)
    B = lambda t: Paragraph(t, bul, bulletText="•")
    PAD = lambda: Spacer(1, 8)

    def framed(flowable, pad=6):
        return Table([[flowable]], hAlign="LEFT", style=[("TOPPADDING", (0, 0), (-1, -1), pad),
                                          ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
                                          ("LEFTPADDING", (0, 0), (-1, -1), pad),
                                          ("RIGHTPADDING", (0, 0), (-1, -1), pad)])

    def side_by_side(left, right, widths):
        return Table([[left, right]], colWidths=widths, hAlign="LEFT",
                     style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (1, 0), (1, 0), 12)])

    s = [
        P("Exploratory Data Analysis", h1),

        P("1. The dataset", h2),
        P("Hetionet v1.0 is a biomedical knowledge graph. Its nodes are things like genes, drugs (called "
          "compounds), diseases, side effects and biological processes, and its edges are facts that link "
          "them, for example that a compound treats a disease or that a gene takes part in a process. It was "
          "put together in 2017 from dozens of public databases, with the goal of finding existing drugs that "
          "could be used for other diseases (drug repurposing). In our benchmark, AI agents answer "
          "repurposing questions by querying this graph, so the way the data is shaped affects how hard the "
          "questions are."),

        P("2. Basic facts", h2),
        B("The graph has 47,031 nodes of 11 kinds and 2,250,197 edges of 24 types."),
        B("It is very imbalanced. There are 20,945 gene nodes but only 137 diseases, and 559,504 edges "
          "saying a gene takes part in a process but only 390 saying a compound palliates a disease."),
        B("Very little of it is about treatment. Only 1,145 edges (0.05%) say that a drug treats (755) or "
          "palliates (390) a disease, while 93% of all edges involve a gene."),
        B("1,873 nodes have no edges at all, and 1,800 of them are genes. Of these genes, 1,463 (81.3%) have "
          "names starting with LOC, which is a placeholder for genes that have not been named yet. In fact, "
          "94.5% of all 1,548 LOC genes have no edges."),
        B("279 names are used by more than one kind of node. For example, abdominal pain is both a side "
          "effect and a symptom, and ache is both a gene and a side effect, so a query that matches only on "
          "the name can return the wrong node."),
        P("Figure 1 shows the imbalance. The left panel counts nodes of each kind and the right panel counts "
          "edges of each type, with the treatment-related ones in orange. The axis is on a log scale, where "
          "each step is ten times larger than the previous one, so a bar that looks only somewhat shorter can "
          "stand for a hundred times fewer items."),
        PAD(), framed(img("counts.png", 16.6)), PAD(),

        P("3. Treatments", h2),
        P("Treatment edges are what repurposing questions are about, so we checked how they are spread over "
          "the 137 diseases. 46 of them (34%) have no drug that treats or palliates them, so for these the "
          "right answer to a question like which drugs treat X is that there are none. The other diseases are "
          "very uneven: hypertension has 70 drugs, while many have only one or two. No compound both treats "
          "and palliates the same disease."),
        P("Hetionet's side-effect edges partly overlap with its treatment edges, so a drug listed as "
          "causing a condition may actually be one that treats it. 36 treated diseases have the same name as a "
          "side effect. Of the 441 treatment edges going into them, 65 (14.7%) come from a compound that is "
          "also listed as causing that side effect. That is 1.9 times the 34.3 we would expect if treating "
          "compounds caused it as often as all 1,552 compounds do."),

        P("In Figure 2, the left panel groups diseases by how many drugs they have, and the orange bar is the "
          "46 diseases with none. The right panel shows the ten diseases with the most drugs, split into drugs "
          "that treat the disease (blue) and drugs that only relieve its symptoms (orange). Some diseases, such "
          "as migraine and multiple sclerosis, have mostly the second kind."),
        PAD(), framed(img("treatments.png", 16.6)), PAD(),
        P("4. Study bias", h2),
    ]
    s.append(side_by_side(
        [P("Some genes have thousands of edges mainly because they are studied a lot. If this bias carried "
           "over to drug data, genes with many interactions would also be bound by many drugs. Figure 3 checks "
           "this. Each dot is one gene, placed by how many drugs bind it (horizontal) and how many other genes "
           "it interacts with (vertical), both on log scales. Dots with small counts are spread out a little "
           "so they do not sit on top of each other."),
         P("There is no clear upward trend. The rank correlation (Spearman rho) is 0.13, where 0 means no "
           "relation and 1 means the two rankings match exactly. The most connected genes, such as UBC with "
           "9,372 edges, have no binding drugs at all, and 92% of genes are bound by none.")],
        framed(img("bias.png", 7.9)), [9.0 * cm, 8.5 * cm]))

    s.append(P("5. Completeness", h2))
    s.append(side_by_side(
        framed(img("completeness.png", 8.1)),
        [P("Each kind of node has a few properties, such as a name, an identifier, a source database or, for "
           "genes, a chromosome. Figure 4 shows how often each property is filled in. Rows are node kinds and "
           "columns are properties. A dark cell means every node of that kind has the property, a lighter "
           "cell with a number marks a gap, and a white cell means that kind of node does not have the "
           "property at all."),
         P("The data is almost complete. Only 3 of the 62 combinations have gaps. Pathway web links are "
           "present for just 16% of pathways and the tissue identifier (bto_id) for 62% of anatomy nodes. Gene "
           "chromosomes are 99.8% filled in, but the 37 genes without one, and the 18 genes listed as X|Y, "
           "would be missed by a filter like chromosome = 'X'.")],
        [8.7 * cm, 8.8 * cm]))

    s.append(P("6. Graph structure", h2))
    sym = pd.read_csv(D / "symmetry.csv")
    rows = [["Edge type", "Self-loops", "Two-way pairs", "Duplicates"]] + \
        [[r.rel_type, f"{r.self_loops:,}", f"{r.reciprocal_pairs:,}", f"{r.parallel_pairs:,}"] for r in sym.itertuples()]
    tbl = Table(rows, colWidths=[3.6 * cm, 1.8 * cm, 2.2 * cm, 1.9 * cm], style=[
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.4), ("FONT", (0, 1), (-1, -1), "Helvetica", 7.4),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(MUTED)),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.HexColor(GRID)),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)])
    s.append(side_by_side(
        P("For the edge types that connect two nodes of the same kind, we looked for edges from a node to "
          "itself, pairs stored in both directions (A to B and B to A) and repeated edges. The table shows "
          "that none of these occur, except for 1,689 pairs of genes that regulate each other, which is "
          "plausible biology. This also means that two-way facts like gene interactions are stored in one "
          "direction only, so a query has to ignore direction to find all of a gene's partners."),
        framed(tbl), [7.4 * cm, 10.1 * cm]))

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=1.7 * cm, rightMargin=1.7 * cm,
                            topMargin=1.3 * cm, bottomMargin=1.2 * cm, title="Exploratory Data Analysis",
                            author="Adam Mazur")
    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    print(OUT)


def footer(canv, doc):
    canv.setFont("Helvetica", 7)
    canv.setFillColor(colors.HexColor(MUTED))
    canv.drawRightString(A4[0] - 1.7 * cm, 0.7 * cm, f"{doc.page} / 2")


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig_counts()
    fig_treatments()
    fig_bias_and_completeness()
    build()


if __name__ == "__main__":
    main()
