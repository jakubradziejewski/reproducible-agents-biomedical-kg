import pandas as pd
import pytest

import eda_queries


def test_fetch_caches_and_refresh_rebuilds(tmp_path, monkeypatch):
    monkeypatch.setattr(eda_queries, "CACHE_DIR", tmp_path)
    calls = []

    def builder():
        calls.append(1)
        return pd.DataFrame({"a": [1]})

    monkeypatch.setitem(eda_queries.DATASETS, "x", builder)
    eda_queries.fetch("x")
    eda_queries.fetch("x")
    assert len(calls) == 1
    eda_queries.fetch("x", refresh=True)
    assert len(calls) == 2


def test_fetch_writes_nothing_on_connection_error(tmp_path, monkeypatch):
    monkeypatch.setattr(eda_queries, "CACHE_DIR", tmp_path)

    def builder():
        raise ConnectionError("down")

    monkeypatch.setitem(eda_queries.DATASETS, "x", builder)
    with pytest.raises(ConnectionError):
        eda_queries.fetch("x")
    assert not any(tmp_path.iterdir())


def test_roundtrip_keeps_ids_and_na_names(tmp_path, monkeypatch):
    monkeypatch.setattr(eda_queries, "CACHE_DIR", tmp_path)
    monkeypatch.setitem(
        eda_queries.DATASETS, "x",
        lambda: pd.DataFrame({"id": [1, "DB01"], "name": ["NA", "NAN"]}),
    )
    eda_queries.fetch("x")
    df = eda_queries.read_cached("x")
    assert list(df["id"]) == ["1", "DB01"]
    assert list(df["name"]) == ["NA", "NAN"]


def test_cypher_raises_on_error_dict(monkeypatch):
    monkeypatch.setattr(eda_queries, "run_cypher", lambda q, max_rows=None: {"error": "boom"})
    with pytest.raises(RuntimeError, match="boom"):
        eda_queries.cypher("MATCH (n) RETURN n")


def test_cypher_rejects_list_cells(monkeypatch):
    res = {"columns": ["s"], "rows": [{"s": ["a", "b"]}], "total_rows": 1, "truncated": False}
    monkeypatch.setattr(eda_queries, "run_cypher", lambda q, max_rows=None: res)
    with pytest.raises(TypeError):
        eda_queries.cypher("MATCH (n) RETURN n")


def test_load_all_missing_names_dataset_and_command(tmp_path, monkeypatch):
    monkeypatch.setattr(eda_queries, "CACHE_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="node_counts") as ei:
        eda_queries.load_all(["node_counts"])
    assert "src/eda_queries.py" in str(ei.value)
