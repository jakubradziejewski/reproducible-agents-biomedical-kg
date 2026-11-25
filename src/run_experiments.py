"""Run models x questions x repetitions and log everything to results/."""
import argparse
import hashlib
import json
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv

from agent import run_agent
from evaluate import _rows, score_final_answer
from models import MODELS

load_dotenv()

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


def exception_details(exc):
    """Include leaf errors when async libraries wrap failures in exception groups."""
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(exception_details(child) for child in exc.exceptions)
    return f"{type(exc).__name__}: {exc}"


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
        print(f"  final answer exact: {g_ok['exact'].mean():.2f}   final answer F1: {g_ok['f1'].mean():.2f}")
        print(f"  mean steps     : {g_ok['n_steps'].mean():.1f}   mean tokens: {g_ok['tokens'].mean():.0f}")
        print(f"  exact by level : {g_ok.groupby('level')['exact'].mean().round(2).to_dict()}")
        if "answer_parse_error" in g_ok:
            invalid = g_ok["answer_parse_error"].notna().mean()
            print(f"  invalid final JSON: {invalid:.0%} of runs")
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
            skip_model = False
            for q in questions:
                for rep in range(args.reps):
                    rec = {"model": mname, "model_id": cfg["model"], "qid": q["id"],
                           "level": q["level"], "rep": rep, "time": datetime.now().isoformat()}
                    try:
                        rec.update(run_agent(cfg, q["question"], args.max_steps))
                        rec["final_cypher"] = final_query(rec)
                        answer_rows, metrics = score_final_answer(
                            rec.get("final_answer"), q["gold_result"], q["ordered"], q["trap"]
                        )
                        rec["pred_rows"] = answer_rows[:200]
                        rec.update(metrics)
                        rec["result_sig"] = sig(answer_rows, q["ordered"])
                        print(f"{mname:<20} {q['id']} r{rep} exact={rec['exact']!s:<5} "
                              f"steps={rec['n_steps']} tokens={rec['tokens']}")
                    except Exception as e:  # infrastructure failures are not counted as model mistakes
                        rec["infra_error"] = exception_details(e)[:1000]
                        print(f"{mname:<20} {q['id']} r{rep} INFRA ERROR: {rec['infra_error'][:150]}")
                        if "402" in rec["infra_error"] or "credit" in rec["infra_error"].lower():
                            print("Credits exhausted: stopping. Partial results are saved.")
                            stop = True
                        elif "team_model_access_denied" in rec["infra_error"]:
                            print(f"Model {mname} is not available to this team; skipping its remaining runs.")
                            skip_model = True
                    f.write(json.dumps(rec, default=str, ensure_ascii=False) + "\n")
                    f.flush()
                    records.append(rec)
                    if stop or skip_model:
                        break
                if stop or skip_model:
                    break
            if stop:
                break
    print(f"\nLog: {out}")
    summarize(records)


if __name__ == "__main__":
    main()
