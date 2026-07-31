"""Test doubles shared across the suite.

FakeOpenAI scripts the model side of the seam; canned_api() provides an
httpx.MockTransport that mimics the Procurement API's shapes and records
every request for tenancy assertions.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx


def fn_call(name: str, args: dict[str, Any], call_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="function_call", name=name, arguments=json.dumps(args), call_id=call_id
    )


def reasoning_item() -> SimpleNamespace:
    return SimpleNamespace(type="reasoning", id="rs_1")


def message_item() -> SimpleNamespace:
    return SimpleNamespace(type="message")


def scripted_response(
    output: list[Any], text: str = "", in_tok: int = 10, out_tok: int = 5
) -> SimpleNamespace:
    return SimpleNamespace(
        output=output,
        output_text=text,
        usage=SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
    )


class FakeOpenAI:
    """Duck-typed stand-in for the OpenAI client: returns scripted
    responses in order and records every create() call's kwargs."""

    def __init__(self, scripted: list[SimpleNamespace]) -> None:
        self._scripted = list(scripted)
        self.calls: list[dict[str, Any]] = []

    @property
    def responses(self) -> FakeOpenAI:
        return self

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if not self._scripted:
            raise AssertionError("FakeOpenAI: no scripted response left")
        return self._scripted.pop(0)


class RequestLog:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def supplier_ids(self) -> list[str | None]:
        return [dict(r.url.params).get("supplier_id") for r in self.requests]


_INVOICE = {
    "id": 2014,
    "po_id": 1013,
    "supplier_id": 2,
    "amount": 19500.0,
    "currency": "USD",
    "status": "pending",
    "issued_date": "2025-04-01",
    "due_date": "2025-06-30",
    "paid_date": None,
}

_PO = {
    "id": 1013,
    "supplier_id": 2,
    "line_items": [],
    "total_amount": 19500.0,
    "currency": "USD",
    "status": "acknowledged",
    "created_date": "2025-03-01",
    "delivery_date": "2025-04-01",
}


def canned_api(log: RequestLog) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        log.requests.append(request)
        path = request.url.path
        if path == "/invoices":
            return httpx.Response(200, json=[_INVOICE])
        if path == "/invoices/2014":
            return httpx.Response(200, json=_INVOICE)
        if path.startswith("/invoices/"):
            return httpx.Response(404, json={"detail": "not found"})
        if path == "/purchase-orders/1013/acknowledge":
            return httpx.Response(200, json=_PO)
        if path == "/suppliers/2":
            return httpx.Response(200, json={"id": 2, "name": "SteelWorks Manufacturing"})
        if path == "/analytics/overdue-summary":
            return httpx.Response(200, json={"total_overdue_amount": 0.0})
        if path == "/analytics/spend-by-supplier":
            return httpx.Response(200, json={"data": [], "currency": "USD"})
        return httpx.Response(200, json=[])

    return httpx.MockTransport(handler)
