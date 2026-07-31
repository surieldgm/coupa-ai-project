"""Session — the deep module. One verb: ask().

Behind the seam: the Responses tool loop, Tenancy, Gated Tool
interception, context pruning, trace emission, and skill loading.
Interface contract and invariants: docs/DESIGN.md.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from openai import OpenAI, OpenAIError

from agent.policy import ApprovalRequest, Decision, PermissionPolicy
from agent.pruning import estimate_chars, prune
from agent.registry import ToolRegistry, error_envelope
from agent.skills_lib import SkillLibrary, SkillNotFoundError
from agent.tracing import TraceEvent, TraceSink

_SKILLS_DIR = Path(__file__).resolve().parent / "skills"

DEFAULT_MODEL = "gpt-5.4"

LOAD_SKILL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "name": "load_skill",
    "description": (
        "Load a skill guide (or one of its bundled resource files) by name. "
        "Skills are step-by-step workflows for multi-step questions; the "
        "available skills are listed in your instructions. Follow the loaded "
        "instructions."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Skill name (e.g. 'account-health') or a resource path "
                "inside a skill (e.g. 'account-health/resources/rubric.md').",
            }
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}


@dataclass(frozen=True)
class SessionConfig:
    model: str = DEFAULT_MODEL
    max_tool_rounds: int = 10
    prune_budget_chars: int = 60_000
    skills_dir: Path = _SKILLS_DIR


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    output: str
    gated: bool
    decision: str | None  # approve / approve_for_session / remembered / deny; None if ungated


@dataclass(frozen=True)
class TurnResult:
    answer: str
    tool_calls: tuple[ToolCall, ...]
    events: tuple[TraceEvent, ...]
    usage: Usage
    stop_reason: Literal["completed", "tool_budget"]


class SessionError(Exception):
    pass


class TenancyError(SessionError):
    pass


class ModelError(SessionError):
    pass


class Session:
    def __init__(
        self,
        *,
        supplier_id: int,
        supplier_name: str,
        openai: OpenAI,
        registry: ToolRegistry,
        permissions: PermissionPolicy,
        trace: TraceSink,
        config: SessionConfig | None = None,
    ) -> None:
        if registry.supplier_id != supplier_id:
            raise TenancyError(
                f"registry is bound to supplier {registry.supplier_id}, "
                f"session to supplier {supplier_id}"
            )
        self.session_id = uuid.uuid4().hex[:12]
        self.supplier_id = supplier_id
        self.supplier_name = supplier_name
        self._openai = openai
        self._registry = registry
        self._permissions = permissions
        self._trace = trace
        self._config = config or SessionConfig()
        self._skills = SkillLibrary(self._config.skills_dir)
        self._tools_payload: list[Any] = [*registry.list_tools(), LOAD_SKILL_SCHEMA]
        self._conversation: list[Any] = [
            {"role": "developer", "content": self._system_prompt()}
        ]
        self._approved_for_session: set[str] = set()
        self._turn = 0
        self._seq = 0
        self._in_turn = False

    # -- the one verb ------------------------------------------------------

    def ask(self, user_text: str) -> TurnResult:
        if self._in_turn:
            raise SessionError("ask() is not reentrant")
        self._in_turn = True
        try:
            return self._run_turn(user_text)
        finally:
            self._in_turn = False

    # -- turn loop ---------------------------------------------------------

    def _run_turn(self, user_text: str) -> TurnResult:
        self._turn += 1
        started = time.monotonic()
        events: list[TraceEvent] = []
        tool_calls: list[ToolCall] = []
        input_tokens = output_tokens = 0

        self._conversation.append({"role": "user", "content": user_text})
        protect_from = len(self._conversation) - 1
        self._emit(events, "turn_started", {"user_text": user_text})

        stop_reason: Literal["completed", "tool_budget"] = "tool_budget"
        answer = ""
        rounds = 0
        for round_no in range(1, self._config.max_tool_rounds + 1):
            rounds = round_no
            self._conversation, elided = prune(
                self._conversation, self._config.prune_budget_chars, protect_from
            )
            if elided:
                self._emit(
                    events,
                    "prune",
                    {
                        "elided_outputs": elided,
                        "conversation_chars": estimate_chars(self._conversation),
                    },
                )

            try:
                response = self._openai.responses.create(
                    model=self._config.model,
                    input=self._conversation,
                    tools=self._tools_payload,
                )
            except OpenAIError as exc:
                raise ModelError(f"model call failed: {exc}") from exc

            usage = getattr(response, "usage", None)
            round_in = getattr(usage, "input_tokens", 0) or 0
            round_out = getattr(usage, "output_tokens", 0) or 0
            input_tokens += round_in
            output_tokens += round_out

            # Pass ALL output items back untouched (reasoning items included).
            output_items: list[Any] = list(response.output)
            self._conversation.extend(output_items)
            calls = [item for item in output_items if getattr(item, "type", "") == "function_call"]
            self._emit(
                events,
                "model_call",
                {
                    "gen_ai.request.model": self._config.model,
                    "gen_ai.usage.input_tokens": round_in,
                    "gen_ai.usage.output_tokens": round_out,
                    "round": round_no,
                    "function_calls": len(calls),
                },
            )

            if not calls:
                answer = response.output_text or ""
                stop_reason = "completed"
                break

            # Every function_call already in the conversation must get its
            # paired output, even if execution blows up: an orphaned call id
            # is an API error on the next request and would poison the Session.
            answered: set[str] = set()
            try:
                for call in calls:
                    record = self._execute_call(call, events)
                    tool_calls.append(record)
                    self._conversation.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": record.output,
                        }
                    )
                    answered.add(call.call_id)
            finally:
                for call in calls:
                    if call.call_id not in answered:
                        self._conversation.append(
                            {
                                "type": "function_call_output",
                                "call_id": call.call_id,
                                "output": error_envelope(
                                    "api_error", "the tool did not complete"
                                ),
                            }
                        )

        self._emit(
            events,
            "turn_completed",
            {
                "stop_reason": stop_reason,
                "rounds": rounds,
                "gen_ai.usage.input_tokens": input_tokens,
                "gen_ai.usage.output_tokens": output_tokens,
                "answer_chars": len(answer),
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )
        return TurnResult(
            answer=answer,
            tool_calls=tuple(tool_calls),
            events=tuple(events),
            usage=Usage(input_tokens, output_tokens),
            stop_reason=stop_reason,
        )

    # -- tool execution ----------------------------------------------------

    def _execute_call(self, call: Any, events: list[TraceEvent]) -> ToolCall:
        name: str = call.name
        started = time.monotonic()
        try:
            parsed: Any = json.loads(call.arguments) if call.arguments else {}
        except json.JSONDecodeError:
            parsed = None
        if not isinstance(parsed, dict):
            output = error_envelope("invalid_args", "arguments must be a JSON object")
            return self._finish_call(
                events, call, name, {}, "invalid_args", output, False, None, started
            )
        args: dict[str, Any] = parsed

        # Strict schemas send explicit nulls for omitted optionals; drop them
        # so tool functions see their own defaults.
        args = {k: v for k, v in args.items() if v is not None}

        if name == "load_skill":
            status, output = self._load_skill(args)
            return self._finish_call(events, call, name, args, status, output, False, None, started)

        gated = self._registry.is_gated(name)
        decision_str: str | None = None
        if gated:
            if name in self._approved_for_session:
                decision_str = "remembered"
                self._emit(
                    events,
                    "gate_decision",
                    {"gen_ai.tool.name": name, "decision": "remembered"},
                )
            else:
                request = ApprovalRequest(
                    tool=name, arguments=args, summary=self._registry.summarize(name, args)
                )
                decision = self._permissions.decide(request)
                decision_str = decision.value
                self._emit(
                    events,
                    "gate_decision",
                    {"gen_ai.tool.name": name, "decision": decision.value},
                )
                if decision is Decision.APPROVE_FOR_SESSION:
                    self._approved_for_session.add(name)
                if decision is Decision.DENY:
                    output = error_envelope(
                        "declined", "The user declined this action. Do not retry it."
                    )
                    return self._finish_call(
                        events, call, name, args, "declined", output, True, decision_str, started
                    )

        outcome = self._registry.call_tool(name, args)
        return self._finish_call(
            events, call, name, args, outcome.status, outcome.output, gated, decision_str, started
        )

    def _load_skill(self, args: dict[str, Any]) -> tuple[str, str]:
        path = str(args.get("path", ""))
        try:
            body = self._skills.load(path)
        except SkillNotFoundError as exc:
            return "invalid_args", error_envelope("invalid_args", str(exc))
        return "ok", json.dumps({"ok": True, "data": body})

    def _finish_call(
        self,
        events: list[TraceEvent],
        call: Any,
        name: str,
        args: dict[str, Any],
        status: str,
        output: str,
        gated: bool,
        decision: str | None,
        started: float,
    ) -> ToolCall:
        self._emit(
            events,
            "tool_call",
            {
                "gen_ai.tool.name": name,
                "gen_ai.tool.call.id": call.call_id,
                "arguments": args,
                "outcome": status,
                "gated": gated,
                "decision": decision,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "output_chars": len(output),
            },
        )
        return ToolCall(name=name, arguments=args, output=output, gated=gated, decision=decision)

    # -- plumbing ----------------------------------------------------------

    def _emit(self, buffer: list[TraceEvent], event_type: str, attrs: dict[str, Any]) -> None:
        self._seq += 1
        event: TraceEvent = {
            "event": event_type,
            "session_id": self.session_id,
            "supplier_id": self.supplier_id,
            "turn": self._turn,
            "seq": self._seq,
            "ts": datetime.now(UTC).isoformat(),
            **attrs,
        }
        self._trace.emit(event)
        buffer.append(dict(event))  # by value: TurnResult must not alias the sink's dicts

    def _system_prompt(self) -> str:
        menu = self._skills.menu()
        skill_lines = "\n".join(f"- {s.name}: {s.description}" for s in menu) or "- (none)"
        # Local date, to match the API's own overdue arithmetic (it uses date.today()).
        today = datetime.now(UTC).astimezone().date().isoformat()
        return f"""You are the accounts-receivable assistant for {self.supplier_name} \
(supplier account #{self.supplier_id}), a supplier to the buyer running this procurement \
system. Today is {today}.

Scope — your account only:
- You can only see and act on {self.supplier_name}'s own data: its invoices, purchase \
orders, contracts, and catalog. This is enforced by the application; no tool reaches \
other suppliers' data.
- If asked about another supplier or about suppliers in general, say plainly that you \
only have visibility into {self.supplier_name}'s account, then answer whatever part of \
the question applies to this account.
- If something can't be found, say it isn't on this account. Never speculate about \
whether it exists elsewhere.

Working with data:
- Fetch, don't assume: answer from tool results, and say so when data is missing.
- For overdue totals and aging, use get_overdue_aging rather than summing invoices \
yourself. When you do arithmetic, show the per-item numbers so the user can verify.
- Always state currencies alongside amounts.

Actions:
- Acknowledging purchase orders and creating invoices require the user's explicit \
approval; the application asks them when you call those tools. If approval is declined, \
accept it and move on — do not retry.

Skills — step-by-step guides for multi-step questions. When a request matches one, call \
load_skill with its name and follow the loaded instructions:
{skill_lines}"""
