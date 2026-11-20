"""Deterministic checks on a generated Cypher query before it is run, inspired by CYGNET (Tomczak, 2026).

Three gates, cheapest first, the same for every model:
1. vocabulary  every :Label, [:TYPE] and property must exist in data/schema.json            (no network)
2. direction   (a:L1)-[:TYPE]->(b:L2) must follow the direction stored for TYPE              (no network)
3. explain     the Neo4j 3.5 server parses and plans the query with EXPLAIN; nothing is executed

CYGNET's ANTLR gate and mirror graph are left out on purpose; the reasons are in
notebooks/preprocessing/01_t2css_pipeline.ipynb. The patterns below are regular expressions, not a
parser: they cover ordinary MATCH patterns and can miss labels hidden inside nested expressions.
The EXPLAIN gate is the authority for syntax.
"""
import re

from db import _post, is_read_only, run_cypher

_STRINGS = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_TOKEN = re.compile(r"(?P<node>\([^()]*\))|(?P<rel><?-\s*(?:\[[^\]]*\])?\s*->?)")
_NODE = re.compile(r"\s*(?P<var>[A-Za-z_]\w*)?\s*(?P<labels>(?::\s*`?\w+`?\s*)*)(?P<rest>.*)", re.S)
_PROP = re.compile(r"(?<![\w.`])([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b(?!\s*\()")


def _parse(query: str) -> list[dict]:
    """Node and relationship tokens in the order they appear, with string literals blanked."""
    text = _STRINGS.sub("''", query)
    out = []
    for m in _TOKEN.finditer(text):
        if m.group("node"):
            n = _NODE.match(m.group("node")[1:-1])
            out.append({
                "kind": "node", "start": m.start(), "end": m.end(), "var": n.group("var"),
                "labels": re.findall(r"\w+", n.group("labels")),
                "map_keys": re.findall(r"[{,]\s*`?(\w+)`?\s*:", n.group("rest")),
            })
        else:
            raw = m.group("rel")
            inner = raw[raw.index("[") + 1: raw.rindex("]")] if "[" in raw else ""
            head = re.split(r"[*{]", inner.split(":", 1)[1])[0] if ":" in inner else ""
            out.append({
                "kind": "rel", "start": m.start(), "end": m.end(),
                "types": [t for t in re.findall(r"\w+", head)],
                "left": raw.startswith("<"), "right": raw.endswith(">"),
            })
    for i, t in enumerate(out):  # a node belongs to a pattern only if it touches a relationship or has a label
        if t["kind"] == "rel":
            for j in (i - 1, i + 1):
                if 0 <= j < len(out) and out[j]["kind"] == "node" and not text[min(out[j]["end"], t["end"]):max(out[j]["start"], t["start"])].strip():
                    out[j]["in_pattern"] = True
    return out


def _bindings(tokens: list[dict]) -> dict[str, str]:
    return {t["var"]: t["labels"][0] for t in tokens if t["kind"] == "node" and t["var"] and t["labels"]}


def check_vocabulary(query: str, schema: dict) -> list[str]:
    """Gate 1: names that do not exist in the schema, and anything that is not read-only."""
    problems = [] if is_read_only(query) else ["write clause or procedure call: only read-only Cypher is allowed"]
    tokens, labels = _parse(query), schema["labels"]
    types = {t["type"]: t for t in schema["triples"]}
    keys, bound = set(schema["property_keys"]), _bindings(tokens)
    for t in tokens:
        if t["kind"] == "node":
            problems += [f"unknown label :{lab}" for lab in t["labels"] if lab not in labels]
            if t["labels"] and t["labels"][0] in labels:
                allowed = labels[t["labels"][0]]["properties"]
                problems += [f"label {t['labels'][0]} has no property '{k}'" for k in t["map_keys"] if k not in allowed]
        else:
            problems += [f"unknown relationship type :{x}" for x in t["types"] if x not in types]
    for var, prop in _PROP.findall(_STRINGS.sub("''", query)):
        if var.lower() in ("db", "dbms"):
            continue
        if var in bound and bound[var] in labels:
            if prop not in labels[bound[var]]["properties"]:
                problems.append(f"label {bound[var]} has no property '{prop}' (used as {var}.{prop})")
        elif prop not in keys:
            problems.append(f"unknown property key '{prop}' (used as {var}.{prop})")
    return sorted(set(problems))


def check_direction(query: str, schema: dict) -> list[str]:
    """Gate 2: relationships written against the direction stored in the schema.
    This is the one structural mistake EXPLAIN accepts silently."""
    tokens, types = _parse(query), {t["type"]: t for t in schema["triples"]}
    bound, problems = _bindings(tokens), []

    def label(node):
        return node["labels"][0] if node["labels"] else bound.get(node["var"])

    for i, t in enumerate(tokens):
        if t["kind"] != "rel" or t["left"] == t["right"] or not (0 < i < len(tokens) - 1):
            continue  # undirected patterns match either way
        a, b = tokens[i - 1], tokens[i + 1]
        if a["kind"] != "node" or b["kind"] != "node" or not (a.get("in_pattern") and b.get("in_pattern")):
            continue
        src, dst = (b, a) if t["left"] else (a, b)
        for name in t["types"]:
            if name not in types:
                continue
            want_s, want_d = types[name]["source"], types[name]["target"]
            got_s, got_d = label(src), label(dst)
            if (got_s and got_s != want_s) or (got_d and got_d != want_d):
                problems.append(f"{name} goes ({want_s})->({want_d}), but the query writes "
                                f"({got_s or '?'})->({got_d or '?'})")
    return sorted(set(problems))


def check_explain(query: str) -> dict:
    """Gate 3: ask the server to plan the query. Returns problems (errors and Unknown* warnings),
    other planner notes, and the planner's row estimate."""
    payload = _post("EXPLAIN " + query)
    problems = [e["message"].split("\n")[0] for e in payload.get("errors", [])]
    notes = []
    for n in payload.get("notifications", []):
        (problems if ".Unknown" in n.get("code", "") else notes).append(f"{n.get('title', '')} [{n.get('code', '').split('.')[-1]}]")
    plan = (payload.get("results") or [{}])[0].get("plan") or {}
    return {"problems": problems, "notes": notes, "estimated_rows": plan.get("root", {}).get("EstimatedRows")}


def validate(query: str, schema: dict, use_server: bool = True, short_circuit: bool = True) -> dict:
    """Run the gates in order. With short_circuit the server is not contacted once a local gate fails."""
    report = {"ok": True, "gates": {}, "notes": [], "estimated_rows": None}
    report["gates"]["vocabulary"] = check_vocabulary(query, schema)
    report["gates"]["direction"] = check_direction(query, schema)
    local_fail = bool(report["gates"]["vocabulary"] or report["gates"]["direction"])
    if use_server and not (short_circuit and local_fail):
        ex = check_explain(query)
        report["gates"]["explain"] = ex["problems"]
        report["notes"], report["estimated_rows"] = ex["notes"], ex["estimated_rows"]
    report["ok"] = not any(report["gates"].values())
    return report


def validate_and_run(query: str, schema: dict, max_rows: int | None = 50) -> dict:
    """Validate, then execute only if every gate passed."""
    report = validate(query, schema)
    report["result"] = run_cypher(query, max_rows) if report["ok"] else None
    return report
