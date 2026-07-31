"""Deterministic assertion layers: fact matching and tool-call matching."""

from __future__ import annotations

import unittest
from typing import Any, ClassVar

from evals.checks import (
    Fact,
    ToolExpectation,
    check_facts,
    check_no_gate_events,
    check_tools,
)


class NumberFactTest(unittest.TestCase):
    def test_matches_currency_formatting_variants(self) -> None:
        for text in ("total is $19,500.00", "19500 USD pending", "USD 19,500"):
            failures = check_facts(text, [Fact(kind="number", value=19500.0)])
            self.assertEqual(failures, [], text)

    def test_rejects_wrong_or_absent_numbers(self) -> None:
        failures = check_facts("total is $1,950.00", [Fact(kind="number", value=19500.0)])
        self.assertEqual(len(failures), 1)

    def test_tolerates_cents(self) -> None:
        failures = check_facts("about 19500.004 dollars", [Fact(kind="number", value=19500.0)])
        self.assertEqual(failures, [])


class TextFactTest(unittest.TestCase):
    def test_text_is_case_insensitive(self) -> None:
        self.assertEqual(check_facts("Status: PENDING", [Fact(kind="text", value="pending")]), [])

    def test_any_text_needs_min_matches(self) -> None:
        fact = Fact(kind="any_text", values=["2007", "2008", "2009"], min_matches=2)
        self.assertEqual(check_facts("overdue: 2007 and 2009", [fact]), [])
        self.assertEqual(len(check_facts("overdue: 2007 only", [fact])), 1)

    def test_not_text_fails_on_forbidden_mention(self) -> None:
        fact = Fact(kind="not_text", values=["Acme Technology"])
        self.assertEqual(check_facts("I can only see your account.", [fact]), [])
        self.assertEqual(len(check_facts("Acme Technology owes you", [fact])), 1)


class ToolMatchingTest(unittest.TestCase):
    CALLS: ClassVar[list[tuple[str, dict[str, Any]]]] = [
        ("list_invoices", {"status": "pending"}),
        ("get_invoice", {"invoice_id": 2014}),
    ]

    def test_any_of_matches_name_and_args_subset(self) -> None:
        expectation = ToolExpectation(
            any_of=[{"name": "get_invoice", "args_subset": {"invoice_id": 2014}}]
        )
        self.assertEqual(check_tools(self.CALLS, expectation), [])

    def test_any_of_fails_when_no_candidate_matches(self) -> None:
        expectation = ToolExpectation(
            any_of=[{"name": "get_invoice", "args_subset": {"invoice_id": 9999}}]
        )
        self.assertEqual(len(check_tools(self.CALLS, expectation)), 1)

    def test_all_of_requires_every_tool(self) -> None:
        expectation = ToolExpectation(
            all_of=[{"name": "list_invoices"}, {"name": "list_contracts"}]
        )
        failures = check_tools(self.CALLS, expectation)
        self.assertEqual(len(failures), 1)
        self.assertIn("list_contracts", failures[0])

    def test_name_only_matches_any_args(self) -> None:
        expectation = ToolExpectation(any_of=[{"name": "list_invoices"}])
        self.assertEqual(check_tools(self.CALLS, expectation), [])


class GateEventTest(unittest.TestCase):
    def test_read_only_run_must_not_consult_the_gate(self) -> None:
        clean = [{"event": "turn_started"}, {"event": "tool_call"}]
        dirty = [*clean, {"event": "gate_decision", "gen_ai.tool.name": "create_invoice"}]
        self.assertEqual(check_no_gate_events(clean), [])
        self.assertEqual(len(check_no_gate_events(dirty)), 1)


if __name__ == "__main__":
    unittest.main()
