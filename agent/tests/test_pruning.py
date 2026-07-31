"""prune() — pure-function seam."""

from __future__ import annotations

import unittest

from agent.pruning import PRUNED_STUB, estimate_chars, prune


def output_item(call_id: str, payload: str) -> dict[str, str]:
    return {"type": "function_call_output", "call_id": call_id, "output": payload}


class PruneTest(unittest.TestCase):
    def test_under_budget_is_untouched(self) -> None:
        conversation = [{"role": "user", "content": "hi"}, output_item("c1", "x" * 50)]
        pruned, elided = prune(conversation, budget_chars=10_000, protect_from=2)
        self.assertEqual(elided, 0)
        self.assertIs(pruned, conversation)

    def test_elides_oldest_outputs_first_and_respects_budget(self) -> None:
        conversation = [
            {"role": "developer", "content": "sys"},
            output_item("c1", "a" * 5_000),
            output_item("c2", "b" * 5_000),
            {"role": "user", "content": "latest question"},
        ]
        pruned, elided = prune(conversation, budget_chars=6_000, protect_from=3)
        self.assertEqual(elided, 1)
        self.assertEqual(pruned[1]["output"], PRUNED_STUB)
        self.assertEqual(pruned[2]["output"], "b" * 5_000)
        self.assertLessEqual(estimate_chars(pruned), 6_000)

    def test_never_touches_protected_or_non_output_items(self) -> None:
        conversation = [
            {"role": "developer", "content": "s" * 9_000},
            {"role": "user", "content": "q"},
            output_item("c1", "current-turn " * 500),
        ]
        pruned, elided = prune(conversation, budget_chars=1_000, protect_from=1)
        self.assertEqual(elided, 0)
        self.assertEqual(pruned[0]["content"], "s" * 9_000)
        self.assertNotEqual(pruned[2]["output"], PRUNED_STUB)

    def test_item_count_and_call_ids_survive(self) -> None:
        conversation = [output_item("c1", "a" * 9_000), {"role": "user", "content": "q"}]
        pruned, _ = prune(conversation, budget_chars=100, protect_from=1)
        self.assertEqual(len(pruned), 2)
        self.assertEqual(pruned[0]["call_id"], "c1")

    def test_already_elided_outputs_are_skipped(self) -> None:
        conversation = [
            output_item("c1", PRUNED_STUB),
            output_item("c2", "z" * 9_000),
            {"role": "user", "content": "q"},
        ]
        pruned, elided = prune(conversation, budget_chars=100, protect_from=2)
        self.assertEqual(elided, 1)
        self.assertEqual(pruned[1]["output"], PRUNED_STUB)


if __name__ == "__main__":
    unittest.main()
