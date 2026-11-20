"""Export the Hetionet schema (labels, relationship types, properties) to data/schema.json.

Run from the repo root:  uv run src/build_schema.py
"""
import json
from datetime import date

from db import URL, _post, run_cypher

GLOSSES = {
    "ASSOCIATES_DaG": "disease is associated with gene",
    "BINDS_CbG": "compound (drug) binds gene (its protein target)",
    "CAUSES_CcSE": "compound (drug) causes side effect",
    "COVARIES_GcG": "gene covaries with gene (evolutionary rate covariation)",
    "DOWNREGULATES_AdG": "anatomy (tissue) downregulates gene expression",
    "DOWNREGULATES_CdG": "compound (drug) downregulates gene expression",
    "DOWNREGULATES_DdG": "disease downregulates gene expression",
    "EXPRESSES_AeG": "anatomy (tissue) expresses gene",
    "INCLUDES_PCiC": "pharmacologic class includes compound (drug)",
    "INTERACTS_GiG": "gene interacts with gene (protein-protein interaction)",
    "LOCALIZES_DlA": "disease localizes to anatomy (body part, tissue)",
    "PALLIATES_CpD": "compound (drug) palliates disease (relieves its symptoms)",
    "PARTICIPATES_GpBP": "gene participates in biological process",
    "PARTICIPATES_GpCC": "gene participates in cellular component",
    "PARTICIPATES_GpMF": "gene participates in molecular function",
    "PARTICIPATES_GpPW": "gene participates in pathway",
    "PRESENTS_DpS": "disease presents symptom",
    "REGULATES_GrG": "gene regulates gene",
    "RESEMBLES_CrC": "compound (drug) resembles compound (chemical similarity)",
    "RESEMBLES_DrD": "disease resembles disease",
    "TREATS_CtD": "compound (drug) treats disease",
    "UPREGULATES_AuG": "anatomy (tissue) upregulates gene expression",
    "UPREGULATES_CuG": "compound (drug) upregulates gene expression",
    "UPREGULATES_DuG": "disease upregulates gene expression",
}


def _rows(query):
    res = run_cypher(query, max_rows=None)
    if "error" in res:
        raise RuntimeError(f"{query}\n{res['error']}")
    return res["rows"]


def build():
    server = _post("CALL dbms.components()")["results"][0]["data"][0]["row"]
    labels = sorted(r["label"] for r in _rows("CALL db.labels()"))
    types = sorted(r["relationshipType"] for r in _rows("CALL db.relationshipTypes()"))
    keys = sorted(r["propertyKey"] for r in _rows("CALL db.propertyKeys()"))

    node_props = {}
    for lab in labels:
        node_props[lab] = sorted(_rows(f"MATCH (n:`{lab}`) RETURN keys(n) AS k LIMIT 1")[0]["k"])

    triples = []
    for t in types:
        row = _rows(f"MATCH (a)-[r:`{t}`]->(b) RETURN labels(a)[0] AS s, labels(b)[0] AS d, keys(r) AS k LIMIT 1")[0]
        triples.append({
            "type": t, "source": row["s"], "target": row["d"],
            "gloss": GLOSSES[t], "properties": sorted(row["k"]),
        })

    return {
        "source": URL,
        "server": {"name": server[0], "version": server[1][0], "edition": server[2]},
        "exported": date.today().isoformat(),
        "labels": {lab: {"properties": node_props[lab]} for lab in labels},
        "triples": triples,
        "property_keys": keys,
    }


if __name__ == "__main__":
    schema = build()
    with open("data/schema.json", "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"{len(schema['labels'])} labels, {len(schema['triples'])} triples, "
          f"{len(schema['property_keys'])} property keys -> data/schema.json")
