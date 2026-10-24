"""Compare an agent's query result with the gold result."""
import itertools
import json


def _norm(v):
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, str):
        return v.strip().lower()
    return v


def _rows(rows, cols=None):
    """Rows -> tuples of normalised values (column names are ignored; aliases differ)."""
    return [tuple(_norm(r[c]) for c in (cols or list(r))) for r in rows]


def _best_view(pred_rows, k, gold, ordered):
    """If the agent returned extra columns, try every k-column subset and keep the best match."""
    if not pred_rows:
        return []
    cols = list(pred_rows[0])
    if len(cols) <= k:
        return _rows(pred_rows)
    best, best_score = None, -1
    for sub in itertools.combinations(cols, k):
        view = _rows(pred_rows, sub)
        score = len(set(view) & set(gold))
        if score > best_score:
            best, best_score = view, score
    return best


def score(pred_rows, gold_rows, ordered=False, trap=False):
    if trap:  # the correct behaviour is "nothing found"; the final text still needs a manual check
        return {"exact": len(pred_rows) == 0, "precision": 1.0, "recall": 1.0, "f1": 1.0 if not pred_rows else 0.0}
    gold = _rows(gold_rows)
    k = len(gold[0]) if gold else 0
    pred = _best_view(pred_rows, k, gold, ordered)
    sp, sg = set(pred), set(gold)
    tp = len(sp & sg)
    prec = tp / len(sp) if sp else 0.0
    rec = tp / len(sg) if sg else (1.0 if not sp else 0.0)
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    exact = (pred == gold) if ordered else (sp == sg and len(pred) == len(set(pred)))
    return {"exact": exact, "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3)}


if __name__ == "__main__":
    # Self-test: gold vs itself must be perfect; damaged copies must not be.
    for line in open("data/questions.jsonl", encoding="utf-8"):
        q = json.loads(line)
        g = q["gold_result"]
        ok = score(g, g, q["ordered"], q["trap"])["exact"]
        dropped = score(g[:-1], g, q["ordered"], q["trap"])["exact"] if len(g) > 1 else None
        reordered = score(g[::-1], g, q["ordered"], q["trap"])["exact"] if len(g) > 1 else None
        print(f"{q['id']}  self={ok}  drop-last={dropped}  reversed={reordered}")
