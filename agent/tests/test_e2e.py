"""End-to-end tests: the whole stack, only the model scripted.

What is REAL here (everything the assignment asks us to build):
  * a live Procurement API — uvicorn on an ephemeral port, spoken to over
    real HTTP sockets, with its real routing, query params, and statuses
  * the production wiring path (`make_session`), the tenant-bound
    ProcurementClient, the ToolRegistry, and the real tool schemas
  * skills read from `agent/skills/` on disk, through `load_skill`
  * traces written to a real JSONL file by JsonlSink
  * the permission gate, pruning, and the full Responses turn loop

What is SCRIPTED: the model, and only the model. It is the one dependency
that cannot be made deterministic — there is no seed on the Responses API
(docs/RESEARCH.md) — so these tests script the tool calls and assert that
everything downstream of the model behaves correctly. Whether the model
*chooses* the right tools is the eval harness's job (`python -m evals.run`),
which is non-deterministic, costs money, and needs a key; this file is
deterministic, free, and runs in CI.

Each journey below is one a reviewer would try by hand in a demo.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, cast

import httpx
from openai import OpenAI

from agent.policy import ApprovalRequest, Decision
from agent.procurement import ProcurementError
from agent.session import Session
from agent.tests.fakes import FakeOpenAI, fn_call, message_item, scripted_response
from agent.tracing import JsonlSink
from agent.wiring import make_session

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTING_SUPPLIER = 2  # SteelWorks Manufacturing
OTHER_SUPPLIER_INVOICE = 2001  # belongs to supplier 1

_server: subprocess.Popen[bytes] | None = None
_base_url = ""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def setUpModule() -> None:
    """Start a real API server. Its data is in-memory and resets on each
    start, so every run of this module gets a pristine fixture."""
    global _server, _base_url
    port = _free_port()
    _base_url = f"http://127.0.0.1:{port}"
    _server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(port),
         "--log-level", "warning"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if _server.poll() is not None:
            raise RuntimeError("API server exited during startup")
        try:
            if httpx.get(f"{_base_url}/", timeout=1.0).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.15)
    raise RuntimeError(f"API server did not become ready at {_base_url}")


def tearDownModule() -> None:
    if _server is not None:
        _server.terminate()
        try:
            _server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _server.kill()


class ScriptedApprovals:
    """Stands in for the human at the approval prompt."""

    def __init__(self, *decisions: Decision) -> None:
        self._decisions = list(decisions)
        self.seen: list[ApprovalRequest] = []

    def decide(self, request: ApprovalRequest) -> Decision:
        self.seen.append(request)
        return self._decisions.pop(0) if self._decisions else Decision.DENY


class EndToEndTestCase(unittest.TestCase):
    """Base: builds a Session through the production composition root."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.trace_path = Path(self._tmp.name) / "session.jsonl"
        self._sessions: list[Session] = []

    def tearDown(self) -> None:
        for session in self._sessions:
            session.close()
        self._tmp.cleanup()

    def build(
        self,
        *responses: Any,
        supplier_id: int = ACTING_SUPPLIER,
        approvals: ScriptedApprovals | None = None,
    ) -> tuple[Session, FakeOpenAI]:
        fake = FakeOpenAI(list(responses))
        session = make_session(
            supplier_id,
            permissions=approvals or ScriptedApprovals(),
            trace=JsonlSink(self.trace_path),
            openai_client=cast(OpenAI, fake),
            base_url=_base_url,
        )
        self._sessions.append(session)
        return session, fake

    def api(self) -> httpx.Client:
        """A direct client for verifying server state — the test may look
        at the API unscoped; the agent may not."""
        return httpx.Client(base_url=_base_url, timeout=10.0)

    def data(self, output: str) -> Any:
        payload = json.loads(output)
        self.assertTrue(payload["ok"], payload)
        return payload["data"]

    def error(self, output: str) -> dict[str, Any]:
        payload = json.loads(output)
        self.assertFalse(payload["ok"], payload)
        return cast(dict[str, Any], payload["error"])


class ReadJourneyTest(EndToEndTestCase):
    def test_supplier_asks_about_invoices_and_gets_only_their_own(self) -> None:
        session, fake = self.build(
            scripted_response([fn_call("list_invoices", {}, "c1")]),
            scripted_response([message_item()], text="You have invoices outstanding."),
        )
        result = session.ask("show me my invoices")

        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual(result.answer, "You have invoices outstanding.")
        invoices = self.data(result.tool_calls[0].output)
        self.assertTrue(invoices, "expected seeded invoices for this supplier")
        self.assertEqual(
            {inv["supplier_id"] for inv in invoices},
            {ACTING_SUPPLIER},
            "tenancy breach: another supplier's invoice reached the model",
        )
        # The supplier's real name was resolved from the live API and put
        # in front of the model.
        self.assertIn("SteelWorks", fake.calls[0]["input"][0]["content"])

    def test_server_side_aggregates_are_reachable(self) -> None:
        session, _ = self.build(
            scripted_response([fn_call("get_invoiced_totals", {}, "c1")]),
            scripted_response([message_item()], text="Totals reported."),
        )
        result = session.ask("what have I invoiced in total?")
        totals = self.data(result.tool_calls[0].output)
        rows = totals["data"]
        self.assertEqual([row["supplier_id"] for row in rows], [ACTING_SUPPLIER])
        self.assertGreater(rows[0]["total_invoiced"], 0)


class TenancyJourneyTest(EndToEndTestCase):
    def test_another_suppliers_invoice_is_indistinguishable_from_a_missing_one(self) -> None:
        with self.api() as api:
            foreign = api.get(f"/invoices/{OTHER_SUPPLIER_INVOICE}").json()
        self.assertNotEqual(
            foreign["supplier_id"], ACTING_SUPPLIER, "fixture assumption broken"
        )

        session, _ = self.build(
            scripted_response(
                [fn_call("get_invoice", {"invoice_id": OTHER_SUPPLIER_INVOICE}, "c1")]
            ),
            scripted_response([fn_call("get_invoice", {"invoice_id": 999999}, "c2")]),
            scripted_response([message_item()], text="Not on your account."),
        )
        result = session.ask("show me invoice 2001, and also invoice 999999")

        foreign_error = self.error(result.tool_calls[0].output)
        missing_error = self.error(result.tool_calls[1].output)
        self.assertEqual(foreign_error, missing_error, "existence leaked through wording")
        self.assertNotIn(str(foreign["amount"]), result.tool_calls[0].output)

    def test_path_traversal_never_reaches_the_server(self) -> None:
        session, _ = self.build(
            scripted_response([fn_call("get_invoice", {"invoice_id": "../suppliers"}, "c1")]),
            scripted_response([message_item()], text="I can't do that."),
        )
        result = session.ask("fetch invoice ../suppliers")

        self.assertEqual(self.error(result.tool_calls[0].output)["type"], "invalid_args")
        for name in ("SteelWorks", "CleanSpace", "Acme", "@"):
            self.assertNotIn(name, result.tool_calls[0].output)

    def test_session_refuses_to_start_for_an_unknown_supplier(self) -> None:
        with self.assertRaises(ProcurementError):
            make_session(
                9999,
                openai_client=cast(OpenAI, FakeOpenAI([])),
                base_url=_base_url,
            )


class GatedMutationJourneyTest(EndToEndTestCase):
    """These tests change server state, so each one acts as a different
    supplier: the API's data is process-wide and shared across this
    module, and tests must not depend on execution order."""

    DECLINE_SUPPLIER = 2  # declines change nothing, so this account stays pristine
    APPROVE_SUPPLIER = 1  # consumes one submitted PO
    SESSION_APPROVE_SUPPLIER = 3  # consumes two

    def submitted_pos(self, supplier_id: int) -> list[int]:
        with self.api() as api:
            pos = api.get(
                "/purchase-orders", params={"supplier_id": supplier_id, "status": "submitted"}
            ).json()
        return [int(po["id"]) for po in pos]

    def claim_po(self, supplier_id: int, count: int = 1) -> list[int]:
        pos = self.submitted_pos(supplier_id)
        if len(pos) < count:
            self.skipTest(f"supplier {supplier_id} has fewer than {count} submitted POs")
        return pos[:count]

    def po_status(self, po_id: int) -> str:
        with self.api() as api:
            return str(api.get(f"/purchase-orders/{po_id}").json()["status"])

    def test_declining_leaves_the_server_untouched_and_the_turn_alive(self) -> None:
        (po_id,) = self.claim_po(self.DECLINE_SUPPLIER)
        approvals = ScriptedApprovals(Decision.DENY)
        session, _ = self.build(
            scripted_response([fn_call("acknowledge_purchase_order", {"po_id": po_id}, "c1")]),
            scripted_response([message_item()], text="Understood, leaving it as is."),
            approvals=approvals,
            supplier_id=self.DECLINE_SUPPLIER,
        )
        result = session.ask(f"acknowledge PO {po_id}")

        self.assertEqual(len(approvals.seen), 1)
        self.assertIn(str(po_id), approvals.seen[0].summary)
        self.assertEqual(self.error(result.tool_calls[0].output)["type"], "declined")
        self.assertEqual(self.po_status(po_id), "submitted", "declined action still executed")
        # A decline is conversation, not an exception: the turn finished.
        self.assertEqual(result.stop_reason, "completed")
        self.assertEqual(result.answer, "Understood, leaving it as is.")

    def test_approving_actually_transitions_the_purchase_order(self) -> None:
        (po_id,) = self.claim_po(self.APPROVE_SUPPLIER)
        self.assertEqual(self.po_status(po_id), "submitted")

        session, _ = self.build(
            scripted_response([fn_call("acknowledge_purchase_order", {"po_id": po_id}, "c1")]),
            scripted_response([message_item()], text="Acknowledged."),
            approvals=ScriptedApprovals(Decision.APPROVE),
            supplier_id=self.APPROVE_SUPPLIER,
        )
        result = session.ask(f"acknowledge PO {po_id}")

        self.assertEqual(self.data(result.tool_calls[0].output)["status"], "acknowledged")
        self.assertEqual(self.po_status(po_id), "acknowledged", "write did not persist")

    def test_approval_for_the_session_is_asked_once_and_honoured_after(self) -> None:
        first, second = self.claim_po(self.SESSION_APPROVE_SUPPLIER, count=2)

        approvals = ScriptedApprovals(Decision.APPROVE_FOR_SESSION)
        session, _ = self.build(
            scripted_response([fn_call("acknowledge_purchase_order", {"po_id": first}, "c1")]),
            scripted_response([fn_call("acknowledge_purchase_order", {"po_id": second}, "c2")]),
            scripted_response([message_item()], text="Both acknowledged."),
            approvals=approvals,
            supplier_id=self.SESSION_APPROVE_SUPPLIER,
        )
        result = session.ask(f"acknowledge POs {first} and {second}")

        self.assertEqual(len(approvals.seen), 1, "the human was asked twice")
        self.assertEqual(
            [call.decision for call in result.tool_calls],
            ["approve_for_session", "remembered"],
        )
        self.assertEqual(self.po_status(first), "acknowledged")
        self.assertEqual(self.po_status(second), "acknowledged")


class SkillJourneyTest(EndToEndTestCase):
    def test_the_menu_advertises_skills_and_bodies_load_from_disk(self) -> None:
        session, fake = self.build(
            scripted_response([fn_call("load_skill", {"path": "account-health"}, "c1")]),
            scripted_response([message_item()], text="Health summarised."),
        )
        result = session.ask("how is my account doing?")

        system_prompt = fake.calls[0]["input"][0]["content"]
        for skill in ("account-health", "follow-ups", "contract-reconciliation"):
            self.assertIn(skill, system_prompt)
        # Level 1 is metadata only: the body arrives after load_skill, and
        # its instructions never sat in the prompt beforehand.
        body = self.data(result.tool_calls[0].output)
        self.assertIn("AGING_CONCENTRATION", body)
        self.assertNotIn("AGING_CONCENTRATION", system_prompt)

    def test_a_skill_path_outside_the_skills_root_is_refused(self) -> None:
        session, _ = self.build(
            scripted_response([fn_call("load_skill", {"path": "../../.env"}, "c1")]),
            scripted_response([message_item()], text="No such skill."),
        )
        result = session.ask("load ../../.env")
        self.assertEqual(self.error(result.tool_calls[0].output)["type"], "invalid_args")


class TraceJourneyTest(EndToEndTestCase):
    def test_a_session_leaves_a_valid_correlated_jsonl_trace(self) -> None:
        po_id = 999999  # a PO this supplier does not have; the gate still runs first
        approvals = ScriptedApprovals(Decision.DENY)
        session, _ = self.build(
            scripted_response([fn_call("list_invoices", {"status": "paid"}, "c1")]),
            scripted_response([message_item()], text="Here they are."),
            scripted_response([fn_call("acknowledge_purchase_order", {"po_id": po_id}, "c2")]),
            scripted_response([message_item()], text="Not acknowledging."),
            approvals=approvals,
        )
        session.ask("show me paid invoices")
        session.ask(f"acknowledge PO {po_id}")

        lines = self.trace_path.read_text(encoding="utf-8").strip().split("\n")
        events = [json.loads(line) for line in lines]  # every line must be valid JSON

        self.assertEqual([e["event"] for e in events].count("turn_started"), 2)
        self.assertEqual([e["event"] for e in events].count("turn_completed"), 2)
        self.assertEqual({e["session_id"] for e in events}, {session.session_id})
        self.assertEqual({e["supplier_id"] for e in events}, {ACTING_SUPPLIER})
        self.assertEqual([e["seq"] for e in events], sorted(e["seq"] for e in events))
        self.assertEqual(sorted({e["turn"] for e in events}), [1, 2])

        model_call = next(e for e in events if e["event"] == "model_call")
        self.assertIn("gen_ai.request.model", model_call)
        self.assertIn("gen_ai.usage.input_tokens", model_call)

        tool_call = next(e for e in events if e["event"] == "tool_call")
        self.assertEqual(tool_call["gen_ai.tool.name"], "list_invoices")
        self.assertEqual(tool_call["gen_ai.tool.call.id"], "c1")
        self.assertEqual(tool_call["arguments"], {"status": "paid"})
        # Payload-light: sizes, not bodies.
        self.assertIn("output_chars", tool_call)
        self.assertNotIn("output", tool_call)

        gate = next(e for e in events if e["event"] == "gate_decision")
        self.assertEqual(gate["decision"], "deny")
        self.assertEqual(gate["turn"], 2)


class ConversationJourneyTest(EndToEndTestCase):
    def test_context_and_tool_results_carry_across_turns(self) -> None:
        session, fake = self.build(
            scripted_response([fn_call("get_my_account", {}, "c1")]),
            scripted_response([message_item()], text="Your terms are net 60."),
            scripted_response([message_item()], text="As I said, net 60."),
        )
        session.ask("what are my payment terms?")
        second = session.ask("and remind me again?")

        self.assertEqual(second.answer, "As I said, net 60.")
        self.assertEqual(second.tool_calls, ())

        # The third model call sees the whole history: both user turns, the
        # tool exchange, and the earlier reply.
        history = fake.calls[2]["input"]
        roles = [item.get("role") for item in history if isinstance(item, dict)]
        self.assertEqual(roles.count("user"), 2)

        # The prior assistant reply is carried back as the model's own
        # output item, not re-authored as a {"role": "assistant"} dict —
        # doing both would send the same message twice.
        self.assertEqual(roles.count("assistant"), 0)
        item_types = [getattr(item, "type", None) for item in history]
        self.assertIn("message", item_types)
        self.assertIn("function_call", item_types)

        outputs = [
            item for item in history
            if isinstance(item, dict) and item.get("type") == "function_call_output"
        ]
        self.assertEqual(len(outputs), 1)
        self.assertIn("SteelWorks", outputs[0]["output"])


if __name__ == "__main__":
    unittest.main()
