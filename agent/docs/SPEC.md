# Spec — Supplier AR Agent

Requirements contract for this fork's implementation. Vocabulary: [CONTEXT.md](../CONTEXT.md).
Module shapes: [DESIGN.md](DESIGN.md). Decision history: [adr/](adr/). Upstream brief: [/ASSIGNMENT.md](../../ASSIGNMENT.md).

## Mission

A conversational AR assistant a supplier uses against their own account on the buyer's
procurement system. Graded on code quality & defensibility first; depth over breadth.

## Scope

**In:** the four assignment stages, built 1 → 3 → 2 → 4 (traces before skills: they are the
debugging substrate for skills and the assertion substrate for evals).
**Out (explicit descopes):** streaming/event-generator interface (DESIGN.md, rejected);
MCP protocol integration (ADR 0002); LLM summarization for context management (tool-output
elision instead); cross-tenant "buyer-side" answering of any kind.

## Functional requirements

### FR1 — Session & tenancy (Stage 1)
1. A Session binds to exactly one Acting Supplier at construction; no interface or model
   path changes it. Construction fails on a tenant-mismatched dependency.
2. No tool schema exposes a supplier parameter; the tenant-bound client injects
   `supplier_id` into every HTTP call.
3. Out-of-tenant questions get Scope-down; missing vs foreign resources are
   indistinguishable in wording (Existence Ambiguity).
4. `ask(text) -> TurnResult{answer, tool_calls, events, usage, stop_reason}`; the loop
   passes **all** Responses output items back (`conversation += response.output`).
5. Tool surface: 8 read tools (`get_my_account`, `list_invoices`, `get_invoice`,
   `list_purchase_orders`, `get_purchase_order`, `list_contracts`, `search_catalog`,
   `get_overdue_aging`) + 2 Gated Tools (`acknowledge_purchase_order`, `create_invoice`).
   Strict schemas: `additionalProperties: false`, all properties required, optionals nullable.
6. Gated Tools: loop-level interception; approval decisions APPROVE / APPROVE_FOR_SESSION
   (remembered by the Session, per tool) / DENY; a decline returns to the model as an
   ordinary tool result. Headless default policy is deny.
7. Tool/HTTP failures never crash a turn: error envelopes (`not_found`, `api_error`,
   `invalid_args`) go back to the model. Only OpenAI transport failures raise.
8. Context management: char-budget pruning that elides only pre-turn tool-output *content*
   (never items, never the developer message, never `function_call`/output pairing).

### FR2 — Traces (Stage 3)
1. Every turn emits flat JSONL events: `turn_started`, `model_call`, `tool_call`,
   `gate_decision`, `prune`, `turn_completed`.
2. Every event carries `session_id`, `supplier_id`, `turn`, `seq`, `ts`; model/tool
   attributes use OTel GenAI names (`gen_ai.request.model`, `gen_ai.usage.input_tokens`,
   `gen_ai.usage.output_tokens`, `gen_ai.tool.name`, `gen_ai.tool.call.id`). No OTel SDK.
3. Payload-light: tool events record argument values and output *sizes*, not bodies.
4. Sink port with two adapters (JSONL file, in-memory); events also returned by value in
   `TurnResult.events`.

### FR3 — Skills (Stage 2)
1. Anthropic Agent Skills shape: `agent/skills/<name>/SKILL.md` with `name`/`description`
   frontmatter; menu (names + descriptions only) in the system prompt; bodies loaded on
   demand via a `load_skill` tool; loads confined to the skills root.
2. Catalog, priority order: `account-health` (diagnose), `follow-ups` (act),
   `contract-reconciliation` (reconcile — the flex casualty).
3. Skills own the decree rules: Monthly Contract Value = annual/12; Delivered PO
   (delivery_date set and <= today); Renewal Window (90 days, non-auto-renew ⇒ follow-up);
   no silent model arithmetic — use `get_overdue_aging` or show per-item numbers.

### FR4 — Evals (Stage 4)
1. Harness runs each `evals/questions.json` question through a real Session
   (auto-deny policy) under the supplier mapped in `evals/expectations.json`.
2. Three assertion layers: (a) trace/behavior — expected tool names + key args present,
   gate never fires on read-only questions; (b) facts — expected values computed **live**
   from the API at eval time, matched with formatting tolerance; (c) rubric judge — second
   model call with structured output (`{pass, reasons}`) grading ambiguous questions,
   fed the live-computed facts. Question #12 asserts Scope-down behavior.
3. Non-determinism: no seed exists on the Responses API. Default 1 run; `--runs N`
   (default 3 when given) reports per-question consistency with pass = majority.
4. Report of record: JSON artifact in `evals/results/` (gitignored); console prints a
   one-line summary + path.

## Non-functional requirements

- **Diff discipline:** only `agent/` and `evals/` change; runtime dirs (`agent/traces/`,
  `evals/results/`) are ignored via nested `.gitignore`s.
- **Quality gates:** `ruff check .` and `mypy agent/ --ignore-missing-imports` green at
  every commit.
- **Dependencies:** pinned `requirements.txt` only (no pytest, no PyYAML, no mcp) —
  stdlib solutions where a helper is missing.
- **Config:** `OPENAI_API_KEY`, `OPENAI_MODEL` (default gpt-5.4), `API_BASE_URL`
  (default http://localhost:8000), `SUPPLIER_ID` for the REPL.
- **Commit cadence:** one milestone per commit, repo runnable at each; final commit
  before 2026-07-31T06:44:52Z (fork + 6h).

## Acceptance

1. `uvicorn api.main:app` + `python -m agent.main --supplier 2` answers "show me my
   invoices" using only supplier 2's data; asking about another supplier produces
   Scope-down; acknowledging a PO prompts y/n/a and a decline is relayed gracefully.
2. A JSONL trace file exists per REPL session and validates as one JSON object per line.
3. `python -m evals.run` produces the JSON report with per-question, per-layer outcomes;
   read-only questions never trigger the gate.
4. ruff + mypy green; walkthrough doc (`agent/NOTES.md`) present.
