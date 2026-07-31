"""Session.ask() -> TurnResult — the external seam.

The model side is scripted (FakeOpenAI); the API side is canned
(httpx.MockTransport). Tests assert only through the interface:
TurnResult and the trace sink.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from openai import OpenAI

from agent.policy import ApprovalRequest, Decision
from agent.procurement import ProcurementClient
from agent.procurement_tools import ALL_TOOLS
from agent.registry import ToolRegistry
from agent.session import Session, SessionConfig
from agent.tests.fakes import (
    FakeOpenAI,
    RequestLog,
    canned_api,
    fn_call,
    message_item,
    reasoning_item,
    scripted_response,
)
from agent.tracing import InMemorySink


class ScriptedPolicy:
    def __init__(self, decisions: list[Decision]) -> None:
        self._decisions = list(decisions)
        self.consulted: list[ApprovalRequest] = []

    def decide(self, request: ApprovalRequest) -> Decision:
        self.consulted.append(request)
        return self._decisions.pop(0)


def make_session(
    fake: FakeOpenAI,
    log: RequestLog,
    policy: ScriptedPolicy | None = None,
    sink: InMemorySink | None = None,
    skills_dir: Path | None = None,
    max_tool_rounds: int = 10,
) -> Session:
    client = ProcurementClient("http://api.test", 2, transport=canned_api(log))
    return Session(
        supplier_id=2,
        supplier_name="SteelWorks Manufacturing",
        openai=cast(OpenAI, fake),
        registry=ToolRegistry(client, ALL_TOOLS),
        permissions=policy or ScriptedPolicy([]),
        trace=sink or InMemorySink(),
        config=SessionConfig(
            model="test-model",
            max_tool_rounds=max_tool_rounds,
            skills_dir=skills_dir or Path(tempfile.gettempdir()) / "no-skills-here",
        ),
    )


class ToolRoundTripTest(unittest.TestCase):
    def test_tool_call_round_trip_produces_answer_and_records(self) -> None:
        fake = FakeOpenAI(
            [
                scripted_response([reasoning_item(), fn_call("list_invoices", {}, "c1")]),
                scripted_response([message_item()], text="You have 1 invoice."),
            ]
        )
        result = make_session(fake, RequestLog()).ask("show me my invoices")

        self.assertEqual(result.answer, "You have 1 invoice.")
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual([t.name for t in result.tool_calls], ["list_invoices"])
        self.assertEqual(result.usage.input_tokens, 20)

        second_input: list[Any] = fake.calls[1]["input"]
        types = [getattr(item, "type", None) or item.get("type") for item in second_input
                 if not isinstance(item, dict) or "type" in item]
        self.assertIn("reasoning", types)  # ALL output items passed back untouched
        outputs = [i for i in second_input
                   if isinstance(i, dict) and i.get("type") == "function_call_output"]
        self.assertEqual(outputs[0]["call_id"], "c1")

    def test_tool_failure_becomes_envelope_and_loop_continues(self) -> None:
        fake = FakeOpenAI(
            [
                scripted_response([fn_call("get_invoice", {"invoice_id": 9999}, "c1")]),
                scripted_response([message_item()], text="That invoice is not on your account."),
            ]
        )
        result = make_session(fake, RequestLog()).ask("invoice 9999?")
        self.assertEqual(result.stop_reason, "completed")
        payload = json.loads(result.tool_calls[0].output)
        self.assertEqual(payload["error"]["type"], "not_found")


class GateTest(unittest.TestCase):
    def test_deny_returns_decline_envelope_and_never_hits_the_api(self) -> None:
        log = RequestLog()
        policy = ScriptedPolicy([Decision.DENY])
        fake = FakeOpenAI(
            [
                scripted_response([fn_call("acknowledge_purchase_order", {"po_id": 1013}, "c1")]),
                scripted_response([message_item()], text="Understood, I won't acknowledge it."),
            ]
        )
        result = make_session(fake, log, policy=policy).ask("acknowledge PO 1013")

        self.assertEqual(result.tool_calls[0].decision, "deny")
        self.assertEqual(json.loads(result.tool_calls[0].output)["error"]["type"], "declined")
        acknowledged = [r for r in log.requests if "acknowledge" in r.url.path]
        self.assertEqual(acknowledged, [])
        self.assertEqual(result.stop_reason, "completed")

    def test_approve_for_session_is_remembered_within_the_session(self) -> None:
        log = RequestLog()
        policy = ScriptedPolicy([Decision.APPROVE_FOR_SESSION])
        fake = FakeOpenAI(
            [
                scripted_response([fn_call("acknowledge_purchase_order", {"po_id": 1013}, "c1")]),
                scripted_response([fn_call("acknowledge_purchase_order", {"po_id": 1013}, "c2")]),
                scripted_response([message_item()], text="Done twice."),
            ]
        )
        result = make_session(fake, log, policy=policy).ask("acknowledge PO 1013 twice")

        self.assertEqual(len(policy.consulted), 1)  # second call rides the remembered approval
        self.assertEqual(
            [t.decision for t in result.tool_calls], ["approve_for_session", "remembered"]
        )
        acknowledged = [r for r in log.requests if "acknowledge" in r.url.path]
        self.assertEqual(len(acknowledged), 2)


class MalformedArgumentsTest(unittest.TestCase):
    def test_non_object_arguments_do_not_crash_the_turn(self) -> None:
        for raw in ("null", "[1, 2]", '"hi"', "123", "{oops"):
            call = SimpleNamespace(
                type="function_call", name="list_invoices", arguments=raw, call_id="c1"
            )
            fake = FakeOpenAI(
                [
                    scripted_response([call]),
                    scripted_response([message_item()], text="recovered"),
                ]
            )
            result = make_session(fake, RequestLog()).ask("bad args")
            self.assertEqual(result.stop_reason, "completed", raw)
            payload = json.loads(result.tool_calls[0].output)
            self.assertEqual(payload["error"]["type"], "invalid_args", raw)

    def test_traversal_id_is_refused_as_invalid_args(self) -> None:
        log = RequestLog()
        fake = FakeOpenAI(
            [
                scripted_response([fn_call("get_invoice", {"invoice_id": "../suppliers"}, "c1")]),
                scripted_response([message_item()], text="cannot do that"),
            ]
        )
        result = make_session(fake, log).ask("invoice ../suppliers")
        payload = json.loads(result.tool_calls[0].output)
        self.assertEqual(payload["error"]["type"], "invalid_args")
        self.assertEqual([r.url.path for r in log.requests], [])


class ConversationIntegrityTest(unittest.TestCase):
    def test_every_function_call_gets_a_paired_output_even_on_failure(self) -> None:
        class ExplodingSink:
            def __init__(self) -> None:
                self.calls = 0

            def emit(self, event: dict[str, Any]) -> None:
                self.calls += 1
                if event.get("event") == "tool_call":
                    raise RuntimeError("sink exploded mid-turn")

        fake = FakeOpenAI([scripted_response([fn_call("list_invoices", {}, "c1")])])
        session = make_session(fake, RequestLog())
        session._trace = ExplodingSink()  # type: ignore[assignment]

        with self.assertRaises(RuntimeError):
            session.ask("boom")

        conversation = session._conversation
        call_ids = {
            getattr(i, "call_id", None) for i in conversation
            if getattr(i, "type", "") == "function_call"
        }
        output_ids = {
            i["call_id"] for i in conversation
            if isinstance(i, dict) and i.get("type") == "function_call_output"
        }
        self.assertEqual(call_ids, output_ids, "orphaned function_call would break the next call")


class TraceTest(unittest.TestCase):
    def test_turn_emits_correlated_otel_named_events(self) -> None:
        sink = InMemorySink()
        fake = FakeOpenAI(
            [
                scripted_response([fn_call("list_invoices", {}, "c1")]),
                scripted_response([message_item()], text="ok"),
            ]
        )
        result = make_session(fake, RequestLog(), sink=sink).ask("invoices?")

        kinds = [e["event"] for e in sink.events]
        self.assertEqual(kinds[0], "turn_started")
        self.assertEqual(kinds[-1], "turn_completed")
        self.assertIn("model_call", kinds)
        self.assertIn("tool_call", kinds)

        model_call = next(e for e in sink.events if e["event"] == "model_call")
        self.assertEqual(model_call["gen_ai.request.model"], "test-model")
        self.assertEqual(model_call["gen_ai.usage.input_tokens"], 10)

        tool_call = next(e for e in sink.events if e["event"] == "tool_call")
        self.assertEqual(tool_call["gen_ai.tool.name"], "list_invoices")
        self.assertEqual(tool_call["gen_ai.tool.call.id"], "c1")

        seqs = [e["seq"] for e in sink.events]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual({e["session_id"] for e in sink.events}, {sink.events[0]["session_id"]})
        self.assertEqual(tuple(sink.events), result.events)


class BudgetTest(unittest.TestCase):
    def test_round_cap_stops_with_tool_budget_not_an_exception(self) -> None:
        responses = [
            scripted_response([fn_call("list_invoices", {}, f"c{i}")]) for i in range(3)
        ]
        fake = FakeOpenAI(responses)
        session = make_session(fake, RequestLog(), max_tool_rounds=3)

        result = session.ask("loop forever")
        self.assertEqual(result.stop_reason, "tool_budget")
        self.assertEqual(len(result.tool_calls), 3)


class SkillLoadingTest(unittest.TestCase):
    def test_load_skill_returns_body_and_menu_is_in_system_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "account-health"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: account-health\ndescription: Diagnose AR health.\n---\nDo the steps.",
                encoding="utf-8",
            )
            fake = FakeOpenAI(
                [
                    scripted_response([fn_call("load_skill", {"path": "account-health"}, "c1")]),
                    scripted_response([message_item()], text="loaded"),
                ]
            )
            session = make_session(fake, RequestLog(), skills_dir=Path(tmp))
            result = session.ask("health check")

            system_prompt = fake.calls[0]["input"][0]["content"]
            self.assertIn("account-health: Diagnose AR health.", system_prompt)
            payload = json.loads(result.tool_calls[0].output)
            self.assertIn("Do the steps.", payload["data"])


if __name__ == "__main__":
    unittest.main()
