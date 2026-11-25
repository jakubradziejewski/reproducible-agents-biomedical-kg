"""Re-check final-answer scores in a saved experiment log (no API calls)."""
import glob
import json
import os
import sys

path = sys.argv[1] if len(sys.argv) > 1 else max(glob.glob("results/pilot_*.jsonl"), key=os.path.getmtime)
print("Log:", path)
for line in open(path, encoding="utf-8"):
    r = json.loads(line)
    if r.get("infra_error"):
        continue
    print(f"{r['qid']} exact={r.get('exact')}  F1={r.get('f1')}  "
          f"answer_parse_error={r.get('answer_parse_error')}")
