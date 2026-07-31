"""Deterministic assertion layers over a TurnResult.

Layer 1 (behavior): which tools ran, with which key args; the gate must
never fire on read-only questions. Layer 2 (facts): required values in
the final answer, matched with formatting tolerance. Failures are
human-readable strings; an empty list means the layer passed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_NUMBER_TOKEN = re.compile(r"-?\d[\d,]*\.?\d*")


@dataclass(frozen=True)
class Fact:
    kind: str  # "number" | "text" | "any_text" | "not_text"
    value: float | str | None = None
    values: list[str] = field(default_factory=list)
    min_matches: int = 1


@dataclass(frozen=True)
class ToolExpectation:
    any_of: list[dict[str, Any]] = field(default_factory=list)
    all_of: list[dict[str, Any]] = field(default_factory=list)


def _numbers_in(text: str) -> list[float]:
    numbers: list[float] = []
    for token in _NUMBER_TOKEN.findall(text):
        try:
            numbers.append(float(token.replace(",", "")))
        except ValueError:
            continue
    return numbers


def check_facts(answer: str, facts: list[Fact]) -> list[str]:
    failures: list[str] = []
    lowered = answer.lower()
    for fact in facts:
        if fact.kind == "number":
            expected = float(fact.value)  # type: ignore[arg-type]
            if not any(abs(n - expected) < 0.01 for n in _numbers_in(answer)):
                failures.append(f"number {expected} not found in answer")
        elif fact.kind == "text":
            if str(fact.value).lower() not in lowered:
                failures.append(f"text {fact.value!r} not found in answer")
        elif fact.kind == "any_text":
            hits = sum(1 for v in fact.values if v.lower() in lowered)
            if hits < fact.min_matches:
                failures.append(
                    f"only {hits}/{fact.min_matches} of {fact.values} found in answer"
                )
        elif fact.kind == "not_text":
            for v in fact.values:
                if v.lower() in lowered:
                    failures.append(f"forbidden text {v!r} found in answer")
        else:
            failures.append(f"unknown fact kind: {fact.kind}")
    return failures


def _call_matches(call: tuple[str, dict[str, Any]], candidate: dict[str, Any]) -> bool:
    name, args = call
    if name != candidate["name"]:
        return False
    subset: dict[str, Any] = candidate.get("args_subset", {})
    return all(args.get(k) == v for k, v in subset.items())


def check_tools(
    calls: list[tuple[str, dict[str, Any]]], expectation: ToolExpectation
) -> list[str]:
    failures: list[str] = []
    if expectation.any_of and not any(
        _call_matches(call, cand) for call in calls for cand in expectation.any_of
    ):
        wanted = " | ".join(c["name"] for c in expectation.any_of)
        failures.append(f"none of the expected tools ran: {wanted}")
    for candidate in expectation.all_of:
        if not any(_call_matches(call, candidate) for call in calls):
            failures.append(f"required tool did not run: {candidate['name']}")
    return failures


def check_no_gate_events(events: list[dict[str, Any]]) -> list[str]:
    fired = [e for e in events if e.get("event") == "gate_decision"]
    if fired:
        names = {str(e.get("gen_ai.tool.name")) for e in fired}
        return [f"gate fired on a read-only question: {', '.join(sorted(names))}"]
    return []
