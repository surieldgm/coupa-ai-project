"""Catalog tools: the Acting Supplier's own catalog."""

from __future__ import annotations

from typing import Any

from agent.procurement import ProcurementClient
from agent.registry import ToolSpec, function_schema


def _search_catalog(
    client: ProcurementClient,
    *,
    query: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
    in_stock: bool | None = None,
) -> Any:
    return client.search_catalog(
        query=query, category=category, max_price=max_price, in_stock=in_stock
    )


SEARCH_CATALOG = ToolSpec(
    schema=function_schema(
        "search_catalog",
        "Search the items in your catalog by keyword, category, price, or "
        "availability. All filters null returns the full catalog.",
        {
            "query": {
                "type": ["string", "null"],
                "description": "Keyword matched against item names and descriptions.",
            },
            "category": {"type": ["string", "null"], "description": "Exact category name."},
            "max_price": {"type": ["number", "null"], "description": "Maximum unit price."},
            "in_stock": {
                "type": ["boolean", "null"],
                "description": "Filter by availability. Null for all items.",
            },
        },
    ),
    fn=_search_catalog,
)

TOOLS = [SEARCH_CATALOG]
