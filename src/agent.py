"""Model-agnostic agent loop over any OpenAI-compatible chat API."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from openai import BadRequestError, OpenAI
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from prompt import SYSTEM_PROMPT


def make_client(cfg):
    key = os.getenv(cfg["key_env"]) if cfg.get("key_env") else "not-needed"
    return OpenAI(base_url=cfg["base_url"], api_key=key, timeout=120, max_retries=6)


def _tool_definitions(mcp_tools):
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


def _tool_result(result):
    if result.isError:
        messages = [item.text for item in result.content if hasattr(item, "text")]
        return {"error": "\n".join(messages) or "MCP tool call failed."}

    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured

    text = "\n".join(item.text for item in result.content if hasattr(item, "text"))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"text": text}


async def _run_agent(cfg, question, max_steps, temperature, seed, system_prompt,
                     cygnet_validation):
    client = make_client(cfg)
    if system_prompt is None:
        system_prompt = SYSTEM_PROMPT
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": question}]
    rec = {
        "steps": [], "final_answer": None, "tokens": 0, "seed_used": None,
        "model_turns": 0, "turn_usage": [],
    }
    t0 = time.time()
    server_path = Path(__file__).with_name("mcp_server.py")
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)] + (["--cygnet-validation"] if cygnet_validation else []),
        cwd=str(server_path.parent.parent),
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            available_tools = (await session.list_tools()).tools
            tools = _tool_definitions(available_tools)
            for _ in range(max_steps):
                rec["model_turns"] += 1
                resp, used = await asyncio.to_thread(
                    _chat, client, cfg, messages, temperature, seed, tools
                )
                rec["seed_used"] = used
                turn_usage = {
                    "turn": rec["model_turns"],
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "tool_calls": [],
                }
                if resp.usage:
                    turn_usage["total_tokens"] = resp.usage.total_tokens or 0
                    turn_usage["prompt_tokens"] = resp.usage.prompt_tokens or 0
                    turn_usage["completion_tokens"] = resp.usage.completion_tokens or 0
                    rec["tokens"] += turn_usage["total_tokens"]
                    rec["prompt_tokens"] = rec.get("prompt_tokens", 0) + turn_usage["prompt_tokens"]
                    rec["completion_tokens"] = rec.get("completion_tokens", 0) + turn_usage["completion_tokens"]
                msg = resp.choices[0].message
                turn_usage["tool_calls"] = [
                    tc.function.name for tc in (msg.tool_calls or [])
                ]
                rec["turn_usage"].append(turn_usage)
                if not msg.tool_calls:
                    rec["final_answer"] = msg.content
                    rec["stop_reason"] = "final_answer" if msg.content is not None else "empty_model_response"
                    break
                messages.append({
                    "role": "assistant", "content": msg.content or "",
                    "tool_calls": [tc.model_dump(exclude_none=True) for tc in msg.tool_calls],
                })
                for tc in msg.tool_calls:
                    try:
                        arguments = json.loads(tc.function.arguments)
                        if not isinstance(arguments, dict):
                            raise TypeError("Tool arguments must be a JSON object.")
                        result = _tool_result(
                            await session.call_tool(tc.function.name, arguments)
                        )
                    except (ValueError, TypeError):
                        arguments, result = {}, {"error": "Tool arguments must be a JSON object."}
                    validation = result.pop("_cygnet_validation", None)
                    step = {
                        "tool": tc.function.name,
                        "arguments": arguments,
                        "cypher": arguments.get("query") if tc.function.name == "run_cypher" else None,
                        "result": result,
                    }
                    if validation is not None:
                        step["validation"] = validation
                    rec["steps"].append(step)
                    messages.append({
                        "role": "tool", "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str)[:20000],
                    })
    rec.setdefault("stop_reason", "max_model_turns")
    rec["n_steps"] = len(rec["steps"])
    rec["latency_s"] = round(time.time() - t0, 2)
    return rec


def _chat(client, cfg, messages, temperature, seed, tools):
    """One model call. Some providers reject 'seed'; fall back and record whether it was used."""
    kwargs = dict(model=cfg["model"], messages=messages, tools=tools, temperature=temperature)
    if seed is not None:
        kwargs["seed"] = seed
    try:
        return client.chat.completions.create(**kwargs), seed is not None
    except BadRequestError as e:
        if seed is not None and "seed" in str(e).lower():
            kwargs.pop("seed")
            return client.chat.completions.create(**kwargs), False
        raise


def run_agent(cfg, question, max_steps=6, temperature=0.0, seed=0,
              system_prompt=SYSTEM_PROMPT, cygnet_validation=False):
    return asyncio.run(_run_agent(
        cfg, question, max_steps, temperature, seed, system_prompt, cygnet_validation
    ))
