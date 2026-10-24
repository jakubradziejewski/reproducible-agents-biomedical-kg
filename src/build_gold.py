"""Run the hand-written gold queries and save question + gold result to data/questions.jsonl."""
import json
from db import run_cypher

DIS = "multiple sclerosis"

QUESTIONS = [
    dict(id="q01", level=1, question="What is the identifier of the disease 'multiple sclerosis'?",
         cypher="MATCH (d:Disease {name:'multiple sclerosis'}) RETURN d.identifier AS identifier"),
    dict(id="q02", level=1, question="How many diseases are in the graph?",
         cypher="MATCH (d:Disease) RETURN count(d) AS n"),
    dict(id="q03", level=2, question="Which compounds are known to treat multiple sclerosis?",
         cypher="MATCH (c:Compound)-[:TREATS_CtD]->(:Disease {name:'multiple sclerosis'}) "
                "RETURN c.name AS name ORDER BY name"),
    dict(id="q04", level=2, question="Which diseases does the compound Metformin treat?",
         cypher="MATCH (:Compound {name:'Metformin'})-[:TREATS_CtD]->(d:Disease) "
                "RETURN d.name AS name ORDER BY name"),
    dict(id="q05", level=2, question="How many distinct side effects does Aspirin cause?",
         cypher="MATCH (:Compound {name:'Acetylsalicylic acid'})-[:CAUSES_CcSE]->(se:SideEffect) "
                "RETURN count(DISTINCT se) AS n",
         notes="Entity resolution: the graph stores the DrugBank chemical name "
               "'Acetylsalicylic acid' (DB00945), not 'Aspirin'."),
    dict(id="q06", level=3, question="Which genes are associated with both multiple sclerosis and rheumatoid arthritis?",
         cypher="MATCH (:Disease {name:'multiple sclerosis'})-[:ASSOCIATES_DaG]->(g:Gene)"
                "<-[:ASSOCIATES_DaG]-(:Disease {name:'rheumatoid arthritis'}) "
                "RETURN g.name AS name ORDER BY name"),
    dict(id="q07", level=4, ordered=True,
         question="Which 5 compounds bind the most genes associated with multiple sclerosis? "
                  "Return name and number of shared genes; break ties alphabetically by name.",
         cypher="MATCH (c:Compound)-[:BINDS_CbG]->(g:Gene)<-[:ASSOCIATES_DaG]-(:Disease {name:'multiple sclerosis'}) "
                "RETURN c.name AS name, count(DISTINCT g) AS shared_genes "
                "ORDER BY shared_genes DESC, name ASC LIMIT 5"),
    dict(id="q08", level=4, ordered=True,
         question="Which 5 diseases have the most compounds that treat them? "
                  "Return name and count; break ties alphabetically by name.",
         cypher="MATCH (:Compound)-[:TREATS_CtD]->(d:Disease) "
                "RETURN d.name AS name, count(*) AS n ORDER BY n DESC, name ASC LIMIT 5"),
    dict(id="q09", level=5, ordered=True,
         question="Which 5 compounds bind the most genes associated with osteoporosis but are NOT "
                  "known to treat it? Return name and shared gene count; break ties alphabetically by name.",
         cypher="MATCH (d:Disease {name:'osteoporosis'}) "
                "MATCH (c:Compound)-[:BINDS_CbG]->(g:Gene)<-[:ASSOCIATES_DaG]-(d) "
                "WHERE NOT (c)-[:TREATS_CtD]->(d) "
                "RETURN c.name AS name, count(DISTINCT g) AS shared_genes "
                "ORDER BY shared_genes DESC, name ASC LIMIT 5",
         notes="Negation matters: without the NOT filter, 2 of the top 5 rows differ (checked on the live server)."),
    dict(id="q10", level=6, trap=True,
         question="Which compounds treat the disease 'zorblax syndrome'?",
         cypher="MATCH (d:Disease {name:'zorblax syndrome'}) RETURN d.name AS name",
         notes="Trap: disease does not exist. Correct behaviour is to say it was not found."),
]

with open("data/questions.jsonl", "w", encoding="utf-8") as f:
    for q in QUESTIONS:
        res = run_cypher(q["cypher"], max_rows=None)
        if "error" in res:
            print(f"{q['id']}  ERROR: {res['error']}")
            continue
        n = res["total_rows"]
        empty = n == 0 or (n == 1 and all(v == 0 for v in res["rows"][0].values()))
        flag = "   <-- EMPTY/ZERO, check the names!" if empty and not q.get("trap") else ""
        print(f"{q['id']}  L{q['level']}  {n:>4} rows{flag}  first: {res['rows'][:2]}")
        rec = dict(id=q["id"], level=q["level"], question=q["question"], gold_cypher=q["cypher"],
                   gold_result=res["rows"], n_rows=n, ordered=q.get("ordered", False),
                   trap=q.get("trap", False), notes=q.get("notes", ""))
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
print("Wrote data/questions.jsonl")
