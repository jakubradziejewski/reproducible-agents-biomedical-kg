"""Checks on a generated Cypher query before we run it. Based on CYGNET (Tomczak, 2026).

Three checks ("gates"), from the cheapest to the most expensive:
1. vocabulary - labels, relationship types and properties must exist in data/schema.json
2. direction  - (a:L1)-[:TYPE]->(b:L2) must go the way TYPE goes in the schema
3. explain    - the server plans the query with EXPLAIN, nothing is executed

The first two work on regular expressions and not on a real Cypher parser, so they only
understand ordinary MATCH patterns. Syntax is left to EXPLAIN. Why the other CYGNET gates
are not here is explained in notebooks/preprocessing/01_t2css_pipeline.ipynb.
"""
import re

from db import _post, is_read_only, run_cypher

_STRINGS = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
# a node "(...)" or a relationship "-[...]->", "<-[...]-", "--"
_TOKEN = re.compile(r"(?P<node>\([^()]*\))|(?P<rel><?-\s*(?:\[[^\]]*\])?\s*->?)")
# inside a node: variable, labels, and the rest (the {key: value} map)
_NODE = re.compile(r"\s*(?P<var>[A-Za-z_]\w*)?\s*(?P<labels>(?::\s*`?\w+`?\s*)*)(?P<rest>.*)", re.S)
# variable.property, but not function calls like db.labels()
_PROP = re.compile(r"(?<![\w.`])([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b(?!\s*\()")


def _parse(query):
    """Nodes and relationships of the query in the order they appear."""
    text = _STRINGS.sub("''", query)  # so that brackets inside names do not confuse us
    out = []
    for m in _TOKEN.finditer(text):
        if m.group("node"):
            n = _NODE.match(m.group("node")[1:-1])
            out.append({
                "kind": "node", "start": m.start(), "end": m.end(),
                "var": n.group("var"),
                "labels": re.findall(r"\w+", n.group("labels")),
                "map_keys": re.findall(r"[{,]\s*`?(\w+)`?\s*:", n.group("rest")),
            })
        else:
            raw = m.group("rel")
            inside = raw[raw.index("[") + 1: raw.rindex("]")] if "[" in raw else ""
            # [r:TYPE_A|TYPE_B*1..2 {..}] -> the part after ":" up to "*" or "{"
            names = re.split(r"[*{]", inside.split(":", 1)[1])[0] if ":" in inside else ""
            out.append({
                "kind": "rel", "start": m.start(), "end": m.end(),
                "types": re.findall(r"\w+", names),
                "left": raw.startswith("<"), "right": raw.endswith(">"),
            })

    # "(...)" is also what a function call looks like, e.g. count(g). We treat it as a node
    # of a pattern only when it stands directly next to a relationship.
    for i, rel in enumerate(out):
        if rel["kind"] != "rel":
            continue
        for j in (i - 1, i + 1):
            if not 0 <= j < len(out) or out[j]["kind"] != "node":
                continue
            node = out[j]
            between = text[min(node["end"], rel["end"]):max(node["start"], rel["start"])]
            if not between.strip():
                node["in_pattern"] = True
    return out


def _bindings(tokens):
    """Which label each variable was declared with, e.g. {"c": "Compound"}."""
    return {t["var"]: t["labels"][0] for t in tokens if t["kind"] == "node" and t["var"] and t["labels"]}


def check_vocabulary(query, schema):
    """Gate 1: names that are not in the schema, and queries that are not read-only."""
    problems = []
    if not is_read_only(query):
        problems.append("write clause or procedure call: only read-only Cypher is allowed")

    labels = schema["labels"]
    types = {t["type"] for t in schema["triples"]}
    keys = set(schema["property_keys"])
    tokens = _parse(query)
    bound = _bindings(tokens)

    for t in tokens:
        if t["kind"] == "rel":
            for name in t["types"]:
                if name not in types:
                    problems.append(f"unknown relationship type :{name}")
            continue
        for name in t["labels"]:
            if name not in labels:
                problems.append(f"unknown label :{name}")
        # properties written inside the node, like (d:Disease {name: 'asthma'})
        if t["labels"] and t["labels"][0] in labels:
            label = t["labels"][0]
            for key in t["map_keys"]:
                if key not in labels[label]["properties"]:
                    problems.append(f"label {label} has no property '{key}'")

    # names can also be given as strings: type(r) = 'CbG' or 'Drug' IN labels(n)
    for name in re.findall(r"type\(\s*\w+\s*\)\s*(?:=|<>)\s*'([^']*)'", query, flags=re.I):
        if name not in types:
            problems.append(f"unknown relationship type '{name}' (compared with type())")
    for name in re.findall(r"'([^']*)'\s+IN\s+labels\(", query, flags=re.I):
        if name not in labels:
            problems.append(f"unknown label '{name}' (tested with labels())")

    # properties used as variable.property
    for var, prop in _PROP.findall(_STRINGS.sub("''", query)):
        if var.lower() in ("db", "dbms"):
            continue
        label = bound.get(var)
        if label in labels:
            if prop not in labels[label]["properties"]:
                problems.append(f"label {label} has no property '{prop}' (used as {var}.{prop})")
        elif prop not in keys:
            problems.append(f"unknown property key '{prop}' (used as {var}.{prop})")
    return sorted(set(problems))


def check_direction(query, schema):
    """Gate 2: relationships written against the direction they have in the schema.
    EXPLAIN does not complain about these, the query would just return nothing."""
    types = {t["type"]: t for t in schema["triples"]}
    tokens = _parse(query)
    bound = _bindings(tokens)

    def label_of(node):
        if node["labels"]:
            return node["labels"][0]
        return bound.get(node["var"])

    problems = []
    for i, rel in enumerate(tokens):
        if rel["kind"] != "rel" or i == 0 or i == len(tokens) - 1:
            continue
        if rel["left"] == rel["right"]:
            continue  # no arrow (or both), so it matches either way
        a, b = tokens[i - 1], tokens[i + 1]
        if a["kind"] != "node" or b["kind"] != "node":
            continue
        if not (a.get("in_pattern") and b.get("in_pattern")):
            continue
        source, target = (b, a) if rel["left"] else (a, b)
        for name in rel["types"]:
            if name not in types:
                continue
            want_s, want_t = types[name]["source"], types[name]["target"]
            got_s, got_t = label_of(source), label_of(target)
            if (got_s and got_s != want_s) or (got_t and got_t != want_t):
                problems.append(f"{name} goes ({want_s})->({want_t}), but the query writes "
                                f"({got_s or '?'})->({got_t or '?'})")
    return sorted(set(problems))


def check_explain(query):
    """Gate 3: ask the server to plan the query.
    Returns the problems (errors and "unknown name" warnings), other notes from the planner
    and the number of rows the planner expects."""
    payload = _post("EXPLAIN " + query)
    problems = [e["message"].split("\n")[0] for e in payload.get("errors", [])]
    notes = []
    for n in payload.get("notifications", []):
        code = n.get("code", "")
        text = f"{n.get('title', '')} [{code.split('.')[-1]}]"
        if ".Unknown" in code:  # UnknownLabelWarning, UnknownRelationshipTypeWarning, ...
            problems.append(text)
        else:
            notes.append(text)
    plan = (payload.get("results") or [{}])[0].get("plan") or {}
    return {"problems": problems, "notes": notes, "estimated_rows": plan.get("root", {}).get("EstimatedRows")}


def validate(query, schema, use_server=True, short_circuit=True):
    """Run the gates in order. With short_circuit we do not bother the server
    when one of the local gates has already failed."""
    gates = {
        "vocabulary": check_vocabulary(query, schema),
        "direction": check_direction(query, schema),
    }
    report = {"ok": True, "gates": gates, "notes": [], "estimated_rows": None}
    failed_locally = bool(gates["vocabulary"] or gates["direction"])
    if use_server and not (short_circuit and failed_locally):
        explain = check_explain(query)
        gates["explain"] = explain["problems"]
        report["notes"] = explain["notes"]
        report["estimated_rows"] = explain["estimated_rows"]
    report["ok"] = not any(gates.values())
    return report


def validate_and_run(query, schema, max_rows=50):
    """Validate, and run the query only if every gate passed."""
    report = validate(query, schema)
    report["result"] = run_cypher(query, max_rows) if report["ok"] else None
    return report
