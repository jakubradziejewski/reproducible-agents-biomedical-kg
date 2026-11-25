"""Run the hand-written gold queries on the live graph and write data/questions.jsonl.

Retrospective drug-repurposing set. Hetionet is a 2017 snapshot; each case below is a drug-disease link
that was confirmed or tested later. The questions ask what the 2017 graph knows, never what is clinically
true. Gold answers come from running the Cypher below, never typed by hand.
"""
import json

from db import run_cypher

DEPRESSION = ("Esketamine (Spravato) FDA-approved 2019 for treatment-resistant depression; "
              "dextromethorphan-bupropion (Auvelity) FDA-approved August 2022 for major depressive disorder; "
              "pramipexole: PAX-D randomised trial (151 patients, registered as Phase IV), not approved.")
VITILIGO = "Ruxolitinib cream FDA-approved for nonsegmental vitiligo on 18 July 2022."

QUESTIONS = [
    dict(id="q01", level=1, role="time boundary: compounds newer than the graph", context=DEPRESSION,
         tests="entity existence (Esketamine is absent), counting zero direct edges, answering about every listed entity",
         question="For each of these compounds - Ketamine, Esketamine, Dextromethorphan, Bupropion, Pramipexole - "
                  "say whether it is a Compound node in the graph and how many direct treats or palliates edges it "
                  "has to endogenous depression. Return one row per listed compound: "
                  "[name, in_graph (true or false), number of direct edges].",
         cypher="UNWIND ['Ketamine','Esketamine','Dextromethorphan','Bupropion','Pramipexole'] AS n "
                "OPTIONAL MATCH (c:Compound {name:n}) "
                "OPTIONAL MATCH (c)-[r:TREATS_CtD|PALLIATES_CpD]->(:Disease {name:'endogenous depression'}) "
                "RETURN n AS name, c IS NOT NULL AS in_graph, count(r) AS direct_edges ORDER BY name"),
    dict(id="q02", level=2, role="graph silence: approved later, no short path in 2017", context=VITILIGO,
         tests="counting with zero results; a model must report 0 for Ruxolitinib instead of recalling the 2022 approval",
         question="For each of Ruxolitinib, Methoxsalen, Monobenzone and Treprostinil, how many vitiligo-associated "
                  "genes does the compound bind? Return one row per compound, including compounds with 0: "
                  "[name, number of genes].",
         cypher="UNWIND ['Ruxolitinib','Methoxsalen','Monobenzone','Treprostinil'] AS n "
                "MATCH (c:Compound {name:n}) "
                "OPTIONAL MATCH (c)-[:BINDS_CbG]->(g:Gene)<-[:ASSOCIATES_DaG]-(:Disease {name:'vitiligo'}) "
                "RETURN n AS name, count(DISTINCT g) AS genes ORDER BY name"),
    dict(id="q03", level=2, role="one-gene paths for several drugs", context=DEPRESSION,
         tests="several entities in one query, correct directions (associates points from disease to gene), empty group",
         question="Which genes associated with endogenous depression does each of Dextromethorphan, Bupropion, "
                  "Pramipexole and Ketamine bind? Return one row per compound-gene pair: [compound, gene]. "
                  "A compound with no such gene gives no rows.",
         cypher="UNWIND ['Dextromethorphan','Bupropion','Pramipexole','Ketamine'] AS n "
                "MATCH (c:Compound {name:n})-[:BINDS_CbG]->(g:Gene)<-[:ASSOCIATES_DaG]-(:Disease {name:'endogenous depression'}) "
                "RETURN DISTINCT c.name AS compound, g.name AS gene ORDER BY compound, gene"),
    dict(id="q04", level=3, role="drug combination: what each drug adds", context=DEPRESSION,
         tests="set logic (both, only one), optional matching, classification of each gene",
         question="Consider only genes associated with endogenous depression. Which of them does Dextromethorphan bind, "
                  "which does Bupropion bind? Return one row per gene reached by at least one of the two drugs: "
                  "[gene, 'both' or 'dextromethorphan_only' or 'bupropion_only'].",
         cypher="MATCH (:Disease {name:'endogenous depression'})-[:ASSOCIATES_DaG]->(g:Gene) "
                "OPTIONAL MATCH (:Compound {name:'Dextromethorphan'})-[a:BINDS_CbG]->(g) "
                "OPTIONAL MATCH (:Compound {name:'Bupropion'})-[b:BINDS_CbG]->(g) "
                "WITH g, a, b WHERE a IS NOT NULL OR b IS NOT NULL "
                "RETURN DISTINCT g.name AS gene, "
                "CASE WHEN a IS NOT NULL AND b IS NOT NULL THEN 'both' "
                "WHEN a IS NOT NULL THEN 'dextromethorphan_only' ELSE 'bupropion_only' END AS reached_by "
                "ORDER BY gene"),
    dict(id="q05", level=4, role="indirect route through gene interaction", ordered=True, context=VITILIGO,
         tests="three-edge path, undirected matching of INTERACTS_GiG, DISTINCT counting, deterministic tie-break",
         question="Which genes that Ruxolitinib binds physically interact (relationship INTERACTS_GiG, direction "
                  "ignored) with a gene associated with vitiligo? Return one row per bound gene: "
                  "[bound gene, number of distinct vitiligo-associated interaction partners], ordered by that number "
                  "descending and then by gene name alphabetically.",
         cypher="MATCH (:Compound {name:'Ruxolitinib'})-[:BINDS_CbG]->(g:Gene)-[:INTERACTS_GiG]-(h:Gene)"
                "<-[:ASSOCIATES_DaG]-(:Disease {name:'vitiligo'}) "
                "RETURN g.name AS bound_gene, count(DISTINCT h) AS vitiligo_partners "
                "ORDER BY vitiligo_partners DESC, bound_gene ASC"),
]

written = 0
with open("data/questions.jsonl", "w", encoding="utf-8") as f:
    for q in QUESTIONS:
        res = run_cypher(q["cypher"], max_rows=None)
        if "error" in res:
            print(f"{q['id']}  ERROR: {res['error']}")
            continue
        n = res["total_rows"]
        print(f"{q['id']}  L{q['level']}  {n:>3} rows  {res['rows'][:6]}")
        rec = dict(id=q["id"], level=q["level"], role=q["role"], tests=q["tests"], context=q["context"],
                   question=q["question"], gold_cypher=q["cypher"], gold_result=res["rows"], n_rows=n,
                   ordered=q.get("ordered", False), trap=False, notes="")
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        written += 1
print(f"Wrote {written} questions to data/questions.jsonl")
