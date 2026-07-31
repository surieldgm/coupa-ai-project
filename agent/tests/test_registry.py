"""ToolRegistry — the MCP-shaped seam."""

from __future__ import annotations

import json
import unittest

from agent.procurement import ProcurementClient
from agent.procurement_tools import ALL_TOOLS
from agent.registry import ToolRegistry
from agent.tests.fakes import RequestLog, canned_api


def make_registry(log: RequestLog) -> ToolRegistry:
    client = ProcurementClient("http://api.test", 2, transport=canned_api(log))
    return ToolRegistry(client, ALL_TOOLS)


class SchemaContractTest(unittest.TestCase):
    def test_no_tool_exposes_a_supplier_parameter(self) -> None:
        for schema in make_registry(RequestLog()).list_tools():
            self.assertNotIn("supplier", json.dumps(schema["parameters"]).lower())

    def test_all_schemas_are_strict(self) -> None:
        for schema in make_registry(RequestLog()).list_tools():
            self.assertTrue(schema["strict"], schema["name"])
            params = schema["parameters"]
            self.assertFalse(params["additionalProperties"])
            self.assertEqual(set(params["required"]), set(params["properties"]))

    def test_the_expected_tool_surface_is_registered(self) -> None:
        names = {s["name"] for s in make_registry(RequestLog()).list_tools()}
        self.assertEqual(
            names,
            {
                "get_my_account",
                "list_invoices",
                "get_invoice",
                "list_purchase_orders",
                "get_purchase_order",
                "list_contracts",
                "search_catalog",
                "get_overdue_aging",
                "get_invoiced_totals",
                "acknowledge_purchase_order",
                "create_invoice",
            },
        )

    def test_only_the_two_mutations_are_gated(self) -> None:
        registry = make_registry(RequestLog())
        gated = {s["name"] for s in registry.list_tools() if registry.is_gated(s["name"])}
        self.assertEqual(gated, {"acknowledge_purchase_order", "create_invoice"})


class CallToolTest(unittest.TestCase):
    def test_ok_call_returns_data_envelope(self) -> None:
        outcome = make_registry(RequestLog()).call_tool("get_invoice", {"invoice_id": 2014})
        self.assertEqual(outcome.status, "ok")
        payload = json.loads(outcome.output)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["id"], 2014)

    def test_not_found_becomes_an_envelope_not_an_exception(self) -> None:
        outcome = make_registry(RequestLog()).call_tool("get_invoice", {"invoice_id": 9999})
        self.assertEqual(outcome.status, "not_found")
        payload = json.loads(outcome.output)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["type"], "not_found")

    def test_unknown_tool_and_bad_args_become_envelopes(self) -> None:
        registry = make_registry(RequestLog())
        self.assertEqual(registry.call_tool("nope", {}).status, "unknown_tool")
        self.assertEqual(registry.call_tool("get_invoice", {}).status, "invalid_args")
        self.assertEqual(
            registry.call_tool("list_invoices", {"status": "bogus"}).status, "invalid_args"
        )


if __name__ == "__main__":
    unittest.main()
