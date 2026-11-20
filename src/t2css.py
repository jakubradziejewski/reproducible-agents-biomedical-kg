"""Schema-guided prompt construction before query generation, inspired by T2CSS (Wan et al., 2025).

The four stages follow the filtering process of the paper (section 4.3):
1. text preprocessing    question -> tokens without stop words -> mean of static word vectors (eq. 3)
2. schema mapping        cosine similarity between the question vector and every schema triple (eq. 4)
3. syntax selection      Cypher rules most relevant to the question
4. prompt assembly       P = question + selected triples + selected rules (eq. 1)

Where we deviate from the paper, and why, is documented in notebooks/preprocessing/01_t2css_pipeline.ipynb.
Everything here runs on CPU and is deterministic, so every model can be given byte-identical prompts.
"""
import json
import re
from functools import lru_cache

import numpy as np

from prompt import SYSTEM_PROMPT

EMBEDDING_MODEL = "minishlab/potion-base-8M"  # static vectors; a sentence vector is the mean of its token vectors

STOP_WORDS = frozenset(
    "a an the of to in on for by with and or but is are was were be been do does did which what who whom "
    "that this these those it its as at from into their there than then so such can could should would "
    "have has had i we you they he she them me my our your return give show list find tell please".split()
)

NAME_HINT = "Disease names are lowercase (e.g. 'bile duct cancer'); compound names are capitalised."


# ---------------------------------------------------------------- stage 1: question -> vector
def tokens(text: str) -> list[str]:
    """Lower-case words with stop words removed (the paper's 'text preprocessing')."""
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP_WORDS]


@lru_cache(maxsize=1)
def _model():
    from model2vec import StaticModel

    return StaticModel.from_pretrained(EMBEDDING_MODEL)


def embed(texts: list[str]) -> np.ndarray:
    """Unit-length vectors, one row per text."""
    v = np.asarray(_model().encode(list(texts)), dtype=np.float32)
    return v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-12, None)


def question_vector(question: str) -> np.ndarray:
    return embed([" ".join(tokens(question))])[0]


# ---------------------------------------------------------------- stage 2: schema mapping
def load_schema(path: str = "data/schema.json") -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rank_triples(question: str, schema: dict) -> list[dict]:
    """All schema triples, most similar to the question first."""
    triples = schema["triples"]
    scores = embed([" ".join(tokens(t["gloss"])) for t in triples]) @ question_vector(question)
    order = sorted(range(len(triples)), key=lambda i: (-float(scores[i]), triples[i]["type"]))
    return [dict(triples[i], score=round(float(scores[i]), 4), rank=r + 1) for r, i in enumerate(order)]


def neighbourhood(labels: set[str], schema: dict, order: int) -> set[str]:
    """Labels reachable from `labels` in at most `order` steps of the schema graph."""
    adj: dict[str, set[str]] = {}
    for t in schema["triples"]:
        adj.setdefault(t["source"], set()).add(t["target"])
        adj.setdefault(t["target"], set()).add(t["source"])
    seen, frontier = set(labels), set(labels)
    for _ in range(order):
        frontier = {n for lab in frontier for n in adj.get(lab, ())} - seen
        seen |= frontier
    return seen


def select_triples(question: str, schema: dict, k: int = 6, order: int = 0) -> list[dict]:
    """Top-k triples by similarity. With order > 0 also every triple inside the order-step
    neighbourhood of the labels they touch (the paper's 'three-order concepts' is order=3)."""
    ranked = rank_triples(question, schema)
    chosen = ranked[:k]
    if order > 0:
        reach = neighbourhood({lab for t in chosen for lab in (t["source"], t["target"])}, schema, order)
        chosen = [t for t in ranked if t["source"] in reach and t["target"] in reach]
    return chosen


# ---------------------------------------------------------------- stage 3: syntax selection
def load_rules(path: str = "data/cypher_rules.json") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rank_rules(question: str, rules: list[dict]) -> list[dict]:
    """Optional rules (always=false), most similar to the question first."""
    optional = [r for r in rules if not r["always"]]
    scores = embed([" ".join(tokens(r["description"])) for r in optional]) @ question_vector(question)
    order = sorted(range(len(optional)), key=lambda i: (-float(scores[i]), optional[i]["id"]))
    return [dict(optional[i], score=round(float(scores[i]), 4), rank=r + 1) for r, i in enumerate(order)]


def select_rules(question: str, rules: list[dict], k: int = 3) -> list[dict]:
    """The always-on rules plus the k most relevant optional ones."""
    return [r for r in rules if r["always"]] + rank_rules(question, rules)[:k]


# ---------------------------------------------------------------- stage 4: prompt assembly
def schema_block(triples: list[dict]) -> str:
    labels = sorted({lab for t in triples for lab in (t["source"], t["target"])})
    lines = [f"Node labels (all have name and identifier): {', '.join(labels)}.", NAME_HINT,
             "Relationship types (direction matters):"]
    lines += [f"- (:{t['source']})-[:{t['type']}]->(:{t['target']})  {t['gloss']}"
              for t in sorted(triples, key=lambda t: t["type"])]
    return "\n".join(lines)


def rules_block(rules: list[dict]) -> str:
    return "\n".join(["Cypher syntax notes:"] + [f"- {r['text']}" for r in rules])


def _split_base_prompt() -> tuple[str, str]:
    """Reuse the shared system prompt: keep its opening lines and its closing 'Rules:' section,
    and replace only the schema description in between."""
    start, end = SYSTEM_PROMPT.index("Node labels"), SYSTEM_PROMPT.index("Rules:")
    return SYSTEM_PROMPT[:start], SYSTEM_PROMPT[end:]


def build_system_prompt(question: str, schema: dict, rules: list[dict], use_schema: str = "filtered",
                        use_rules: str = "filtered", k: int = 6, order: int = 0, rule_k: int = 3) -> str:
    """System prompt for one question.

    use_schema: "filtered" (top-k triples), "full" (all triples) or "none"
    use_rules:  "filtered" (always-on + top rule_k), "full" (all rules) or "none"
    The four input strategies of the paper's ablation are (none, none), (none, full),
    (full or filtered, none) and (full or filtered, full or filtered).
    """
    head, tail = _split_base_prompt()
    parts = []
    if use_schema != "none":
        chosen = schema["triples"] if use_schema == "full" else select_triples(question, schema, k, order)
        parts.append(schema_block(chosen))
    if use_rules != "none":
        parts.append(rules_block(rules if use_rules == "full" else select_rules(question, rules, rule_k)))
    return head + "\n".join(parts) + ("\n" if parts else "") + tail


# Prompt variants stored for every question. s1-s4 are the four input strategies of the paper's
# ablation (section 6.4.2); "filtered" is s4 with the similarity filter switched on.
VARIANTS = {
    "s1_question_only": dict(use_schema="none", use_rules="none"),
    "s2_rules": dict(use_schema="none", use_rules="full"),
    "s3_schema": dict(use_schema="full", use_rules="none"),
    "s4_schema_rules": dict(use_schema="full", use_rules="full"),
    "s4_filtered": dict(use_schema="filtered", use_rules="filtered"),
}


def build_context(qid: str, question: str, schema: dict, rules: list[dict], k: int = 6, rule_k: int = 3) -> dict:
    """Everything stages 1-4 produce for one question, ready to be stored next to the question set."""
    return {
        "id": qid, "question": question, "tokens": tokens(question),
        "embedding_model": EMBEDDING_MODEL, "k": k, "rule_k": rule_k,
        "triple_ranking": [{"type": t["type"], "score": t["score"]} for t in rank_triples(question, schema)],
        "rule_ranking": [{"id": r["id"], "score": r["score"]} for r in rank_rules(question, rules)],
        "system_prompts": {name: build_system_prompt(question, schema, rules, k=k, rule_k=rule_k, **opts)
                           for name, opts in VARIANTS.items()},
    }


if __name__ == "__main__":
    # Pre-compute the context of every question once, so all models receive identical prompts.
    schema, rules = load_schema(), load_rules()
    with open("data/questions.jsonl", encoding="utf-8-sig") as f:
        questions = [json.loads(line) for line in f if line.strip()]
    with open("data/t2css_context.jsonl", "w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps(build_context(q["id"], q["question"], schema, rules), ensure_ascii=False) + "\n")
    print(f"{len(questions)} questions -> data/t2css_context.jsonl (model {EMBEDDING_MODEL})")
