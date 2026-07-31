"""Judge — an unusable verdict must be an error, never a silent pass."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any, cast

from openai import OpenAI

from evals.judge import Judge, JudgeError


class FakeResponses:
    def __init__(self, response: SimpleNamespace) -> None:
        self._response = response
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.kwargs = kwargs
        return self._response


class FakeClient:
    def __init__(self, response: SimpleNamespace) -> None:
        self.responses = FakeResponses(response)


def grade_with(response: SimpleNamespace) -> dict[str, Any]:
    client = FakeClient(response)
    judge = Judge(cast(OpenAI, client), "test-judge")
    return judge.grade(
        question="q", answer="a", rubric="r", facts={"x": 1}, supplier_id=2
    )


class JudgeTest(unittest.TestCase):
    def test_parses_a_completed_verdict(self) -> None:
        response = SimpleNamespace(
            status="completed", output_text='{"pass": true, "reasons": ["ok"]}'
        )
        self.assertEqual(grade_with(response)["pass"], True)

    def test_refusal_empty_output_raises_judge_error(self) -> None:
        with self.assertRaises(JudgeError):
            grade_with(SimpleNamespace(status="completed", output_text=""))

    def test_truncated_json_raises_judge_error(self) -> None:
        with self.assertRaises(JudgeError):
            grade_with(SimpleNamespace(status="completed", output_text='{"pass": tr'))

    def test_incomplete_status_raises_judge_error(self) -> None:
        response = SimpleNamespace(
            status="incomplete", output_text='{"pass": true, "reasons": []}'
        )
        with self.assertRaises(JudgeError):
            grade_with(response)

    def test_uses_strict_json_schema_format(self) -> None:
        client = FakeClient(
            SimpleNamespace(status="completed", output_text='{"pass": true, "reasons": []}')
        )
        Judge(cast(OpenAI, client), "test-judge").grade(
            question="q", answer="a", rubric="r", facts={}, supplier_id=1
        )
        text_format = client.responses.kwargs["text"]["format"]
        self.assertEqual(text_format["type"], "json_schema")
        self.assertTrue(text_format["strict"])


if __name__ == "__main__":
    unittest.main()
