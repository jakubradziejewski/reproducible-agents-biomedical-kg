"""MCP tools for read-only access to the Hetionet graph and its schema."""
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from db import run_cypher as execute_cypher

ROOT = Path(__file__).resolve().parents[1]
mcp = FastMCP("Hetionet")


@mcp.tool()
def get_graph_schema() -> dict:
    """Get compact graph labels, relationship directions, and Neo4j Cypher dialect guidance."""
    schema_path = ROOT / "data" / "schema.json"
    if not schema_path.is_file():
        raise FileNotFoundError(f"Hetionet schema file not found: {schema_path}")

    with schema_path.open(encoding="utf-8") as file:
        schema = json.load(file)

    result = {
        "server": schema["server"],
        "cypher_dialect": "Neo4j 3.5; avoid EXISTS {}, COUNT {}, and CALL {} subqueries.",
        "read_only": True,
        "labels": list(schema["labels"]),
        "relationships": [
            {
                "type": relation["type"],
                "source": relation["source"],
                "target": relation["target"],
            }
            for relation in schema["triples"]
        ],
    }
    return result


@mcp.tool()
def run_cypher(query: str) -> dict:
    """Run a read-only Neo4j 3.5 Cypher query. Results are limited to 50 rows."""
    return execute_cypher(query)


if __name__ == "__main__":
    mcp.run(transport="stdio")
