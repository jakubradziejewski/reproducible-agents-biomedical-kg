"""Re-check a saved log for answer faithfulness (no API calls)."""
import glob
import json
import os
import sys

from faithfulness import faithfulness

path = sys.argv[1] if len(sys.argv) > 1 else max(glob.glob("results/pilot_*.jsonl"), key=os.path.getmtime)
print("Log:", path)
for line in open(path, encoding="utf-8"):
    r = json.loads(line)
    if r.get("infra_error"):
        continue
    unsup, miss = faithfulness(r.get("final_answer"), r.get("pred_rows", []))
    print(f"{r['qid']} exact={r.get('exact')}  unsupported={unsup}  missing={miss[:5]}")
