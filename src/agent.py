"""Model-agnostic agent loop over any OpenAI-compatible chat API."""
import json
import os
import time

from openai import BadRequestError, OpenAI

from db import run_cypher
from prompt import SYSTEM_PROMPT

TOOLS = [{
    "type": "function",
    "function": {
        "name": "run_cypher",
        "description": "Run a read-only Cypher query (Neo4j 3.5) on the Hetionet graph. "
                       "Returns columns, rows, total_rows, truncated, or an error message.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "The Cypher query"}},
            "required": ["query"],
        },
    },
}]


def make_client(cfg):
    key = os.getenv(cfg["key_env"]) if cfg.get("key_env") else "not-needed"
    return OpenAI(base_url=cfg["base_url"], api_key=key, timeout=120, max_retries=6)


def _chat(client, cfg, messages, temperature, seed):
    """One model call. Some providers reject 'seed'; fall back and record whether it was used."""
    kwargs = dict(model=cfg["model"], messages=messages, tools=TOOLS, temperature=temperature)
    if seed is not None:
        kwargs["seed"] = seed
    try:
        return client.chat.completions.create(**kwargs), seed is not None
    except BadRequestError as e:
        if seed is not None and "seed" in str(e).lower():
            kwargs.pop("seed")
            return client.chat.completions.create(**kwargs), False
        raise


def run_agent(cfg, question, max_steps=6, temperature=0.0, seed=0):
    client = make_client(cfg)
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question}]
    rec = {"steps": [], "final_answer": None, "tokens": 0, "seed_used": None}
    t0 = time.time()
    for _ in range(max_steps):
        resp, used = _chat(client, cfg, messages, temperature, seed)
        rec["seed_used"] = used
        if resp.usage:
            rec["tokens"] += resp.usage.total_tokens or 0
        msg = resp.choices[0].message
        if not msg.tool_calls:
            rec["final_answer"] = msg.content
            break
        messages.append({
            "role": "assistant", "content": msg.content or "",
            "tool_calls": [tc.model_dump(exclude_none=True) for tc in msg.tool_calls],
        })
        for tc in msg.tool_calls:
            try:
                query = json.loads(tc.function.arguments)["query"]
                result = run_cypher(query)
            except (ValueError, KeyError, TypeError):
                query, result = "", {"error": "Tool arguments must be JSON with a 'query' string."}
            rec["steps"].append({"cypher": query, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result, default=str)[:20000]})
    rec["n_steps"] = len(rec["steps"])
    rec["latency_s"] = round(time.time() - t0, 2)
    return rec
