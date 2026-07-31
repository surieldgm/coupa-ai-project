"""Account tool: the Acting Supplier's own record."""

from __future__ import annotations

from typing import Any

from agent.procurement import ProcurementClient
from agent.registry import ToolSpec, function_schema


def _get_my_account(client: ProcurementClient) -> Any:
    return client.get_my_account()


GET_MY_ACCOUNT = ToolSpec(
    schema=function_schema(
        "get_my_account",
        "Your supplier account record: company name, category, rating, status, "
        "location, onboarding date, and standard payment terms in days. Use for "
        "questions about your own profile or payment terms.",
        {},
    ),
    fn=_get_my_account,
)

TOOLS = [GET_MY_ACCOUNT]
