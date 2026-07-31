"""Budget-based context pruning: a pure function over the conversation list.

Elides the *content* of old tool outputs instead of removing items, so a
`function_call` is never orphaned from its `function_call_output` (a
Responses API requirement) and reasoning items always survive intact.
Tool outputs are the safe thing to elide: they dominate the transcript's
bulk and are re-fetchable — the stub tells the model how.
"""

from __future__ import annotations

import json
from typing import Any

PRUNED_STUB = "[output pruned to save context — call the tool again if you need this data]"


def estimate_chars(conversation: list[Any]) -> int:
    total = 0
    for item in conversation:
        if isinstance(item, dict):
            total += len(json.dumps(item, default=str))
        else:
            total += len(str(item))
    return total


def prune(
    conversation: list[Any], budget_chars: int, protect_from: int
) -> tuple[list[Any], int]:
    """Return (conversation, elided_count), oldest outputs elided first.

    Items at index >= protect_from (the current turn) are never touched;
    neither is anything that isn't a function_call_output dict.
    """
    total = estimate_chars(conversation)
    if total <= budget_chars:
        return conversation, 0

    pruned = list(conversation)
    elided = 0
    for i, item in enumerate(pruned):
        if i >= protect_from:
            break
        if not (isinstance(item, dict) and item.get("type") == "function_call_output"):
            continue
        output = item.get("output", "")
        saving = len(str(output)) - len(PRUNED_STUB)
        if output == PRUNED_STUB or saving <= 0:
            continue
        pruned[i] = {**item, "output": PRUNED_STUB}
        total -= saving
        elided += 1
        if total <= budget_chars:
            break
    return pruned, elided
