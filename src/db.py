"""Safe, read-only Cypher access to Hetionet over the Neo4j HTTP API."""
import os
import re
import time

import httpx
from dotenv import load_dotenv

load_dotenv()
URL = os.environ.get("NEO4J_HTTP_URL", "https://neo4j.het.io/db/data/transaction/commit")
USER, PWD = os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")

_CLIENT = httpx.Client(
    timeout=httpx.Timeout(120, connect=30),
    headers={"Accept": "application/json; charset=UTF-8", "Content-Type": "application/json"},
    auth=(USER, PWD) if USER else None,
)

# Block anything that could modify data, and any procedure call except db.* (schema info).
_WRITE = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV)\b|\bCALL\s+(?!db\.)",
    re.I,
)
_STRINGS = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")


def is_read_only(query: str) -> bool:
    """Check the query with string literals removed, so a disease named 'set' is not blocked."""
    return not _WRITE.search(_STRINGS.sub("''", query))


def _post(query: str, retries: int = 6) -> dict:
    body = {"statements": [{"statement": query}]}
    for attempt in range(retries):
        try:
            r = _CLIENT.post(URL, json=body)
            if r.status_code in (429, 502, 503, 504):
                raise httpx.TransportError(f"HTTP {r.status_code}")
            r.raise_for_status()
            time.sleep(0.2)  # be polite to a shared server
            return r.json()
        except httpx.TransportError:
            time.sleep(2 ** attempt)
    # Infrastructure failure: raise, so the runner never scores it as a model mistake.
    raise ConnectionError("Neo4j server unreachable after retries")


def run_cypher(query: str, max_rows: int | None = 50) -> dict:
    """Run a read-only query. Returns {"columns","rows","total_rows","truncated"} or {"error"}.

    Cypher mistakes come back as {"error": ...} so an agent can read them and retry.
    max_rows=None returns everything (used for gold answers).
    """
    if not is_read_only(query):
        return {"error": "Blocked: only read-only Cypher (MATCH/RETURN) is allowed."}
    payload = _post(query)
    if payload["errors"]:
        return {"error": payload["errors"][0]["message"][:500]}
    res = payload["results"][0]
    cols = res["columns"]
    rows = [dict(zip(cols, d["row"])) for d in res["data"]]
    total = len(rows)
    if max_rows is not None and total > max_rows:
        rows = rows[:max_rows]
    return {"columns": cols, "rows": rows, "total_rows": total, "truncated": total > len(rows)}
