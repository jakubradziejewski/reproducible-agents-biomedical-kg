import re

import pytest

import eda_queries
import eda_report
from eda_plots import make_all
from eda_report import compute_facts, render, takeaways


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
    assert "nan" not in md.lower() and "## Key takeaways" in md


def test_main_without_cache_names_command(tmp_path, monkeypatch):
    monkeypatch.setattr(eda_queries, "CACHE_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="src/eda_queries.py"):
        eda_report.main()
    assert not (tmp_path / "figures").exists()
