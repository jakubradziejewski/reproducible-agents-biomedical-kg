"""Building the prompt before the model is called. Based on T2CSS (Wan et al., 2025).

The idea from the paper: turn the question into a vector, find the schema triples and the
Cypher rules that are closest to it, and put those into the prompt. What we do differently
from the paper is described in notebooks/preprocessing/01_t2css_pipeline.ipynb.

Run from the repo root to write the prompts for all questions:  uv run src/t2css.py
"""
import json
import re
from functools import lru_cache

import numpy as np

from prompt import SYSTEM_PROMPT

# static embedding model: a sentence vector is the mean of its token vectors
EMBEDDING_MODEL = "minishlab/potion-base-8M"

STOP_WORDS = set("""
a an the of to in on for by with and or but is are was were be been do does did which what who whom
that this these those it its as at from into their there than then so such can could should would
have has had i we you they he she them me my our your return give show list find tell please
""".split())

NAME_HINT = "Disease names are lowercase (e.g. 'bile duct cancer'); compound names are capitalised."


# --- step 1: question -> vector

def tokens(text):
    """Lower-case words of a text, without stop words."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOP_WORDS]


@lru_cache(maxsize=1)
def _model():
    from model2vec import StaticModel  # loaded only when something is actually embedded
    return StaticModel.from_pretrained(EMBEDDING_MODEL)


def embed(texts):
    """One vector of length 1 per text."""
    v = np.asarray(_model().encode(list(texts)), dtype=np.float32)
    norm = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.maximum(norm, 1e-12)  # an empty text gives a zero vector


def question_vector(question):
    return embed([" ".join(tokens(question))])[0]


def _rank(question, items, text_key, name_key):
    """Items sorted by cosine similarity between the question and item[text_key], best first.
    Equal scores are ordered by name, so the result is always the same."""
    scores = embed([" ".join(tokens(item[text_key])) for item in items]) @ question_vector(question)
    order = sorted(range(len(items)), key=lambda i: (-float(scores[i]), items[i][name_key]))
    return [dict(items[i], score=round(float(scores[i]), 4), rank=rank) for rank, i in enumerate(order, 1)]


# --- step 2: which schema triples is the question about

def load_schema(path="data/schema.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rank_triples(question, schema):
    """All schema triples with a score, most similar to the question first."""
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
    """The k most similar triples. With order > 0 also every triple that lies within `order`
    steps of them (order=3 is the "three-order concepts" from the paper)."""
    ranked = rank_triples(question, schema)
    top = ranked[:k]
    if order <= 0:
        return top
    labels = {t["source"] for t in top} | {t["target"] for t in top}
    near = neighbourhood(labels, schema, order)
    return [t for t in ranked if t["source"] in near and t["target"] in near]


# --- step 3: which Cypher rules does the question need

def load_rules(path="data/cypher_rules.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rank_rules(question, rules):
    """The optional rules (always=false) with a score, most similar to the question first."""
    optional = [r for r in rules if not r["always"]]
    return _rank(question, optional, "description", "id")


def select_rules(question, rules, k=3):
    """The rules that are always included plus the k most similar optional ones."""
    always = [r for r in rules if r["always"]]
    return always + rank_rules(question, rules)[:k]


# --- step 4: putting the prompt together

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
    """System prompt for one question.

    use_schema: "filtered" (top-k triples), "full" (all triples) or "none"
    use_rules:  "filtered" (always-on rules + top rule_k), "full" (all rules) or "none"
    """
    parts = []
    if use_schema == "full":
        parts.append(schema_block(schema["triples"]))
    elif use_schema == "filtered":
        parts.append(schema_block(select_triples(question, schema, k, order)))
    if use_rules == "full":
        parts.append(rules_block(rules))
    elif use_rules == "filtered":
        parts.append(rules_block(select_rules(question, rules, rule_k)))

    # the beginning and the "Rules:" ending come from the team prompt, only the schema part is swapped
    start = SYSTEM_PROMPT.index("Node labels")
    end = SYSTEM_PROMPT.index("Rules:")
    middle = "\n".join(parts) + "\n" if parts else ""
    return SYSTEM_PROMPT[:start] + middle + SYSTEM_PROMPT[end:]


# Prompt variants saved for every question. s1-s4 are the four input strategies from the
# ablation in the paper (section 6.4.2), s4_filtered is s4 with the similarity filter on.
VARIANTS = {
    "s1_question_only": dict(use_schema="none", use_rules="none"),
    "s2_rules": dict(use_schema="none", use_rules="full"),
    "s3_schema": dict(use_schema="full", use_rules="none"),
    "s4_schema_rules": dict(use_schema="full", use_rules="full"),
    "s4_filtered": dict(use_schema="filtered", use_rules="filtered"),
}


def build_context(qid, question, schema, rules, k=6, rule_k=3):
    """Rankings and all prompt variants for one question (one line of data/t2css_context.jsonl)."""
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
    # computed once and saved, so every model gets exactly the same prompts
    schema, rules = load_schema(), load_rules()
    questions = [json.loads(line) for line in open("data/questions.jsonl", encoding="utf-8")]
    with open("data/t2css_context.jsonl", "w", encoding="utf-8") as f:
        for q in questions:
            context = build_context(q["id"], q["question"], schema, rules)
            f.write(json.dumps(context, ensure_ascii=False) + "\n")
    print(f"{len(questions)} questions -> data/t2css_context.jsonl")
