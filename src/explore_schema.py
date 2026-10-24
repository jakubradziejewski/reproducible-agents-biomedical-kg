import os
import httpx
from dotenv import load_dotenv

load_dotenv()
URL = os.environ.get("NEO4J_HTTP_URL", "https://neo4j.het.io/db/data/transaction/commit")
USER, PWD = os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")
AUTH = (USER, PWD) if USER else None
HEADERS = {"Accept": "application/json; charset=UTF-8", "Content-Type": "application/json"}

import time

HEADERS = {"Accept": "application/json; charset=UTF-8", "Content-Type": "application/json"}
CLIENT = httpx.Client(timeout=httpx.Timeout(120, connect=30), headers=HEADERS, auth=AUTH)


def q(statement: str, retries: int = 6):
    """Run one Cypher statement over the HTTP API, retrying on network trouble."""
    body = {"statements": [{"statement": statement}]}
    for attempt in range(retries):
        try:
            r = CLIENT.post(URL, json=body)
            if r.status_code in (429, 502, 503, 504):
                raise httpx.TransportError(f"HTTP {r.status_code}")
            r.raise_for_status()
            break
        except httpx.TransportError as e:
            wait = 2 ** attempt
            print(f"  retry {attempt + 1}/{retries} ({type(e).__name__}), waiting {wait}s")
            time.sleep(wait)
    else:
        raise RuntimeError("Server unreachable after retries")
    payload = r.json()
    if payload["errors"]:
        raise RuntimeError(payload["errors"][0]["message"])
    res = payload["results"][0]
    time.sleep(0.2)  # be polite to a shared public server
    return res["columns"], [d["row"] for d in res["data"]]
def main():
    _, comp = q("CALL dbms.components()")
    print("Server:", comp)

    labels = sorted(r[0] for r in q("CALL db.labels()")[1])
    rels = sorted(r[0] for r in q("CALL db.relationshipTypes()")[1])
    print(f"{len(labels)} labels, {len(rels)} relationship types")

    out = ["# Hetionet schema (auto-generated)\n", f"Server: `{comp}`\n"]

    out.append("\n## Node labels\n\n| Label | Count | Properties |\n|---|---|---|")
    for lab in labels:
        n = q(f"MATCH (n:`{lab}`) RETURN count(n)")[1][0][0]
        keys = q(f"MATCH (n:`{lab}`) RETURN keys(n) LIMIT 1")[1][0][0]
        out.append(f"| {lab} | {n} | {', '.join(keys)} |")

    out.append("\n## Relationship types\n\n| Type | Count | From -> To | Properties |\n|---|---|---|---|")
    for t in rels:
        n = q(f"MATCH ()-[r:`{t}`]->() RETURN count(r)")[1][0][0]
        row = q(f"MATCH (a)-[r:`{t}`]->(b) RETURN labels(a)[0], labels(b)[0], keys(r) LIMIT 1")[1][0]
        out.append(f"| {t} | {n} | {row[0]} -> {row[1]} | {', '.join(row[2])} |")

    out.append("\n## One example node per label\n")
    for lab in labels:
        ex = q(f"MATCH (n:`{lab}`) RETURN n LIMIT 1")[1][0][0]
        out.append(f"- **{lab}**: `{ex}`")

    text = "\n".join(out)
    with open("data/schema.md", "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
