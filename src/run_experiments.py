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

CONDITIONS = {
    "baseline": {"t2css": False, "cygnet": False},
    "t2css": {"t2css": True, "cygnet": False},
    "cygnet": {"t2css": False, "cygnet": True},
    "t2css_cygnet": {"t2css": True, "cygnet": True},
}


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
    if "condition" not in df:
        df["condition"] = "baseline"
    ok = df[df["infra_error"].isna()]
    print("\n=== Summary ===")
    for condition, condition_runs in df.groupby("condition"):
        print(f"\nCondition: {condition}")
        for model, runs in condition_runs.groupby("model"):
            successful = ok[(ok["model"] == model) & (ok["condition"] == condition)]
            print(f"  {model}: {len(runs)} runs, "
                  f"{len(runs) - len(successful)} infrastructure errors")
            if successful.empty:
                continue
            print(f"    final answer exact: {successful['exact'].mean():.2f}   "
                  f"final answer F1: {successful['f1'].mean():.2f}")
            print(f"    mean steps     : {successful['n_steps'].mean():.1f}   "
                  f"mean tokens: {successful['tokens'].mean():.0f}")
            print(f"    exact by level : "
                  f"{successful.groupby('level')['exact'].mean().round(2).to_dict()}")
            if "answer_parse_error" in successful:
                invalid = successful["answer_parse_error"].notna().mean()
                print(f"    invalid final JSON: {invalid:.0%} of runs")
            validation_failures = sum(
                step.get("validation", {}).get("ok") is False
                for record in successful.to_dict("records")
                for step in record.get("steps", [])
            )
            if validation_failures:
                print(f"    rejected queries : {validation_failures}")
            multi = successful.groupby("qid").filter(lambda group: len(group) > 1)
            if not multi.empty:
                same_res = multi.groupby("qid")["result_sig"].nunique().eq(1).mean()
                same_cy = multi.groupby("qid")["final_cypher"].nunique().eq(1).mean()
                print(f"    repeatability  : identical result in {same_res:.0%} of questions, "
                      f"identical Cypher text in {same_cy:.0%}")


def load_t2css_prompts(questions):
    path = "data/t2css_context.jsonl"
    contexts = {}
    with open(path, encoding="utf-8") as file:
        for line in file:
            context = json.loads(line)
            contexts[context["id"]] = context

    prompts = {}
    for question in questions:
        context = contexts.get(question["id"])
        if context is None or context.get("question") != question["question"]:
            raise ValueError(
                f"T2CSS context for {question['id']} is missing or stale. "
                "Regenerate it with `uv run python src/t2css.py`."
            )
        prompt = context.get("system_prompts", {}).get("s4_filtered")
        if not isinstance(prompt, str) or not prompt:
            raise ValueError(f"T2CSS filtered prompt missing for {question['id']} in {path}.")
        prompts[question["id"]] = prompt
    return prompts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True, help="comma-separated keys from models.py")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--only", default="", help="comma-separated question ids, e.g. q01,q03")
    ap.add_argument("--max-steps", type=int, default=6)
    ap.add_argument("--conditions", default="baseline",
                    help="comma-separated conditions: " + ", ".join(CONDITIONS))
    args = ap.parse_args()

    condition_names = [name.strip() for name in args.conditions.split(",")]
    if not condition_names or any(not name for name in condition_names):
        ap.error("at least one non-empty condition is required")
    if len(condition_names) != len(set(condition_names)):
        ap.error("conditions must not be repeated")
    unknown_conditions = sorted(set(condition_names) - CONDITIONS.keys())
    if unknown_conditions:
        ap.error(f"unknown condition(s): {', '.join(unknown_conditions)}")
    if args.reps < 1:
        ap.error("--reps must be at least 1")
    model_names = [name.strip() for name in args.models.split(",")]
    if not model_names or any(not name for name in model_names):
        ap.error("at least one model is required")
    unknown_models = sorted(set(model_names) - MODELS.keys())
    if unknown_models:
        ap.error(f"unknown model(s): {', '.join(unknown_models)}")
    questions = [json.loads(line) for line in open("data/questions.jsonl", encoding="utf-8")]
    if args.only:
        keep = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in keep]
    if not questions:
        ap.error("no questions selected")
    t2css_prompts = (
        load_t2css_prompts(questions)
        if any(CONDITIONS[name]["t2css"] for name in condition_names)
        else {}
    )

    out = f"results/pilot_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    records, stop = [], False
    with open(out, "w", encoding="utf-8") as f:
        for condition_name in condition_names:
            condition = CONDITIONS[condition_name]
            for mname in model_names:
                cfg = MODELS[mname]
                skip_model = False
                for q in questions:
                    for rep in range(args.reps):
                        rec = {"condition": condition_name, "model": mname,
                               "model_id": cfg["model"], "qid": q["id"],
                               "level": q["level"], "rep": rep,
                               "time": datetime.now().isoformat()}
                        try:
                            rec.update(run_agent(
                                cfg, q["question"], args.max_steps,
                                system_prompt=t2css_prompts.get(q["id"])
                                if condition["t2css"] else None,
                                cygnet_validation=condition["cygnet"],
                            ))
                            rec["final_cypher"] = final_query(rec)
                            answer_rows, metrics = score_final_answer(
                                rec.get("final_answer"), q["gold_result"], q["ordered"], q["trap"]
                            )
                            rec["pred_rows"] = answer_rows[:200]
                            rec.update(metrics)
                            rec["result_sig"] = sig(answer_rows, q["ordered"])
                            print(f"{condition_name:<16} {mname:<20} {q['id']} r{rep} "
                                  f"exact={rec['exact']!s:<5} steps={rec['n_steps']} "
                                  f"tokens={rec['tokens']}")
                        except Exception as e:  # infrastructure failures are not counted as model mistakes
                            rec["infra_error"] = exception_details(e)[:1000]
                            print(f"{condition_name:<16} {mname:<20} {q['id']} r{rep} "
                                  f"INFRA ERROR: {rec['infra_error'][:150]}")
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
            if stop:
                break
    print(f"\nLog: {out}")
    summarize(records)


if __name__ == "__main__":
    main()
