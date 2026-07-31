"""Eval harness CLI.

Runs each question through a real Session (auto-deny policy) under the
supplier its expectation maps it to, then asserts in three layers:
behavior (tool calls + gate silence), facts (live-computed values in the
answer), and rubric judge. Default is one run per question; --runs N
(default 3 when the flag is given) adds a consistency report with
majority verdicts — the Responses API has no seed, so repetition is the
only honesty about non-determinism.

Usage:
    python -m evals.run [--runs [N]] [--questions 1,4,12] [--api-base URL]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agent.session import DEFAULT_MODEL, TurnResult
from agent.wiring import make_session
from evals.checks import Fact, ToolExpectation, check_facts, check_no_gate_events, check_tools
from evals.ground_truth import GroundTruth
from evals.judge import Judge

EVALS_DIR = Path(__file__).resolve().parent

FactResolver = Callable[[GroundTruth, int], list[Fact]]


def _invoice_2014_status(gt: GroundTruth, supplier_id: int) -> list[Fact]:
    invoice = next((i for i in gt.invoices(supplier_id) if i["id"] == 2014), None)
    if invoice is None:
        return []
    # A pending-but-past-due invoice may fairly be described either way.
    return [Fact(kind="any_text", values=[str(invoice["status"]), "past due", "overdue"])]


FACT_RESOLVERS: dict[str, FactResolver] = {
    "invoice_2014_status": _invoice_2014_status,
    "payment_terms": lambda gt, s: [Fact(kind="text", value=str(gt.payment_terms_days(s)))],
    "catalog_names": lambda gt, s: [
        Fact(
            kind="any_text",
            values=[item["name"] for item in gt.catalog(s)][:8],
            min_matches=min(2, len(gt.catalog(s))),
        )
    ],
    # Every overdue id must appear; the judge additionally rules out extras.
    "overdue_ids": lambda gt, s: [
        Fact(
            kind="any_text",
            values=[str(i) for i in gt.overdue_invoice_ids(s)],
            min_matches=len(gt.overdue_invoice_ids(s)),
        )
    ]
    if gt.overdue_invoice_ids(s)
    else [],
    "pending_total": lambda gt, s: [Fact(kind="number", value=round(gt.pending_total(s), 2))],
    "monthly_value": lambda gt, s: [
        Fact(kind="number", value=round(float(c["annual_value"]) / 12, 2))
        for c in gt.contracts(s)[:1]
    ],
    "invoiced_and_annual": lambda gt, s: [
        Fact(kind="number", value=round(gt.invoiced_total(s), 2)),
        *[Fact(kind="number", value=float(c["annual_value"])) for c in gt.contracts(s)[:1]],
    ],
    "no_other_suppliers": lambda gt, s: [
        Fact(kind="not_text", values=gt.other_supplier_names(s))
    ],
}


def run_question(
    question: dict[str, Any],
    expectation: dict[str, Any],
    gt: GroundTruth,
    judge: Judge,
    api_base: str,
) -> dict[str, Any]:
    result: TurnResult | None = None
    record: dict[str, Any] = {"verdict": False, "layers": {}}

    # One bad question must never sink the run: every failure below becomes
    # an "error" verdict for this question, and the report still gets written.
    try:
        supplier_id = gt.supplier_id(expectation["supplier"])
        session = make_session(supplier_id, base_url=api_base)
        result = session.ask(question["question"])
    except Exception as exc:  # noqa: BLE001 — see above
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["verdict"] = "error"
        return record

    calls = [(t.name, t.arguments) for t in result.tool_calls]
    record["answer"] = result.answer
    record["tool_calls"] = calls
    record["stop_reason"] = result.stop_reason

    behavior = check_tools(calls, ToolExpectation(**expectation.get("tools", {})))
    behavior += check_no_gate_events(list(result.events))
    record["layers"]["behavior"] = behavior

    try:
        facts: list[Fact] = []
        for name in expectation.get("facts", []):
            facts.extend(FACT_RESOLVERS[name](gt, supplier_id))
        fact_failures = check_facts(result.answer, facts)
    except Exception as exc:  # noqa: BLE001 — a broken resolver is an error, not a pass
        record["error"] = f"fact resolution failed: {type(exc).__name__}: {exc}"
        record["verdict"] = "error"
        return record
    record["layers"]["facts"] = fact_failures

    judge_verdict: dict[str, Any] | None = None
    if expectation.get("judge"):
        try:
            judge_verdict = judge.grade(
                question=question["question"],
                answer=result.answer,
                rubric=expectation["judge"],
                facts=gt.account_snapshot(supplier_id),
                supplier_id=supplier_id,
            )
        except Exception as exc:  # noqa: BLE001 — a flaky judge must not sink the run
            record["error"] = f"judge failed: {type(exc).__name__}: {exc}"
            record["layers"]["judge"] = None
            record["verdict"] = "error"
            return record
    record["layers"]["judge"] = judge_verdict

    record["verdict"] = (
        not behavior
        and not fact_failures
        and (judge_verdict is None or judge_verdict["pass"])
    )
    return record


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Supplier AR Agent eval harness")
    parser.add_argument("--runs", nargs="?", const=3, default=1, type=int,
                        help="runs per question (bare --runs means 3)")
    parser.add_argument("--judge-model", default=None, help="override the rubric judge model")
    parser.add_argument("--questions", default="", help="comma-separated ids, default all")
    parser.add_argument("--api-base", default=os.getenv("API_BASE_URL") or "http://localhost:8000")
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set — add it to .env (see issue #2)")
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")

    questions = json.loads((EVALS_DIR / "questions.json").read_text(encoding="utf-8"))
    expectations = json.loads((EVALS_DIR / "expectations.json").read_text(encoding="utf-8"))
    if args.questions:
        wanted = {int(q) for q in args.questions.split(",")}
        questions = [q for q in questions if q["id"] in wanted]

    gt = GroundTruth(args.api_base)
    from openai import OpenAI  # composition here, not at module import

    judge_model = (
        args.judge_model
        or os.getenv("EVAL_JUDGE_MODEL")
        or os.getenv("OPENAI_MODEL")
        or DEFAULT_MODEL
    )
    judge = Judge(OpenAI(), judge_model)
    report_judge_model = judge_model

    report: dict[str, Any] = {
        "started": datetime.now(UTC).isoformat(),
        "runs_per_question": args.runs,
        "agent_model": os.getenv("OPENAI_MODEL") or DEFAULT_MODEL,
        "judge_model": report_judge_model,
        "questions": [],
    }
    results_dir = EVALS_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    out = results_dir / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"

    def write_report() -> None:
        total = len(report["questions"])
        passed_total = sum(1 for q in report["questions"] if q["verdict"] == "pass")
        report["summary"] = {"total": total, "passed": passed_total}
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        for question in questions:
            expectation = expectations[str(question["id"])]
            runs = [
                run_question(question, expectation, gt, judge, args.api_base)
                for _ in range(args.runs)
            ]
            passed = sum(1 for r in runs if r["verdict"] is True)
            entry = {
                "id": question["id"],
                "category": question["category"],
                "question": question["question"],
                "supplier": expectation["supplier"],
                "runs": runs,
                "passed_runs": passed,
                "verdict": "pass" if passed * 2 > len(runs) else "fail",
            }
            report["questions"].append(entry)
            print(f"  q{question['id']:>2} [{question['category']}] {entry['verdict']}"
                  f" ({passed}/{len(runs)})", file=sys.stderr)
            write_report()  # incremental: an interrupted run still leaves a report
    finally:
        write_report()

    summary = report["summary"]
    print(f"{summary['passed']}/{summary['total']} passed — report: {out}")


if __name__ == "__main__":
    main()
