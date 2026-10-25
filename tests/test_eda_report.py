import re

import pandas as pd
import pytest

import eda_queries
import eda_report
from eda_plots import make_all
from eda_report import Finding, compute_facts, render, takeaways


def test_compute_facts_on_tiny_data(tiny_data):
    f = compute_facts(tiny_data)
    assert f["n_nodes"] == len(tiny_data["degrees"])
    assert f["diseases_no_treatment"] >= 1 and 0.0 <= f["auroc_cbgad"] <= 1.0


def test_takeaways_are_numeric_and_bounded(tiny_data):
    t = takeaways(compute_facts(tiny_data))
    assert 8 <= len(t) <= 12 and all(re.search(r"\d", s) for s in t)


def test_render_links_every_figure_and_has_no_nan(tiny_data, tmp_path):
    figs = make_all(tiny_data, tmp_path / "figures")
    md = render(tiny_data, compute_facts(tiny_data), figs)
    assert all(f"figures/{p.name}" in md for p in figs.values())
    assert not re.search(r"\bnan\b", md, re.I) and "## Key takeaways" in md


def test_main_without_cache_names_command(tmp_path, monkeypatch):
    monkeypatch.setattr(eda_queries, "CACHE_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="src/eda_queries.py"):
        eda_report.main()
    assert not (tmp_path / "figures").exists()


def test_render_without_findings_has_no_section_5(tiny_data, tmp_path):
    figs = make_all(tiny_data, tmp_path / "figures")
    assert "## 5." not in render(tiny_data, compute_facts(tiny_data), figs)


def test_render_with_finding(tiny_data, tmp_path, monkeypatch):
    finding = Finding("x", "X", "unexplained", "finding_x", lambda df: f"{len(df)} odd rows")
    monkeypatch.setattr(eda_report, "FINDINGS", [finding])
    tiny_data["finding_x"] = pd.DataFrame({"a": [1, 2]})
    figs = make_all(tiny_data, tmp_path / "figures")
    md = render(tiny_data, compute_facts(tiny_data), figs)
    assert "## 5. Unexpected findings" in md and "unexplained" in md
    section_5 = md.split("## 5. Unexpected findings")[1]
    takeaways_part = md.split("## Key takeaways")[1].split("## 1.")[0]
    assert "2 odd rows" in section_5 and "2 odd rows" in takeaways_part


def test_findings_within_limit_and_registered():
    assert len(eda_report.FINDINGS) <= eda_report.MAX_FINDINGS == 3
    for f in eda_report.FINDINGS:
        assert f.dataset == f"finding_{f.slug}" and f.dataset in eda_queries.DATASETS
