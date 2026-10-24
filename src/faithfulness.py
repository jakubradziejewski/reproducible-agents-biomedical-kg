"""Does the final answer text agree with what the query actually returned?"""
import re

_BULLET = re.compile(r"^\s*(?:[-*\u2022]|\d+[.)])\s+(.+?)\s*$", re.M)


def faithfulness(answer, rows):
    """Return (unsupported_items, missing_values)."""
    text = answer or ""
    low = text.lower()
    vals = {str(v).strip() for r in rows for v in r.values() if isinstance(v, str) and v.strip()}
    low_vals = {v.lower() for v in vals}
    missing = sorted(v for v in vals if v.lower() not in low)
    items = [re.sub(r"[*_`]", "", m).strip() for m in _BULLET.findall(text)]
    unsupported = [i for i in items if i and not any(v in i.lower() for v in low_vals)]
    # a single numeric answer (a count) must appear in the text
    if len(rows) == 1 and len(rows[0]) == 1:
        v = next(iter(rows[0].values()))
        if isinstance(v, (int, float)) and not isinstance(v, bool) and str(v) not in text:
            missing.append(str(v))
    return unsupported, missing
