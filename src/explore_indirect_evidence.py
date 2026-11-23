"""Explore indirect compound-disease evidence before defining benchmark gold queries.

Usage:
  uv run python src/explore_indirect_evidence.py "vitiligo" Ruxolitinib Methoxsalen Monobenzone
  uv run python src/explore_indirect_evidence.py "endogenous depression" Pramipexole Sertraline
"""
import argparse
from itertools import combinations

from db import run_cypher

FIRST = "BINDS_CbG|UPREGULATES_CuG|DOWNREGULATES_CdG"
LAST = "ASSOCIATES_DaG|UPREGULATES_DuG|DOWNREGULATES_DdG"
KNOWN = "TREATS_CtD|PALLIATES_CpD"
GG = "INTERACTS_GiG|REGULATES_GrG|COVARIES_GcG"


def rows(query):
    result = run_cypher(query, max_rows=None)
    if "error" in result:
        raise SystemExit(f"Cypher error: {result['error']}\n{query}")
    return result["rows"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("disease")
    parser.add_argument("compounds", nargs="+")
    args = parser.parse_args()

    disease_rows = rows(
        f"MATCH (d:Disease {{name:'{args.disease}'}}) RETURN d.name AS name, d.identifier AS id"
    )
    if not disease_rows:
        raise SystemExit(f"Disease not in graph: {args.disease}")

    did = disease_rows[0]["id"]
    known = rows(
        f"MATCH (c:Compound)-[r:{KNOWN}]->(:Disease {{identifier:'{did}'}}) "
        "RETURN c.name AS name, type(r) AS relation"
    )
    known_names = {row["name"] for row in known}
    print(f"Disease: {args.disease}")
    print("Known graph therapies:", ", ".join(sorted(known_names)) or "none")

    evidence = {}
    for name in args.compounds:
        compound = rows(f"MATCH (c:Compound {{name:'{name}'}}) RETURN c.identifier AS id")
        if not compound:
            print(f"\n{name}: NOT IN GRAPH")
            continue

        direct = rows(
            f"MATCH (:Compound {{name:'{name}'}})-[r:{KNOWN}]->"
            f"(:Disease {{name:'{args.disease}'}}) RETURN type(r) AS relation"
        )
        gene_links = rows(
            f"MATCH (:Compound {{name:'{name}'}})-[r:{FIRST}]->() RETURN count(r) AS count"
        )[0]["count"]
        cgd = rows(
            f"MATCH (:Compound {{name:'{name}'}})-[:{FIRST}]->(g:Gene)"
            f"<-[:{LAST}]-(:Disease {{name:'{args.disease}'}}) "
            "RETURN count(*) AS paths, count(DISTINCT g) AS genes"
        )[0]
        cggd = rows(
            f"MATCH (:Compound {{name:'{name}'}})-[:{FIRST}]->(g1:Gene)-[:{GG}]-(g2:Gene)"
            f"<-[:{LAST}]-(:Disease {{name:'{args.disease}'}}) "
            "RETURN count(*) AS paths, count(DISTINCT g1) AS genes"
        )[0]
        evidence[name] = rows(
            f"MATCH (:Compound {{name:'{name}'}})-[:{FIRST}]->(g:Gene)"
            f"<-[:{LAST}]-(:Disease {{name:'{args.disease}'}}) RETURN DISTINCT g.name AS name"
        )

        tags = ["known therapy"] if name in known_names else []
        if not direct:
            tags.append("no direct edge")
        print(
            f"\n{name}: gene links={gene_links}, C-G-D={cgd['paths']}/{cgd['genes']} "
            f"(paths/distinct genes), C-G-G-D={cggd['paths']}/{cggd['genes']} "
            f"(paths/distinct bound genes), " + ("; ".join(tags) or "no graph therapy label")
        )

    if len(evidence) >= 2:
        print("\nC-G-D distinct-gene overlap:")
        for left, right in combinations(evidence, 2):
            left_genes = {row["name"] for row in evidence[left]}
            right_genes = {row["name"] for row in evidence[right]}
            print(
                f"{left} + {right}: union={len(left_genes | right_genes)}, "
                f"shared={len(left_genes & right_genes)}"
            )

    ranking = rows(
        f"MATCH (c:Compound)-[:{FIRST}]->(g:Gene)"
        f"<-[:{LAST}]-(:Disease {{name:'{args.disease}'}}) "
        "RETURN c.name AS name, count(*) AS paths "
        "ORDER BY paths DESC, name ASC"
    )
    print(f"\nC-G-D ranking: {len(ranking)} compounds reach the disease")
    for row in ranking[:10]:
        print(f"  {row['name']}: {row['paths']}")


if __name__ == "__main__":
    main()
