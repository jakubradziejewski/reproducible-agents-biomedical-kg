import json

import pandas as pd
import pytest

import eda_probe
import eda_queries


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(eda_probe, "PROBE_DIR", tmp_path / "probes")
    monkeypatch.setattr(eda_probe, "LOG_PATH", tmp_path / "probes.jsonl")
    monkeypatch.setattr(eda_queries, "cypher", lambda q: pd.DataFrame({"a": [1, 2, 3]}))
    return tmp_path


def _log(tmp_path) -> list[dict]:
    lines = (tmp_path / "probes.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_probe_logs_and_caches(sandbox):
    df = eda_probe.probe("s1", "three rows expected", "MATCH (n) RETURN n LIMIT 3")
    (entry,) = _log(sandbox)
    assert entry["slug"] == "s1" and entry["rows"] == len(df) == 3
    assert entry["hypothesis"] == "three rows expected" and "ts" in entry and "query" in entry
    assert (sandbox / "probes" / "s1.csv").exists()


def test_probe_budget_enforced(sandbox, monkeypatch):
    monkeypatch.setattr(eda_probe, "MAX_PROBES", 2)
    eda_probe.probe("a", "h", "MATCH (n) RETURN n")
    eda_probe.probe("b", "h", "MATCH (n) RETURN n")
    with pytest.raises(RuntimeError, match="budget"):
        eda_probe.probe("c", "h", "MATCH (n) RETURN n")
    assert len(_log(sandbox)) == 2


def test_probe_failed_query_counts(sandbox, monkeypatch):
    def boom(q):
        raise RuntimeError("timeout")

    monkeypatch.setattr(eda_queries, "cypher", boom)
    monkeypatch.setattr(eda_probe, "MAX_PROBES", 1)
    with pytest.raises(RuntimeError, match="timeout"):
        eda_probe.probe("bad", "h", "MATCH (n) RETURN n")
    (entry,) = _log(sandbox)
    assert entry["error"] == "timeout" and entry["rows"] is None
    assert not (sandbox / "probes" / "bad.csv").exists()
    with pytest.raises(RuntimeError, match="budget"):
        eda_probe.probe("next", "h", "MATCH (n) RETURN n")


def test_probe_requires_hypothesis(sandbox):
    with pytest.raises(ValueError):
        eda_probe.probe("x", "", "MATCH (n) RETURN n")
    with pytest.raises(ValueError):
        eda_probe.probe("x", "   ", "MATCH (n) RETURN n")
    eda_probe.probe("x", "h", "MATCH (n) RETURN n")
    with pytest.raises(ValueError, match="duplicate"):
        eda_probe.probe("x", "h", "MATCH (n) RETURN n")
    assert len(_log(sandbox)) == 1
