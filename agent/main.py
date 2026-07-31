"""Interactive REPL — a thin adapter over Session."""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from agent.policy import ConsoleApprovals
from agent.procurement import ProcurementError
from agent.session import ModelError
from agent.tracing import JsonlSink
from agent.wiring import make_session


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Supplier AR Agent")
    parser.add_argument(
        "--supplier",
        type=int,
        default=int(os.getenv("SUPPLIER_ID", "1")),
        help="Acting Supplier id for this session (default: $SUPPLIER_ID or 1)",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set — copy .env.example to .env and add your key")

    trace_path = (
        Path(__file__).resolve().parent
        / "traces"
        / f"session-{datetime.now(UTC):%Y%m%dT%H%M%S}.jsonl"
    )
    try:
        session = make_session(
            args.supplier, permissions=ConsoleApprovals(), trace=JsonlSink(trace_path)
        )
    except ProcurementError as exc:
        raise SystemExit(
            f"cannot start: {exc.message} — is the API running "
            "(uvicorn api.main:app) and the supplier id valid?"
        ) from exc

    print(f"Supplier AR Agent — acting for {session.supplier_name} (#{session.supplier_id})")
    print(f"trace: {trace_path}")
    print("-" * 40)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input or user_input.lower() in ("quit", "exit"):
            break
        try:
            result = session.ask(user_input)
        except ModelError as exc:
            print(f"\n[model error — try again] {exc}")
            continue
        for call in result.tool_calls:
            marker = f" [{call.decision}]" if call.gated else ""
            print(f"  -> {call.name}({call.arguments}){marker}")
        print(f"\nAssistant: {result.answer}")


if __name__ == "__main__":
    main()
