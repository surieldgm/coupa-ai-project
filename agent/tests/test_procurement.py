"""ProcurementClient over httpx.MockTransport — the tenancy seam."""

from __future__ import annotations

import unittest

from agent.procurement import NOT_FOUND_MESSAGE, ProcurementClient, ProcurementError
from agent.tests.fakes import RequestLog, canned_api


def make_client(log: RequestLog) -> ProcurementClient:
    return ProcurementClient("http://api.test", 2, transport=canned_api(log))


class TenancyInjectionTest(unittest.TestCase):
    def test_every_endpoint_carries_the_acting_supplier(self) -> None:
        log = RequestLog()
        client = make_client(log)
        client.get_my_account()
        client.list_invoices(status="pending")
        client.get_invoice(2014)
        client.list_purchase_orders()
        client.acknowledge_purchase_order(1013)
        client.list_contracts()
        client.search_catalog(query="steel")
        client.overdue_summary()
        client.create_invoice(amount=10.0, due_date="2026-08-01")
        self.assertTrue(log.requests, "no requests recorded")
        self.assertEqual(log.supplier_ids(), ["2"] * len(log.requests))

    def test_model_supplied_none_filters_are_dropped_not_sent(self) -> None:
        log = RequestLog()
        make_client(log).list_invoices()
        params = dict(log.requests[0].url.params)
        self.assertEqual(set(params), {"supplier_id"})


class ErrorMappingTest(unittest.TestCase):
    def test_404_maps_to_existence_ambiguous_not_found(self) -> None:
        log = RequestLog()
        with self.assertRaises(ProcurementError) as ctx:
            make_client(log).get_invoice(9999)
        self.assertEqual(ctx.exception.kind, "not_found")
        self.assertEqual(ctx.exception.message, NOT_FOUND_MESSAGE)


if __name__ == "__main__":
    unittest.main()
