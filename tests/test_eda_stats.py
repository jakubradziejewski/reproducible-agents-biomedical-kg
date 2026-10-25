import string

import pandas as pd
import pytest

import eda_queries
from db import is_read_only
from eda_stats import (
    auroc, completeness, coverage, cross_label_names, degree_summary, gini,
    name_quirks, pair_scores, top_hubs,
)


def test_gini_equal_is_zero():
    assert gini([5, 5, 5, 5]) == 0


def test_gini_one_holds_all():
    assert gini([0, 0, 0, 1]) == pytest.approx(0.75)


def test_gini_all_zero_is_zero():
    assert gini([0, 0]) == 0.0


def test_auroc_perfect_and_ties():
    assert auroc([3, 4], [1, 2]) == 1.0
    assert auroc([1, 2], [3, 4]) == 0.0
    assert auroc([1, 1], [1, 1]) == 0.5


def _genes(rows):
    return pd.DataFrame(rows, columns=["label", "id", "name", "degree"])


def test_top_hubs_ties_alphabetical():
    df = _genes([("Gene", "1", "B", 5), ("Gene", "2", "A", 5), ("Gene", "3", "C", 9),
                 ("Disease", "d", "Z", 99)])
    assert list(top_hubs(df, "Gene")["name"]) == ["C", "A", "B"]
    assert list(top_hubs(df, "Gene", k=2)["name"]) == ["C", "A"]


def test_degree_summary_counts_isolated():
    df = _genes([("Gene", str(i), f"g{i}", d) for i, d in enumerate([0, 0, 3, 7])])
    s = degree_summary(df)
    assert s.loc["Gene", "isolated"] == 2
    assert s.loc["Gene", "max"] == 7
    assert s.loc["Gene", "n"] == 4
    assert list(s.columns) == ["n", "isolated", "median", "mean", "p99", "max", "gini"]


def test_coverage_fractions():
    rc = pd.DataFrame({"rel_type": ["TREATS_CtD"], "src": ["Compound"], "dst": ["Disease"],
                       "n_src": [50], "n_dst": [10]})
    nc = pd.DataFrame({"label": ["Compound", "Disease"], "n_labels": [1, 1], "n": [100, 40]})
    out = coverage(rc, nc)
    assert out.loc[0, "src_frac"] == 0.5
    assert out.loc[0, "dst_frac"] == 0.25


def test_completeness_counts_empty_as_missing():
    props = pd.DataFrame({"label": ["Gene"], "property": ["description"],
                          "n_present": [10], "n_empty": [4]})
    nc = pd.DataFrame({"label": ["Gene"], "n_labels": [1], "n": [10]})
    assert completeness(props, nc).loc["Gene", "description"] == pytest.approx(0.6)


def test_name_quirks():
    names = ["multiple sclerosis", "Crohn's disease", "café", "x", "x"]
    df = _genes([("Disease", str(i), n, 1) for i, n in enumerate(names)])
    q = name_quirks(df).loc["Disease"]
    assert (q["n"], q["all_lower"], q["starts_upper"]) == (5, 4, 1)
    assert (q["non_ascii"], q["has_punct"], q["dup_names"]) == (1, 1, 1)


def test_cross_label_names():
    df = _genes([("Disease", "1", "asthma", 1), ("Symptom", "2", "Asthma", 1),
                 ("Gene", "3", "solo", 1)])
    out = cross_label_names(df)
    assert len(out) == 1
    assert out.iloc[0]["name_lower"] == "asthma"
    assert out.iloc[0]["labels"] == "Disease|Symptom"


def test_pair_scores_fills_zero_and_marks_treated():
    paths = pd.DataFrame({"compound": ["C1"], "disease": ["D1"], "paths": [3]})
    tr = pd.DataFrame({"compound": ["C2", "C1"], "disease": ["D1", "D1"],
                       "rel_type": ["TREATS_CtD", "PALLIATES_CpD"]})
    out = pair_scores(paths, tr, ["C1", "C2"], ["D1"]).set_index("compound")
    assert len(out) == 2
    assert out.loc["C2", "paths"] == 0
    assert bool(out.loc["C2", "treated"]) is True
    assert bool(out.loc["C1", "treated"]) is False
    assert out.loc["C1", "paths"] == 3


def test_all_dataset_queries_read_only():
    qs = [v for k, v in vars(eda_queries).items() if k.endswith("_Q") and isinstance(v, str)]
    assert len(qs) >= 10
    for q in qs:
        fields = {f for _, f, _, _ in string.Formatter().parse(q) if f}
        assert is_read_only(q.format(**dict.fromkeys(fields, "DUMMY"))), q
