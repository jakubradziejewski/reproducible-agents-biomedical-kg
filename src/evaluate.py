"""Compare structured agent answers with the gold result."""
import itertools
import json
import re


def _norm(v):
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, str):
        return v.strip().lower()
    if isinstance(v, (list, tuple)):
        return tuple(_norm(item) for item in v)
    if isinstance(v, dict):
        items = [(_norm(key), _norm(value)) for key, value in v.items()]
        return tuple(sorted(items, key=lambda item: repr(item[0])))
    if isinstance(v, set):
        return frozenset(_norm(item) for item in v)
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


def parse_answer_rows(answer, gold_rows):
    """Parse the model's final JSON array and align its columns to the gold schema."""
    text = (answer or "").strip()
    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as exc:
        return [], f"Final answer is not valid JSON: {exc.msg}"

    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return [], "Final answer must be a JSON array of row objects."

    if not gold_rows:
        return rows, None

    columns = list(gold_rows[0])
    expected = set(columns)
    for row in rows:
        if len(row) != len(columns):
            return [], f"Each answer row must contain exactly {len(columns)} requested fields."
    return [
        ({column: row[column] for column in columns}
         if set(row) == expected
         else {column: value for column, value in zip(columns, row.values())})
        for row in rows
    ], None


def score_final_answer(answer, gold_rows, ordered=False, trap=False):
    """Score only the model's final structured answer, never its intermediate tool calls."""
    pred_rows, parse_error = parse_answer_rows(answer, gold_rows)
    if parse_error:
        return pred_rows, {
            "exact": False, "precision": 0.0, "recall": 0.0, "f1": 0.0,
            "answer_parse_error": parse_error,
        }
    return pred_rows, {
        **score(pred_rows, gold_rows, ordered, trap),
        "answer_parse_error": None,
    }


if __name__ == "__main__":
    # Self-test: gold vs itself must be perfect; damaged copies must not be.
    for line in open("data/questions.jsonl", encoding="utf-8"):
        q = json.loads(line)
        g = q["gold_result"]
        ok = score(g, g, q["ordered"], q["trap"])["exact"]
        _, final_answer = score_final_answer(
            json.dumps(g, ensure_ascii=False), g, q["ordered"], q["trap"]
        )
        dropped = score(g[:-1], g, q["ordered"], q["trap"])["exact"] if len(g) > 1 else None
        reordered = score(g[::-1], g, q["ordered"], q["trap"])["exact"] if len(g) > 1 else None
        print(f"{q['id']}  self={ok}  final-answer-self={final_answer['exact']}  "
              f"drop-last={dropped}  reversed={reordered}")
