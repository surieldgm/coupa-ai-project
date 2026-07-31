"""Tenant-bound HTTP client for the Procurement API.

The Acting Supplier is fixed at construction and injected into every
request. No caller — and in particular no model output — can address
another tenant through this client. This is where Tenancy lives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx

ErrorKind = Literal["not_found", "api_error", "invalid_args"]

# Existence Ambiguity: the same wording whether a resource doesn't exist
# or exists on another supplier's account.
NOT_FOUND_MESSAGE = "No such resource on your account."


def ensure_choice(value: str | None, allowed: tuple[str, ...], field: str) -> None:
    """Shared filter validation: raises invalid_args for out-of-vocabulary values."""
    if value is not None and value not in allowed:
        raise ProcurementError("invalid_args", f"{field} must be one of {', '.join(allowed)}")


def resource_id(value: object, field: str) -> int:
    """Coerce a model-supplied resource id to an int before it reaches a URL path.

    Tenancy depends on this: httpx normalizes dot segments client-side, so a
    string id like "../suppliers" would escape the resource prefix and land on
    an endpoint that ignores the pinned supplier_id. Path identity must never
    depend on the model emitting the right JSON type.
    """
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ProcurementError("invalid_args", f"{field} must be an integer id")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ProcurementError("invalid_args", f"{field} must be an integer id") from None


@dataclass(frozen=True)
class ProcurementError(Exception):
    kind: ErrorKind
    message: str
    status_code: int | None = None


class ProcurementClient:
    """Typed access to the Procurement API, scoped to one Acting Supplier."""

    def __init__(
        self,
        base_url: str,
        supplier_id: int,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.supplier_id = supplier_id
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        query = {k: v for k, v in (params or {}).items() if v is not None}
        query["supplier_id"] = self.supplier_id
        try:
            response = self._http.request(method, path, params=query, json=body)
        except httpx.HTTPError as exc:
            raise ProcurementError("api_error", f"procurement API unreachable: {exc}") from exc
        if response.status_code == 404:
            raise ProcurementError("not_found", NOT_FOUND_MESSAGE, 404)
        if response.status_code >= 400:
            raise ProcurementError(
                "api_error",
                f"procurement API error (HTTP {response.status_code})",
                response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProcurementError("api_error", "procurement API returned a malformed body") from exc

    # -- account ----------------------------------------------------------

    def get_my_account(self) -> Any:
        return self._request("GET", f"/suppliers/{self.supplier_id}")

    # -- invoices ---------------------------------------------------------

    def list_invoices(
        self,
        *,
        status: str | None = None,
        overdue: bool | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
    ) -> Any:
        return self._request(
            "GET",
            "/invoices",
            params={
                "status": status,
                "overdue": overdue,
                "min_amount": min_amount,
                "max_amount": max_amount,
            },
        )

    def get_invoice(self, invoice_id: int) -> Any:
        return self._request("GET", f"/invoices/{resource_id(invoice_id, 'invoice_id')}")

    def create_invoice(
        self,
        *,
        amount: float,
        due_date: str,
        po_id: int | None = None,
        currency: str = "USD",
    ) -> Any:
        return self._request(
            "POST",
            "/invoices",
            body={
                "po_id": None if po_id is None else resource_id(po_id, "po_id"),
                "amount": amount,
                "due_date": due_date,
                "currency": currency,
            },
        )

    # -- purchase orders --------------------------------------------------

    def list_purchase_orders(
        self,
        *,
        status: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        min_amount: float | None = None,
    ) -> Any:
        return self._request(
            "GET",
            "/purchase-orders",
            params={
                "status": status,
                "created_after": created_after,
                "created_before": created_before,
                "min_amount": min_amount,
            },
        )

    def get_purchase_order(self, po_id: int) -> Any:
        return self._request("GET", f"/purchase-orders/{resource_id(po_id, 'po_id')}")

    def acknowledge_purchase_order(self, po_id: int) -> Any:
        path = f"/purchase-orders/{resource_id(po_id, 'po_id')}/acknowledge"
        return self._request("POST", path)

    # -- contracts --------------------------------------------------------

    def list_contracts(
        self,
        *,
        status: str | None = None,
        expiring_within_days: int | None = None,
    ) -> Any:
        return self._request(
            "GET",
            "/contracts",
            params={"status": status, "expiring_within_days": expiring_within_days},
        )

    # -- catalog ----------------------------------------------------------

    def search_catalog(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        max_price: float | None = None,
        in_stock: bool | None = None,
    ) -> Any:
        return self._request(
            "GET",
            "/catalog",
            params={
                "query": query,
                "category": category,
                "max_price": max_price,
                "in_stock": in_stock,
            },
        )

    # -- analytics --------------------------------------------------------

    def overdue_summary(self) -> Any:
        return self._request("GET", "/analytics/overdue-summary")
