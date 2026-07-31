"""Invoice tools: list, get, and (gated) create."""

from __future__ import annotations

from datetime import date
from typing import Any

from agent.procurement import ProcurementClient, ProcurementError, ensure_choice
from agent.registry import ToolSpec, function_schema


def _list_invoices(
    client: ProcurementClient,
    *,
    status: str | None = None,
    overdue: bool | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
) -> Any:
    ensure_choice(status, ("pending", "paid", "overdue"), "status")
    return client.list_invoices(
        status=status, overdue=overdue, min_amount=min_amount, max_amount=max_amount
    )


def _get_invoice(client: ProcurementClient, *, invoice_id: int) -> Any:
    return client.get_invoice(invoice_id)


def _create_invoice(
    client: ProcurementClient,
    *,
    amount: float,
    due_date: str,
    po_id: int | None = None,
    currency: str | None = None,
) -> Any:
    if amount <= 0:
        raise ProcurementError("invalid_args", "amount must be positive")
    try:
        date.fromisoformat(due_date)
    except ValueError:
        raise ProcurementError("invalid_args", "due_date must be YYYY-MM-DD") from None
    return client.create_invoice(
        amount=amount, due_date=due_date, po_id=po_id, currency=currency or "USD"
    )


LIST_INVOICES = ToolSpec(
    schema=function_schema(
        "list_invoices",
        "List the invoices on your account, optionally filtered. Use for payment "
        "status checks, overdue reviews, or invoice history. For overdue totals "
        "and aging buckets prefer get_overdue_aging.",
        {
            "status": {
                "type": ["string", "null"],
                "description": "Filter by status: pending, paid, or overdue. Null for all.",
            },
            "overdue": {
                "type": ["boolean", "null"],
                "description": "True to return only currently overdue invoices (includes "
                "pending invoices past their due date). Null for all.",
            },
            "min_amount": {"type": ["number", "null"], "description": "Minimum amount."},
            "max_amount": {"type": ["number", "null"], "description": "Maximum amount."},
        },
    ),
    fn=_list_invoices,
)

GET_INVOICE = ToolSpec(
    schema=function_schema(
        "get_invoice",
        "Fetch a single invoice on your account by its ID.",
        {"invoice_id": {"type": "integer", "description": "Invoice ID, e.g. 2014."}},
    ),
    fn=_get_invoice,
)


def _summarize_create(args: dict[str, Any]) -> str:
    amount = args.get("amount")
    currency = args.get("currency") or "USD"
    po_id = args.get("po_id")
    tail = f" against PO {po_id}" if po_id else ", not tied to a PO"
    return f"Create invoice: {currency} {amount}, due {args.get('due_date')}{tail}"


CREATE_INVOICE = ToolSpec(
    schema=function_schema(
        "create_invoice",
        "Create a new invoice on your account. Requires the user's explicit "
        "approval before it executes. Confirm amount and due date with the user "
        "before calling.",
        {
            "amount": {"type": "number", "description": "Invoice amount, must be positive."},
            "due_date": {"type": "string", "description": "Payment due date, YYYY-MM-DD."},
            "po_id": {
                "type": ["integer", "null"],
                "description": "Purchase order this invoice bills against, or null for a "
                "non-PO invoice.",
            },
            "currency": {
                "type": ["string", "null"],
                "description": "ISO currency code; null defaults to USD.",
            },
        },
    ),
    fn=_create_invoice,
    gated=True,
    summarize=_summarize_create,
)

TOOLS = [LIST_INVOICES, GET_INVOICE, CREATE_INVOICE]
