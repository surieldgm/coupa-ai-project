# Module Design

Vocabulary: *module / interface / seam / adapter / depth* per the codebase-design discipline; domain terms per [../CONTEXT.md](../CONTEXT.md). Decision history in [adr/](adr/).

## Module map

```
REPL (main.py)                 eval harness (evals/)
      \                          /
       ├── make_session() ──────┤        ← composition root (wiring only)
       ▼                        ▼
   ┌─────────────────────────────────┐
   │             Session             │  ← the deep module
   │  Responses loop · tenancy ·     │
   │  gate · pruning · traces ·      │
   │  skill loading                  │
   └──┬────────┬─────────┬────────┬──┘
      │        │         │        │
 ToolRegistry  PermissionPolicy  TraceSink   (ports at the Session's seams)
      │        (Console/AutoDeny) (Jsonl/InMemory)
 ProcurementClient                          OpenAI client (injected concrete)
 (tenant-bound httpx; MockTransport in tests)
```

## Session — the deep module

**Interface (the whole thing):**

```python
Session(*, supplier_id, supplier_name, openai, registry, permissions, trace, config)
session.ask(user_text) -> TurnResult
session.session_id / session.supplier_id / session.supplier_name       # read-only

TurnResult: answer, tool_calls, events, usage, stop_reason("completed" | "tool_budget")
ToolCall:   name, arguments, output, gated, decision
```

(`supplier_name` is display identity for the system prompt, resolved by the
composition root; tenant identity remains `supplier_id` alone.)

**Invariants** (part of the interface — callers may rely on them):
1. One Session ↔ one Acting Supplier, fixed at construction; `TenancyError` if the injected registry/client is bound to a different tenant. No interface path changes it.
2. A Gated Tool never executes without approval; a decline returns to the model as an ordinary `function_call_output`, never an exception. Approval memory (per-tool, "always for this Session") is held by the Session; the PermissionPolicy port stays stateless.
3. Pruning never touches the current turn, never drops the system prompt, and never orphans a `function_call`/`function_call_output` pair.
4. Every trace event of a turn reaches the sink before `ask()` returns; `TurnResult.events` is the same data by value.
5. `ask()` is not reentrant; turns are strictly sequential.

**Error modes:** procurement/tool failures never escape — they return to the model as error-shaped outputs (preserving Existence Ambiguity). Only OpenAI failures (`ModelError`) escape. Round-cap exhaustion is `stop_reason="tool_budget"`, not an exception.

**Behind the seam:** manual Responses loop (`conversation += response.output`), tenancy injection, gate interception + approval memory, budget-based pruning (pure function), OTel-GenAI-named JSONL event emission with `session_id/turn/seq`, skill menu assembly + `load_skill` tool.

**Deletion test:** delete Session and the loop, gate, pruning, tracing, and tenancy logic reappear in both the REPL and the harness. Earns its keep twice over.

## Supporting modules

| Module | Interface | Adapters / notes |
|---|---|---|
| **ToolRegistry** | `list_tools() -> [schema]`, `call_tool(name, args) -> ToolOutcome`, `is_gated(name)`, `summarize(name, args)` | MCP-congruent seam (ADR 0002). Gating and approval summaries are registry metadata (tool modules declare them), not Session config. Tenant-bound at construction via ProcurementClient. |
| **ProcurementClient** | typed per-endpoint methods, *no supplier parameter anywhere* — tenancy injected internally | Concrete class over httpx; tests swap `httpx.MockTransport`. No Protocol wrapper: one real transport = hypothetical seam. |
| **PermissionPolicy** | `decide(ApprovalRequest) -> APPROVE / APPROVE_FOR_SESSION / DENY` | Two real adapters: `ConsoleApprovals` (REPL, blocks on input), `AutoDeny` (harness default). Stateless. |
| **TraceSink** | `emit(event) -> None` | Two real adapters: `JsonlSink(path)`, `InMemorySink`. The observation extension point. |
| **SkillLibrary** | `menu() -> [(name, description)]`, `load(relpath) -> str` | Filesystem SKILL.md scan; path-traversal guard (loads confined to skills dir). Not a port (one adapter, no seam): Session constructs it internally from `config.skills_dir` — the injected-dependency rule applies to ports, not to this. |
| **prune()** | pure: `(conversation, budget) -> conversation` | Not injectable — policy, not a port. Tested directly, no mocks. |
| **make_session()** | composition root: `make_session(supplier_id, *, permissions=AutoDeny(), trace=InMemorySink(), ...)` | The only place default adapters are constructed. Safe default = auto-deny. `Session.__init__` never builds a port adapter. |

## Test surfaces

The interface is the test surface: harness and tests assert through `ask() -> TurnResult` (+ sink contents), never past the seam. Internal seams (prune as pure fn, ProcurementClient over MockTransport) are used by their own tests only and are not exported through Session's interface. Old-style unit tests against the raw loop are superseded, not layered.

## Rejected: streaming event generator (`run() -> Iterator[TurnEvent]`)

Considered as the primary seam (design-it-twice candidate 3). Rejected for now: exactly one consumer today would stream (a live REPL nicety), and one consumer = hypothetical seam. Its costs are concrete: a drain-or-close generator contract callers can silently violate, seven event types, and a second observation channel ~70% redundant with traces. If a live UI materializes, `run()` becomes a real seam and can be added *around* the existing loop without breaking `ask()` callers. Two of its details were adopted anyway: `stop_reason` as an outcome, and construction-time tenancy verification.
