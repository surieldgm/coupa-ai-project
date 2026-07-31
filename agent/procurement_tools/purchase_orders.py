"""Purchase order tools: list, get, and (gated) acknowledge."""

from __future__ import annotations

from typing import Any

from agent.procurement import ProcurementClient, ensure_choice
from agent.registry import ToolSpec, function_schema


def _list_purchase_orders(
    client: ProcurementClient,
    *,
    status: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    min_amount: float | None = None,
) -> Any:
    ensure_choice(status, ("submitted", "acknowledged"), "status")
    return client.list_purchase_orders(
        status=status,
        created_after=created_after,
        created_before=created_before,
        min_amount=min_amount,
    )


def _get_purchase_order(client: ProcurementClient, *, po_id: int) -> Any:
    return client.get_purchase_order(po_id)


def _acknowledge_purchase_order(client: ProcurementClient, *, po_id: int) -> Any:
    return client.acknowledge_purchase_order(po_id)


LIST_PURCHASE_ORDERS = ToolSpec(
    schema=function_schema(
        "list_purchase_orders",
        "List the purchase orders on your account, optionally filtered. A PO with "
        "status 'submitted' is awaiting your acknowledgement. delivery_date is the "
        "expected or actual delivery date.",
        {
            "status": {
                "type": ["string", "null"],
                "description": "Filter by status: submitted or acknowledged. Null for all.",
            },
            "created_after": {
                "type": ["string", "null"],
                "description": "Only POs created on/after this date (YYYY-MM-DD).",
            },
            "created_before": {
                "type": ["string", "null"],
                "description": "Only POs created on/before this date (YYYY-MM-DD).",
            },
            "min_amount": {"type": ["number", "null"], "description": "Minimum total amount."},
        },
    ),
    fn=_list_purchase_orders,
)

GET_PURCHASE_ORDER = ToolSpec(
    schema=function_schema(
        "get_purchase_order",
        "Fetch a single purchase order on your account by its ID, including line items.",
        {"po_id": {"type": "integer", "description": "Purchase order ID, e.g. 1013."}},
    ),
    fn=_get_purchase_order,
)

ACKNOWLEDGE_PURCHASE_ORDER = ToolSpec(
    schema=function_schema(
        "acknowledge_purchase_order",
        "Acknowledge a submitted purchase order on your account (status "
        "submitted -> acknowledged). Requires the user's explicit approval "
        "before it executes.",
        {"po_id": {"type": "integer", "description": "Purchase order ID to acknowledge."}},
    ),
    fn=_acknowledge_purchase_order,
    gated=True,
    summarize=lambda args: f"Acknowledge purchase order {args.get('po_id')}",
)

TOOLS = [LIST_PURCHASE_ORDERS, GET_PURCHASE_ORDER, ACKNOWLEDGE_PURCHASE_ORDER]
