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

How to use FACTS: it is authoritative for what it states — any claim that
CONTRADICTS it fails. It is NOT an exhaustive list of everything true.
The agent has live access to the same system, so extra detail that FACTS
does not mention (dates, per-item breakdowns, statuses, phrasing) is NOT a
failure — only contradictions and rubric misses are. Do not recompute
totals yourself; compare against the FACTS values as given, and mind that
different totals mean different things (overdue_total covers overdue
invoices; pending_total_status_pending_only covers only status=pending;
server_analytics holds the same aging buckets and paid/outstanding totals
the agent's own tools return). Never fail an answer merely because a
figure is absent from FACTS — fail it when FACTS says otherwise.

The agent is instructed to compare stored status fields against dates and
to say so when they disagree (e.g. a contract marked active whose end_date
has passed, or an invoice marked pending that is past due). Pointing that
out is correct behaviour, never an unsupported claim.

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


class JudgeError(Exception):
    """The judge produced no usable verdict (refusal, truncation, bad JSON)."""


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
        status = getattr(response, "status", "completed")
        if status not in ("completed", None):
            raise JudgeError(f"judge response was {status}, not completed")
        text = response.output_text or ""
        try:
            verdict: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError as exc:
            # Refusals and truncated outputs land here: output_text is empty
            # or mid-JSON. An unparseable verdict is an error, never a pass.
            raise JudgeError(f"judge returned unparseable output: {text[:120]!r}") from exc
        return verdict
