"""Composition root: the only place default adapters are constructed.

Session and its ports stay fully injected; callers that want the default
wiring (REPL, eval harness) come through make_session().
"""

from __future__ import annotations

import os

from openai import DefaultHttpxClient, OpenAI

from agent.policy import AutoDeny, PermissionPolicy
from agent.procurement import ProcurementClient
from agent.procurement_tools import ALL_TOOLS
from agent.registry import ToolRegistry
from agent.session import DEFAULT_MODEL, Session, SessionConfig
from agent.tracing import InMemorySink, TraceSink


def make_session(
    supplier_id: int,
    *,
    permissions: PermissionPolicy | None = None,
    trace: TraceSink | None = None,
    openai_client: OpenAI | None = None,
    base_url: str | None = None,
    config: SessionConfig | None = None,
) -> Session:
    base_url = base_url or os.getenv("API_BASE_URL") or "http://localhost:8000"
    client = ProcurementClient(base_url, supplier_id)
    try:
        # Fail fast if the API is down or the supplier is unknown — and do
        # not leak the connection pool when it does.
        account = client.get_my_account()
    except BaseException:
        client.close()
        raise

    if openai_client is None:
        http_client = DefaultHttpxClient(verify=False) if os.getenv("DISABLE_SSL_VERIFY") else None
        openai_client = OpenAI(http_client=http_client)

    return Session(
        supplier_id=supplier_id,
        supplier_name=str(account["name"]),
        openai=openai_client,
        registry=ToolRegistry(client, ALL_TOOLS),
        permissions=permissions or AutoDeny(),  # safe default: headless runs deny side effects
        trace=trace or InMemorySink(),
        config=config or SessionConfig(model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL)),
    )
