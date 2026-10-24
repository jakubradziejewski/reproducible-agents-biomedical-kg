from db import run_cypher

print("== Aspirin / acetylsalicylic lookup ==")
r = run_cypher("MATCH (c:Compound) WHERE toLower(c.name) CONTAINS 'aspirin' "
               "OR toLower(c.name) CONTAINS 'acetylsalicylic' "
               "RETURN c.name AS name, c.identifier AS id")
print(r["rows"])

def top5(d, negate):
    d = d.replace("'", "\\'")
    cond = "WHERE NOT (c)-[:TREATS_CtD]->(d) " if negate else ""
    q = (f"MATCH (d:Disease {{name:'{d}'}}) "
         f"MATCH (c:Compound)-[:BINDS_CbG]->(g:Gene)<-[:ASSOCIATES_DaG]-(d) {cond}"
         "RETURN c.name AS name, count(DISTINCT g) AS shared_genes "
         "ORDER BY shared_genes DESC, name ASC LIMIT 5")
    return run_cypher(q, max_rows=None)["rows"]

print("\n== Does the NOT filter change the top 5? ==")
dis = run_cypher("MATCH (:Compound)-[:TREATS_CtD]->(d:Disease) "
                 "RETURN d.name AS name, count(*) AS n ORDER BY n DESC, name LIMIT 15",
                 max_rows=None)["rows"]
for row in dis:
    d = row["name"]
    a, b = top5(d, False), top5(d, True)
    changed = sum(1 for x in a if x not in b)
    print(f"{d:<35} treatments={row['n']:<3} rows_changed_by_NOT={changed}/5"
          + ("   <-- good candidate" if changed >= 2 else ""))
