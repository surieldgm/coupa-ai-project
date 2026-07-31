"""GroundTruth — live-computed expected values (never hardcoded)."""

from __future__ import annotations

import json
import unittest
from datetime import date, timedelta
from typing import Any

import httpx

from evals.ground_truth import GroundTruth

TODAY = date(2026, 7, 31)

SUPPLIERS: list[dict[str, Any]] = [
    {"id": 1, "name": "Acme Technology Solutions", "payment_terms_days": 30},
    {"id": 2, "name": "SteelWorks Manufacturing", "payment_terms_days": 45},
]

INVOICES: list[dict[str, Any]] = [
    # paid, linked to delivered PO 1001
    {"id": 2001, "po_id": 1001, "supplier_id": 2, "amount": 100.0, "currency": "USD",
     "status": "paid", "issued_date": "2025-01-01", "due_date": "2025-02-01",
     "paid_date": "2025-01-20"},
    # pending but past due -> dynamically overdue
    {"id": 2002, "po_id": 1002, "supplier_id": 2, "amount": 200.0, "currency": "USD",
     "status": "pending", "issued_date": "2025-05-01",
     "due_date": (TODAY - timedelta(days=10)).isoformat(), "paid_date": None},
    # pending, future due -> NOT overdue
    {"id": 2003, "po_id": None, "supplier_id": 1, "amount": 300.0, "currency": "USD",
     "status": "pending", "issued_date": "2026-07-01",
     "due_date": (TODAY + timedelta(days=10)).isoformat(), "paid_date": None},
    {"id": 2004, "po_id": None, "supplier_id": 1, "amount": 55.5, "currency": "USD",
     "status": "pending", "issued_date": "2026-07-02",
     "due_date": (TODAY + timedelta(days=20)).isoformat(), "paid_date": None},
]

POS: list[dict[str, Any]] = [
    # delivered, has paid invoice -> not unbilled/unpaid
    {"id": 1001, "supplier_id": 2, "status": "acknowledged", "total_amount": 100.0,
     "currency": "USD", "created_date": "2024-12-01",
     "delivery_date": (TODAY - timedelta(days=30)).isoformat(), "line_items": []},
    # delivered, only a pending invoice -> delivered-without-paid-invoice
    {"id": 1002, "supplier_id": 2, "status": "acknowledged", "total_amount": 200.0,
     "currency": "USD", "created_date": "2025-04-01",
     "delivery_date": (TODAY - timedelta(days=5)).isoformat(), "line_items": []},
    # future delivery -> not delivered
    {"id": 1003, "supplier_id": 2, "status": "submitted", "total_amount": 300.0,
     "currency": "USD", "created_date": "2026-07-01",
     "delivery_date": (TODAY + timedelta(days=5)).isoformat(), "line_items": []},
]


def transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        params = dict(request.url.params)
        if path == "/suppliers":
            return httpx.Response(200, json=SUPPLIERS)
        if path == "/invoices":
            rows = INVOICES
            if "supplier_id" in params:
                rows = [r for r in rows if r["supplier_id"] == int(params["supplier_id"])]
            return httpx.Response(200, json=rows)
        if path == "/purchase-orders":
            rows = POS
            if "supplier_id" in params:
                rows = [r for r in rows if r["supplier_id"] == int(params["supplier_id"])]
            return httpx.Response(200, json=rows)
        if path == "/contracts":
            return httpx.Response(200, json=[])
        if path == "/analytics/overdue-summary":
            return httpx.Response(
                200,
                json={
                    "total_overdue_amount": 200.0,
                    "total_overdue_count": 1,
                    "aging_buckets": {"1-30_days": {"count": 1, "total": 200.0, "invoices": []}},
                },
            )
        if path == "/analytics/spend-by-supplier":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "supplier_id": int(params.get("supplier_id", 0)),
                            "total_invoiced": 300.0,
                            "total_paid": 100.0,
                            "total_outstanding": 200.0,
                            "invoice_count": 2,
                        }
                    ],
                    "currency": "USD",
                },
            )
        raise AssertionError(f"unexpected path {path}")

    return httpx.MockTransport(handler)


def make_gt() -> GroundTruth:
    return GroundTruth("http://api.test", transport=transport(), today=TODAY)


class GroundTruthTest(unittest.TestCase):
    def test_supplier_id_resolution_by_name(self) -> None:
        self.assertEqual(make_gt().supplier_id("SteelWorks Manufacturing"), 2)

    def test_overdue_matches_api_semantics(self) -> None:
        # status==overdue OR (pending AND due_date < today) — 2002, not 2001/2003
        self.assertEqual(make_gt().overdue_invoice_ids(2), [2002])

    def test_pending_total_sums_only_pending(self) -> None:
        self.assertAlmostEqual(make_gt().pending_total(1), 355.5)

    def test_delivered_pos_without_paid_invoice(self) -> None:
        # 1001 delivered+paid (excluded), 1002 delivered+pending-only (included),
        # 1003 future delivery (excluded)
        self.assertEqual(make_gt().delivered_pos_without_paid_invoice(2), [1002])

    def test_payment_terms(self) -> None:
        self.assertEqual(make_gt().payment_terms_days(2), 45)

    def test_other_supplier_names_for_scope_down(self) -> None:
        self.assertEqual(make_gt().other_supplier_names(2), ["Acme Technology Solutions"])

    def test_judge_context_is_json_serializable(self) -> None:
        context = make_gt().account_snapshot(2)
        json.dumps(context)  # must not raise
        self.assertIn("overdue_invoice_ids", context)

    def test_snapshot_mirrors_the_agents_own_server_figures(self) -> None:
        """A judge without these rejects correct answers as ungrounded."""
        analytics = make_gt().account_snapshot(2)["server_analytics"]
        self.assertEqual(analytics["total_outstanding"], 200.0)
        self.assertEqual(analytics["total_paid"], 100.0)
        self.assertIn("1-30_days", analytics["aging_buckets"])

    def test_snapshot_carries_per_item_rows_not_only_aggregates(self) -> None:
        snapshot = make_gt().account_snapshot(2)
        self.assertEqual({i["id"] for i in snapshot["invoices"]}, {2001, 2002})
        self.assertEqual({p["id"] for p in snapshot["purchase_orders"]}, {1001, 1002, 1003})


if __name__ == "__main__":
    unittest.main()
