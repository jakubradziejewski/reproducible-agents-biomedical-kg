import warnings

import pytest

from eda_plots import FIGURES, make_all


@pytest.mark.parametrize("key", sorted(FIGURES))
def test_figure_writes_png(key, tiny_data, tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # zeros on log axes must not warn
        path = FIGURES[key](tiny_data, tmp_path)
    assert path == tmp_path / f"{key}.png" and path.stat().st_size > 1000


def test_make_all_returns_every_figure(tiny_data, tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert set(make_all(tiny_data, tmp_path)) == set(FIGURES)


def test_figures_registry_complete():
    assert set(FIGURES) == {"counts", "metagraph_heatmap", "degree_ccdf", "coverage_heatmap",
        "completeness_heatmap", "unbiased_share", "treatments_per_disease", "gene_study_bias",
        "edge_numeric", "compound_profile", "metapath_signal"}
