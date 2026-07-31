"""Live ground truth for the eval harness.

Expected values are computed from the API at eval time — never hardcoded —
because the seeded data is time-dependent (a pending invoice becomes
dynamically overdue the day after its due date). The harness is a tester,
not the agent: it may query the API unscoped.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx


class GroundTruth:
    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        today: date | None = None,
    ) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=10.0, transport=transport)
        self._today = today or date.today()  # noqa: DTZ011 — must match the API's own clock
        self._suppliers: list[dict[str, Any]] | None = None

    def _get(self, path: str, **params: Any) -> Any:
        response = self._http.get(path, params=params)
        response.raise_for_status()
        return response.json()

    # -- suppliers --------------------------------------------------------

    def suppliers(self) -> list[dict[str, Any]]:
        if self._suppliers is None:
            self._suppliers = self._get("/suppliers")
        return self._suppliers

    def supplier_id(self, name: str) -> int:
        for supplier in self.suppliers():
            if supplier["name"] == name:
                return int(supplier["id"])
        raise LookupError(f"no supplier named {name!r}")

    def payment_terms_days(self, supplier_id: int) -> int:
        for supplier in self.suppliers():
            if supplier["id"] == supplier_id:
                return int(supplier["payment_terms_days"])
        raise LookupError(f"no supplier {supplier_id}")

    def other_supplier_names(self, supplier_id: int) -> list[str]:
        return [s["name"] for s in self.suppliers() if s["id"] != supplier_id]

    # -- invoices ---------------------------------------------------------

    def invoices(self, supplier_id: int) -> list[dict[str, Any]]:
        return self._get("/invoices", supplier_id=supplier_id)

    def overdue_invoice_ids(self, supplier_id: int) -> list[int]:
        """Mirrors the API's own overdue semantics: status overdue, or
        pending with a due date strictly before today."""
        ids = []
        for inv in self.invoices(supplier_id):
            due = date.fromisoformat(inv["due_date"])
            if inv["status"] == "overdue" or (inv["status"] == "pending" and due < self._today):
                ids.append(int(inv["id"]))
        return sorted(ids)

    def pending_total(self, supplier_id: int) -> float:
        return sum(
            float(inv["amount"])
            for inv in self.invoices(supplier_id)
            if inv["status"] == "pending"
        )

    def invoiced_total(self, supplier_id: int) -> float:
        return sum(float(inv["amount"]) for inv in self.invoices(supplier_id))

    # -- purchase orders --------------------------------------------------

    def purchase_orders(self, supplier_id: int) -> list[dict[str, Any]]:
        return self._get("/purchase-orders", supplier_id=supplier_id)

    def delivered_pos_without_paid_invoice(self, supplier_id: int) -> list[int]:
        """Delivered PO decree: delivery_date set and <= today. 'Paid' means
        an invoice with that po_id has status paid."""
        paid_po_ids = {
            inv["po_id"]
            for inv in self.invoices(supplier_id)
            if inv["status"] == "paid" and inv["po_id"] is not None
        }
        ids = []
        for po in self.purchase_orders(supplier_id):
            delivery = po.get("delivery_date")
            if delivery is None or date.fromisoformat(delivery) > self._today:
                continue
            if po["id"] not in paid_po_ids:
                ids.append(int(po["id"]))
        return sorted(ids)

    # -- contracts --------------------------------------------------------

    def contracts(self, supplier_id: int) -> list[dict[str, Any]]:
        return self._get("/contracts", supplier_id=supplier_id)

    def catalog(self, supplier_id: int) -> list[dict[str, Any]]:
        return self._get("/catalog", supplier_id=supplier_id)

    # -- judge context ----------------------------------------------------

    def account_snapshot(self, supplier_id: int) -> dict[str, Any]:
        """Everything a rubric judge needs, precomputed — the judge never
        does its own arithmetic."""
        contracts = self.contracts(supplier_id)
        return {
            "supplier_id": supplier_id,
            "as_of": self._today.isoformat(),
            "payment_terms_days": self.payment_terms_days(supplier_id),
            "overdue_invoice_ids": self.overdue_invoice_ids(supplier_id),
            "pending_total": round(self.pending_total(supplier_id), 2),
            "invoiced_total": round(self.invoiced_total(supplier_id), 2),
            "delivered_pos_without_paid_invoice": self.delivered_pos_without_paid_invoice(
                supplier_id
            ),
            "submitted_po_ids": sorted(
                po["id"] for po in self.purchase_orders(supplier_id)
                if po["status"] == "submitted"
            ),
            "contracts": [
                {
                    "id": c["id"],
                    "title": c.get("title"),
                    "status": c["status"],
                    "end_date": c["end_date"],
                    "annual_value": c["annual_value"],
                    "monthly_contract_value": round(float(c["annual_value"]) / 12, 2),
                    "auto_renew": c.get("auto_renew"),
                }
                for c in contracts
            ],
        }
