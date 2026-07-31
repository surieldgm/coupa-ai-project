"""Permission port: who approves a Gated Tool, and how.

Adapters are stateless; per-tool "always for this session" memory is held
by the Session, so a policy is only consulted when no remembered approval
exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class Decision(Enum):
    APPROVE = "approve"
    APPROVE_FOR_SESSION = "approve_for_session"
    DENY = "deny"


@dataclass(frozen=True)
class ApprovalRequest:
    tool: str
    arguments: dict[str, Any]
    summary: str


class PermissionPolicy(Protocol):
    def decide(self, request: ApprovalRequest) -> Decision: ...


class AutoDeny:
    """Headless default: no side effect ever executes silently."""

    def decide(self, request: ApprovalRequest) -> Decision:
        return Decision.DENY


class ConsoleApprovals:
    """Interactive adapter: blocks on stdin mid-turn."""

    def decide(self, request: ApprovalRequest) -> Decision:
        print(f"\n  ! {request.summary}")
        while True:
            try:
                answer = input("  approve? [y]es / [n]o / [a]lways this session: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                # Fail closed: an interrupted prompt is not an approval.
                print("\n  (interrupted — treating as declined)")
                return Decision.DENY
            if answer in ("y", "yes"):
                return Decision.APPROVE
            if answer in ("n", "no"):
                return Decision.DENY
            if answer in ("a", "always"):
                return Decision.APPROVE_FOR_SESSION
