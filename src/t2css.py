"""Building the prompt before the model is called, based on T2CSS (Wan et al., 2025).

Run from the repo root to write the prompts for all questions:  uv run src/t2css.py
"""
import json
import re
from functools import lru_cache

import numpy as np
from model2vec import StaticModel

from prompt import SYSTEM_PROMPT

EMBEDDING_MODEL = "minishlab/potion-base-8M"

STOP_WORDS = set("""
a an the of to in on for by with and or but is are was were be been do does did which what who whom
that this these those it its as at from into their there than then so such can could should would
have has had i we you they he she them me my our your return give show list find tell please
""".split())

NAME_HINT = "Disease names are lowercase (e.g. 'bile duct cancer'); compound names are capitalised."


def tokens(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOP_WORDS]


@lru_cache(maxsize=1)
def _model():
    return StaticModel.from_pretrained(EMBEDDING_MODEL)


def embed(texts):
    v = np.asarray(_model().encode(list(texts)), dtype=np.float32)
    norm = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.maximum(norm, 1e-12)


def question_vector(question):
    return embed([" ".join(tokens(question))])[0]


def _rank(question, items, text_key, name_key):
    """Sort items by cosine similarity to the question, equal scores by name."""
    scores = embed([" ".join(tokens(item[text_key])) for item in items]) @ question_vector(question)
    order = sorted(range(len(items)), key=lambda i: (-float(scores[i]), items[i][name_key]))
    return [dict(items[i], score=round(float(scores[i]), 4), rank=rank) for rank, i in enumerate(order, 1)]


def load_schema(path="data/schema.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rank_triples(question, schema):
    return _rank(question, schema["triples"], "gloss", "type")


def neighbourhood(labels, schema, order):
    """Labels that can be reached from `labels` in at most `order` steps in the schema graph."""
    neighbours = {}
    for t in schema["triples"]:
        neighbours.setdefault(t["source"], set()).add(t["target"])
        neighbours.setdefault(t["target"], set()).add(t["source"])
    reached = set(labels)
    for _ in range(order):
        for label in list(reached):
            reached |= neighbours.get(label, set())
    return reached


def select_triples(question, schema, k=6, order=0):
    """Top-k triples, with order > 0 also the triples within `order` steps of them."""
    ranked = rank_triples(question, schema)
    top = ranked[:k]
    if order <= 0:
        return top
    labels = {t["source"] for t in top} | {t["target"] for t in top}
    near = neighbourhood(labels, schema, order)
    return [t for t in ranked if t["source"] in near and t["target"] in near]


def load_rules(path="data/cypher_rules.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rank_rules(question, rules):
    optional = [r for r in rules if not r["always"]]
    return _rank(question, optional, "description", "id")


def select_rules(question, rules, k=3):
    always = [r for r in rules if r["always"]]
    return always + rank_rules(question, rules)[:k]


def schema_block(triples):
    labels = sorted({t["source"] for t in triples} | {t["target"] for t in triples})
    lines = [
        f"Node labels (all have name and identifier): {', '.join(labels)}.",
        NAME_HINT,
        "Relationship types (direction matters):",
    ]
    for t in sorted(triples, key=lambda t: t["type"]):
        lines.append(f"- (:{t['source']})-[:{t['type']}]->(:{t['target']})  {t['gloss']}")
    return "\n".join(lines)


def rules_block(rules):
    return "\n".join(["Cypher syntax notes:"] + [f"- {r['text']}" for r in rules])


def build_system_prompt(question, schema, rules, use_schema="filtered", use_rules="filtered",
                        k=6, order=0, rule_k=3):
    """use_schema and use_rules can be "filtered", "full" or "none"."""
    parts = []
    if use_schema == "full":
        parts.append(schema_block(schema["triples"]))
    elif use_schema == "filtered":
        parts.append(schema_block(select_triples(question, schema, k, order)))
    if use_rules == "full":
        parts.append(rules_block(rules))
    elif use_rules == "filtered":
        parts.append(rules_block(select_rules(question, rules, rule_k)))

    if not parts:
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + "\n\n" + "\n\n".join(parts)


# s1-s4 are the input strategies from the ablation in the paper (section 6.4.2)
VARIANTS = {
    "s1_question_only": dict(use_schema="none", use_rules="none"),
    "s2_rules": dict(use_schema="none", use_rules="full"),
    "s3_schema": dict(use_schema="full", use_rules="none"),
    "s4_schema_rules": dict(use_schema="full", use_rules="full"),
    "s4_filtered": dict(use_schema="filtered", use_rules="filtered"),
}


def build_context(qid, question, schema, rules, k=6, rule_k=3):
    prompts = {}
    for name, options in VARIANTS.items():
        prompts[name] = build_system_prompt(question, schema, rules, k=k, rule_k=rule_k, **options)
    return {
        "id": qid,
        "question": question,
        "tokens": tokens(question),
        "embedding_model": EMBEDDING_MODEL,
        "k": k,
        "rule_k": rule_k,
        "triple_ranking": [{"type": t["type"], "score": t["score"]} for t in rank_triples(question, schema)],
        "rule_ranking": [{"id": r["id"], "score": r["score"]} for r in rank_rules(question, rules)],
        "system_prompts": prompts,
    }


if __name__ == "__main__":
    schema, rules = load_schema(), load_rules()
    questions = [json.loads(line) for line in open("data/questions.jsonl", encoding="utf-8")]
    with open("data/t2css_context.jsonl", "w", encoding="utf-8") as f:
        for q in questions:
            context = build_context(q["id"], q["question"], schema, rules)
            f.write(json.dumps(context, ensure_ascii=False) + "\n")
    print(f"{len(questions)} questions -> data/t2css_context.jsonl")
