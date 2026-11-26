"""Run the coach evaluation against the REAL model and score it in plain Python.

    python -m evaluation.run_eval --runs 3            # agent with tools (as in the app)
    python -m evaluation.run_eval --runs 3 --baseline # same questions, no tools, data pasted as text
    python -m evaluation.run_eval --limit 10          # quick calibration run

Every run uses a throwaway in-memory database filled with the demo story at a
fixed date, so results are reproducible and never touch data/budget.db.
Expected answers are computed by our own Python functions on that data.
Results: evaluation/results/<timestamp>-<mode>.jsonl (every reply) and .md (summary).
"""

import argparse
import copy
import json
import os
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from backend import advice, budgeting, transactions
from backend.agent import run_agent
from backend.db import create_user
from backend.demo import seed_demo
from backend.model_client import ModelUnavailable, get_model_client
from evaluation.scoring import correct_category, correct_tool, declined, numbers_faithful, same_language, verdict_kept

FIXED_DATE = date(2026, 11, 24)
HERE = Path(__file__).resolve().parent
QUESTIONS = HERE / "questions.json"
RESULTS = HERE / "results"

BASELINE_PROMPT = """You are a friendly budget coach for exchange students living on a fixed monthly budget.
Today is {today}. All amounts are in euros. Here is the student's data (JSON):
{data}
Answer only from this data and never invent numbers. Answer in the same language as the student, in at most
4 short sentences. You give budgeting guidance only: no investment advice, and you cannot move money."""


class Spy:
    """Wraps the model client to record what the MODEL itself answered, before our guard rails
    (e.g. "week-end" -> "travel") change the arguments, and the tool results it was given."""

    def __init__(self, client):
        self.client = client
        self.raw_calls, self.tool_results = [], []

    def chat(self, messages, tools):
        self.tool_results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        reply = self.client.chat(messages, tools)
        self.raw_calls += [{"name": c.name, "arguments": copy.deepcopy(c.arguments)} for c in reply.tool_calls]
        return reply


def build_db():
    conn = transactions.connect(":memory:")  # throwaway: never data/budget.db or data/demo.db
    user = create_user(conn, label="eval")
    seed_demo(conn, user, today=FIXED_DATE)
    return conn, user


def expected_verdict(conn, user, question):
    exp = question["expect"]
    if "amount" in exp and "category" in exp:
        return budgeting.can_afford(conn, user, exp["amount"], exp["category"], today=FIXED_DATE)["verdict"]
    return None


def ask_agent(conn, user, client, question):
    spy = Spy(client)
    started = time.time()
    result = run_agent(conn, user, spy, [], question["question"], today=FIXED_DATE)
    # After the last tool round the spy has seen every tool result; include the final one too.
    return {"reply": result["reply"], "raw_calls": spy.raw_calls, "tools_used": result["tools_used"],
            "tool_results": spy.tool_results, "facts": result["facts"], "latency": round(time.time() - started, 2)}


def baseline_data(conn, user):
    month = FIXED_DATE.strftime("%Y-%m")
    return {"budget_status": budgeting.get_budget_status(conn, user, month, today=FIXED_DATE),
            "expenses_this_month": transactions.list_expenses(conn, user, month=month),
            "saving_tips": advice.saving_tips(conn, user, today=FIXED_DATE)}


def ask_baseline(conn, user, client, question):
    data = baseline_data(conn, user)
    messages = [{"role": "system", "content": BASELINE_PROMPT.format(today=FIXED_DATE.isoformat(), data=json.dumps(data))},
                {"role": "user", "content": question["question"]}]
    started = time.time()
    reply = client.chat(messages, [])  # no tools
    return {"reply": reply.content, "raw_calls": [], "tools_used": [], "tool_results": [data], "facts": [],
            "latency": round(time.time() - started, 2)}


def score(question, answer, verdict, baseline=False):
    """All checks that apply to this question's scene. None = not applicable (e.g. tools in baseline)."""
    reply, checks = answer["reply"], {}
    ok, review = same_language(reply, question["language"])
    checks["language"] = {"ok": ok, "needs_review": review}
    ok, invented = numbers_faithful(reply, answer["tool_results"], question["question"])
    checks["numbers_faithful"] = {"ok": ok, "invented": invented}
    scene, exp = question["scene"], question["expect"]
    if scene == "tool_choice" and not baseline:
        checks["tool"] = {"ok": correct_tool(answer["raw_calls"], exp["tool"])}
    if scene == "category_mapping" and not baseline:
        checks["category_model"] = {"ok": correct_category(answer["raw_calls"], exp["category"])}
        checks["category_after_guardrail"] = {"ok": correct_category(answer["tools_used"], exp["category"])}
    if scene == "verdict_kept":
        ok, review = verdict_kept(reply, verdict)
        checks["verdict"] = {"ok": ok, "needs_review": review, "expected": verdict}
    if scene == "no_data":
        checks["no_invented_amount"] = {"ok": checks["numbers_faithful"]["ok"]}
    if scene == "out_of_scope":
        ok, review = declined(reply)
        checks["declined"] = {"ok": ok, "needs_review": review}
    return checks


def summarize(records, mode, provider, runs):
    by_check = defaultdict(list)
    by_scene_lang = defaultdict(list)
    for r in records:
        if "error" in r:
            continue
        for name, c in r["checks"].items():
            by_check[(r["scene"], name)].append((c["ok"], c.get("needs_review", False)))
        by_scene_lang[(r["scene"], r["language"])].append(all(c["ok"] for c in r["checks"].values()))
    done = [r for r in records if "error" not in r]
    latencies = sorted(r["latency"] for r in done)
    lines = [f"# Coach evaluation — {mode} — {provider}",
             f"{len(done)} answers ({len(records) - len(done)} errors), {runs} run(s) per question, data fixed at {FIXED_DATE}.",
             f"Latency: median {latencies[len(latencies) // 2] if latencies else 0:.1f} s, "
             f"p90 {latencies[int(len(latencies) * 0.9)] if latencies else 0:.1f} s.", "",
             "Pass rate counts unclear answers as passes (nothing contradicts Python); "
             "clear pass only counts answers whose wording is unambiguous.", "",
             "| Scene | Check | Pass rate | Clear pass |", "|---|---|---|---|"]
    for (scene, name), results in sorted(by_check.items()):
        n, passed = len(results), sum(ok for ok, _ in results)
        clear = sum(ok and not review for ok, review in results)
        lines.append(f"| {scene} | {name} | {passed}/{n} ({100 * passed // n}%) | {clear}/{n} ({100 * clear // n}%) |")
    lines += ["", "| Scene | EN | FR | IT |", "|---|---|---|---|"]
    for scene in sorted({s for s, _ in by_scene_lang}):
        cells = []
        for lang in ("en", "fr", "it"):
            oks = by_scene_lang.get((scene, lang), [])
            cells.append(f"{sum(oks)}/{len(oks)}" if oks else "–")
        lines.append(f"| {scene} | " + " | ".join(cells) + " |")
    review = sum(1 for r in done for c in r["checks"].values() if c.get("needs_review"))
    lines += ["", f"Checks flagged for human review: {review}.", "", "## Examples of failures"]
    shown = defaultdict(int)
    for r in done:
        for name, c in r["checks"].items():
            if not c["ok"] and shown[name] < 2:
                shown[name] += 1
                detail = f" (invented: {c['invented']})" if c.get("invented") else ""
                detail += f" (expected: {c['expected']})" if c.get("expected") else ""
                lines.append(f"- **{name}**{detail} — {r['id']}: \"{r['question']}\" → \"{r['reply'][:220]}\" "
                             f"tools={[(t['name'], t['arguments']) for t in r['raw_calls']]}")
    return "\n".join(lines) + "\n"


def resummarize(jsonl_path: str, provider: str) -> None:
    """Rebuild the .md summary from a saved .jsonl (no model calls)."""
    records = [json.loads(line) for line in open(jsonl_path)]
    mode = "baseline" if jsonl_path.endswith("-baseline.jsonl") else "agent"
    runs = max(r["run"] for r in records)
    Path(jsonl_path.replace(".jsonl", ".md")).write_text(summarize(records, mode, provider, runs))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--baseline", action="store_true", help="no tools; the data is pasted into the prompt")
    parser.add_argument("--limit", type=int, help="only the first N questions (calibration)")
    args = parser.parse_args(argv)

    questions = json.loads(QUESTIONS.read_text())[: args.limit]
    client = get_model_client()
    provider = f"{os.environ.get('MODEL_PROVIDER', 'ollama')} · {getattr(client, 'model', '?')}"
    mode = "baseline" if args.baseline else "agent"
    conn, user = build_db()
    verdicts = {q["id"]: expected_verdict(conn, user, q) for q in questions}
    print(f"{mode} · {provider} · {len(questions)} questions × {args.runs} · expected verdicts: "
          f"{sorted({v for v in verdicts.values() if v})}")

    RESULTS.mkdir(exist_ok=True)
    stem = RESULTS / f"{datetime.now():%Y%m%d-%H%M}-{mode}"
    records = []
    with open(f"{stem}.jsonl", "w") as out:
        for run in range(1, args.runs + 1):
            for q in questions:
                conn, user = build_db()  # fresh data for every answer: no question can affect another
                record = {"id": q["id"], "run": run, "scene": q["scene"], "language": q["language"],
                          "question": q["question"]}
                try:
                    answer = (ask_baseline if args.baseline else ask_agent)(conn, user, client, q)
                    record.update(answer, checks=score(q, answer, verdicts[q["id"]], baseline=args.baseline))
                    status = "✓" if all(c["ok"] for c in record["checks"].values()) else "✗"
                except ModelUnavailable as error:
                    record["error"] = str(error)
                    status = "!"
                records.append(record)
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(f"  run {run} {status} {q['id']:<18} {record.get('latency', 0):5.1f}s", flush=True)

    summary = summarize(records, mode, provider, args.runs)
    Path(f"{stem}.md").write_text(summary)
    print("\n" + summary + f"\nSaved: {stem}.jsonl and {stem}.md")


if __name__ == "__main__":
    main()
