"""Run models x questions x repetitions and log everything to results/."""
import argparse
import hashlib
import json
import re
from datetime import datetime
from faithfulness import faithfulness
import pandas as pd
from dotenv import load_dotenv

from agent import run_agent
from db import run_cypher
from evaluate import _rows, score
from models import MODELS

load_dotenv()

NOT_FOUND = re.compile(r"not found|no (such )?(disease|result|match|record|data)|does not exist|"
                       r"doesn't exist|could not find|couldn't find|not in the (graph|database)", re.I)


def final_query(rec):
    for s in reversed(rec["steps"]):
        if s["cypher"] and "error" not in s["result"]:
            return s["cypher"]
    return None


def sig(rows, ordered):
    items = [repr(t) for t in _rows(rows)]
    if not ordered:
        items.sort()
    return hashlib.sha1("|".join(items).encode()).hexdigest()[:12]


def summarize(records):
    df = pd.DataFrame(records)
    if "infra_error" not in df:
        df["infra_error"] = None
    ok = df[df["infra_error"].isna()]
    print("\n=== Summary ===")
    for m, g in df.groupby("model"):
        g_ok = ok[ok["model"] == m]
        print(f"\n{m}: {len(g)} runs, {len(g) - len(g_ok)} infrastructure errors")
        if g_ok.empty:
            continue
        print(f"  exact accuracy : {g_ok['exact'].mean():.2f}   mean F1: {g_ok['f1'].mean():.2f}")
        print(f"  mean steps     : {g_ok['n_steps'].mean():.1f}   mean tokens: {g_ok['tokens'].mean():.0f}")
        print(f"  exact by level : {g_ok.groupby('level')['exact'].mean().round(2).to_dict()}")
        if "unsupported" in g_ok:
            print(f"  answer text has unsupported items in {g_ok['unsupported'].apply(bool).mean():.0%} of runs")
        multi = g_ok.groupby("qid").filter(lambda x: len(x) > 1)
        if not multi.empty:
            same_res = multi.groupby("qid")["result_sig"].nunique().eq(1).mean()
            same_cy = multi.groupby("qid")["final_cypher"].nunique().eq(1).mean()
            print(f"  repeatability  : identical result in {same_res:.0%} of questions, "
                  f"identical Cypher text in {same_cy:.0%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True, help="comma-separated keys from models.py")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--only", default="", help="comma-separated question ids, e.g. q01,q03")
    ap.add_argument("--max-steps", type=int, default=6)
    args = ap.parse_args()

    questions = [json.loads(line) for line in open("data/questions.jsonl", encoding="utf-8")]
    if args.only:
        keep = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in keep]

    out = f"results/pilot_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    records, stop = [], False
    with open(out, "w", encoding="utf-8") as f:
        for mname in args.models.split(","):
            cfg = MODELS[mname]
            for q in questions:
                for rep in range(args.reps):
                    rec = {"model": mname, "model_id": cfg["model"], "qid": q["id"],
                           "level": q["level"], "rep": rep, "time": datetime.now().isoformat()}
                    try:
                        rec.update(run_agent(cfg, q["question"], args.max_steps))
                        cy = final_query(rec)
                        rec["final_cypher"] = cy
                        full = run_cypher(cy, max_rows=None) if cy else None
                        rows = full["rows"] if full and "error" not in full else []
                        rec["pred_rows"] = rows[:200]
                        rec.update(score(rows, q["gold_result"], q["ordered"], q["trap"]))
                        rec["result_sig"] = sig(rows, q["ordered"])
                            # Check faithfulness of the answer
                        unsup, miss = faithfulness(rec.get("final_answer"), rows)
                        rec["unsupported"], rec["missing"] = unsup, miss[:20]
                        if q["trap"]:
                            rec["trap_text_ok"] = bool(NOT_FOUND.search(rec.get("final_answer") or ""))
                            rec["exact"] = rec["exact"] and rec["trap_text_ok"]
                        print(f"{mname:<20} {q['id']} r{rep} exact={rec['exact']!s:<5} "
                              f"steps={rec['n_steps']} tokens={rec['tokens']}")
                    except Exception as e:  # network, credits, bad model id: never counted as a wrong answer
                        rec["infra_error"] = f"{type(e).__name__}: {str(e)[:300]}"
                        print(f"{mname:<20} {q['id']} r{rep} INFRA ERROR: {rec['infra_error'][:150]}")
                        if "402" in rec["infra_error"] or "credit" in rec["infra_error"].lower():
                            print("Credits exhausted: stopping. Partial results are saved.")
                            stop = True
                    f.write(json.dumps(rec, default=str, ensure_ascii=False) + "\n")
                    f.flush()
                    records.append(rec)
                    if stop:
                        break
                if stop:
                    break
            if stop:
                break
    print(f"\nLog: {out}")
    summarize(records)


if __name__ == "__main__":
    main()
