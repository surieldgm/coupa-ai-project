"""Layer 3: rubric judge via structured outputs.

The judge grades the agent's answer against a per-question rubric and a
FACTS block precomputed by GroundTruth — it never does its own arithmetic,
so a judge failure means the answer disagrees with the facts, not that
two models did math differently.
"""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pass": {"type": "boolean"},
        "reasons": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short reasons; on failure, cite the FACTS entry contradicted.",
        },
    },
    "required": ["pass", "reasons"],
    "additionalProperties": False,
}

_PROMPT = """You are grading a supplier AR agent's answer. Be strict but fair: the
agent is graded on grounding, not phrasing.

QUESTION (asked by a user of supplier account #{supplier_id}):
{question}

AGENT ANSWER:
{answer}

FACTS (computed from the live system; authoritative — do not recompute):
{facts}

RUBRIC:
{rubric}

Grade against the RUBRIC only, checking claims against FACTS. Formatting,
tone, and extra helpful detail are not failures."""


class Judge:
    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    def grade(
        self,
        *,
        question: str,
        answer: str,
        rubric: str,
        facts: dict[str, Any],
        supplier_id: int,
    ) -> dict[str, Any]:
        prompt = _PROMPT.format(
            supplier_id=supplier_id,
            question=question,
            answer=answer or "(empty answer)",
            facts=json.dumps(facts, indent=2),
            rubric=rubric,
        )
        response = self._client.responses.create(
            model=self._model,
            input=[{"role": "user", "content": prompt}],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "verdict",
                    "schema": VERDICT_SCHEMA,
                    "strict": True,
                }
            },
        )
        return json.loads(response.output_text)
