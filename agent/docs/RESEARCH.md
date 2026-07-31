# RESEARCH.md — Primary-source findings for the Supplier AR Agent build

> **Diff hygiene warning:** the assignment says "Your diff should only touch `agent/` and `evals/`"
> ([ASSIGNMENT.md:60](../ASSIGNMENT.md)). This file lives in `docs/`, so it **adds to the fork's diff**.
> Before submission, either move it under `agent/` or `evals/`, add it to `.gitignore`, or delete it.

Researched 2026-07-30. Every claim cites a primary source (URL or `file:line` in this repo).
Anything not verifiable against a primary source is marked **UNVERIFIED**.

---

## TL;DR

1. **The scaffold's tool schema shape is correct.** Responses API function tools are **flat**
   (`{"type": "function", "name", "description", "parameters", "strict"}`), not Chat Completions'
   nested `{"type": "function", "function": {...}}`. Confirmed in the docs and in SDK 1.82.0's
   `FunctionToolParam` type. `strict` "Default `true`" per the SDK docstring — the scaffold's
   schema omits it and is **not strict-compliant** (has a property not listed in `required`, no
   `additionalProperties: false`).
2. **`gpt-5.4` is a real model id** (snapshot `gpt-5.4-2026-03-05`, ~1.05M context, Responses +
   function calling + structured outputs supported). The scaffold default is valid. Current
   frontier is `gpt-5.6` (alias of `gpt-5.6-sol`). Model ids are plain strings server-validated,
   so the old SDK pin does not block new models.
3. **SDK pin `openai==1.82.0` is from 2025-05-22.** It has `previous_response_id`,
   `instructions`, `temperature`/`top_p`, `text` (structured outputs), `tools`/`tool_choice`,
   `parallel_tool_calls`, `store`, `truncation`, `reasoning`, `include`
   (`reasoning.encrypted_content`), plus `.parse()` and `.stream()` helpers. It has **no
   `conversation` param** (Conversations API postdates it) and **no `seed` param** (Responses
   has never had one). `requirements.txt` is outside `agent/`+`evals/`, so the pin effectively
   cannot be changed.
4. **The scaffold's agent loop drops output items it must keep.** Docs: "ensure all items
   between the last user message and your function call output are passed into the next response
   untouched" — `agent/main.py` re-appends only `function_call` items, silently discarding
   reasoning items, and stores the final turn as plain text instead of the response's output
   items. With a reasoning-family model (gpt-5.x) this is against documented guidance.
5. **Tenancy is entirely the agent's job.** Every API list/get endpoint takes an **optional**
   `supplier_id`; `filter_by_supplier` returns **everything** when it's `None`, and
   `POST /purchase-orders/{id}/acknowledge` acts on any PO when `supplier_id` is omitted. The
   agent layer must pin `supplier_id` in Python (tool implementation), never let the model
   choose it.
6. **Skills (Anthropic spec):** a skill = directory with `SKILL.md` (YAML frontmatter `name` ≤64
   chars lowercase/digits/hyphens, `description` ≤1024 chars stating what + when) + optional
   bundled files; three-level progressive disclosure (metadata always in system prompt ≈100
   tokens → SKILL.md body on trigger <5k tokens → resources on demand). Reproducing this on
   OpenAI = metadata listing in the system prompt + a `load_skill`-style tool (adaptation, not
   spec — the spec's loading mechanism is filesystem + bash in Claude's VM).
7. **Traces:** OpenTelemetry GenAI semconv (status: **Development**) is a ready-made schema:
   span `{gen_ai.operation.name} {gen_ai.request.model}` (e.g. `chat gpt-5.4`),
   `execute_tool {tool.name}`, `invoke_agent {agent.name}`; attributes
   `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.id`,
   `gen_ai.usage.input_tokens`/`output_tokens`, `gen_ai.tool.name`/`gen_ai.tool.call.id`,
   `gen_ai.conversation.id`, `error.type`. You can emit these attribute names in plain JSON
   lines without importing any framework.
8. **Evals:** no seed on Responses ⇒ determinism cannot be forced. OpenAI's grader taxonomy:
   `string_check`, `text_similarity`, `score_model`, `label_model`, `python`, `multi`.
   Anthropic: automate grading, prefer volume over hand-grading, use a *different* model as
   judge. Practical harness: exact/code assertions on tool calls + LLM-judge (via
   `text.format` json_schema or `.parse()`) on final answers, N runs per question for
   flaky-tolerance.

---

## 1. OpenAI Responses API (as of SDK 1.82.0 and current docs)

Note on URLs: `platform.openai.com/docs/...` now 301-redirects to
`developers.openai.com/api/docs/...`; `docs.claude.com` 302s to `platform.claude.com`. Citations
below use the final URLs.

### 1.1 Function tool schema — flat, not nested

The Responses function tool is flat:

```json
{
  "type": "function",
  "name": "get_weather",
  "description": "Retrieves current weather for the given location.",
  "parameters": { "type": "object", "properties": { ... }, "required": [...], "additionalProperties": false },
  "strict": true
}
```

— [Function calling guide](https://developers.openai.com/api/docs/guides/function-calling).
Confirmed in SDK 1.82.0: `FunctionToolParam` is a TypedDict with top-level `name`, `parameters`,
`strict`, `type: Literal["function"]`, `description`
([function_tool_param.py @ v1.82.0](https://github.com/openai/openai-python/blob/v1.82.0/src/openai/types/responses/function_tool_param.py)).
The scaffold's `GET_INVOICES_SCHEMA` uses this flat shape correctly
([agent/procurement_tools/invoices.py:15-29](../agent/procurement_tools/invoices.py)).

`strict` docstring in 1.82.0: "Whether to enforce strict parameter validation. Default `true`."
(same file). Strict-mode requirements per the
[function calling guide](https://developers.openai.com/api/docs/guides/function-calling):
`additionalProperties: false` on every object, **all** properties listed in `required`, optional
fields expressed as `"type": ["string", "null"]`. The scaffold schema meets none of these
(`print_string` defined but `required: []`, no `additionalProperties`) — set `strict: true`
explicitly and write compliant schemas.

### 1.2 Tool-call round trip: `function_call` → `function_call_output` via `call_id`

The model emits output items `{"type": "function_call", "call_id", "name", "arguments"(JSON string)}`;
you execute and append `{"type": "function_call_output", "call_id": <same id>, "output": <string>}`
to the input. The `call_id` links results "to specific function invocations."
— [Function calling guide](https://developers.openai.com/api/docs/guides/function-calling).
The scaffold does exactly this ([agent/main.py:43-50](../agent/main.py)) — the shape is sanctioned.
**But** see §5.2: it appends *only* the `function_call` items, not all output items.

### 1.3 Conversation state: three options

Per the [conversation state guide](https://developers.openai.com/api/docs/guides/conversation-state):

| Option | Mechanism | Trade-off | In SDK 1.82.0? |
|---|---|---|---|
| Manual `input` list | Append alternating messages + all output items yourself | Full control; you own truncation/summarization (the assignment's "manage the context window" criterion) | **Yes** (the scaffold's approach) |
| `previous_response_id` | Chain response ids; server replays history | Simple, but "All previous input tokens for responses in the chain are billed as input tokens in the API"; requires `store: true` (30-day retention) | **Yes** ([response_create_params.py @ v1.82.0](https://github.com/openai/openai-python/blob/v1.82.0/src/openai/types/responses/response_create_params.py): "The unique ID of the previous response to the model. Use this to create multi-turn conversations.") |
| Conversations API (`conversation` param) | Durable server-side conversation object, "not subject to the 30 day TTL" | Most convenient, least control | **No** — `conversation` is absent from `ResponseCreateParams` in 1.82.0 (verified against the tag source); present in the current [API reference](https://developers.openai.com/api/docs/api-reference/responses/create) ("Items from this conversation are prepended to `input_items`"). Would need `extra_body` to use. |

For manual management with reasoning models, the guide says you must "preserve every item in the
response's `output` array" across turns.

For stateless operation (`store: false`), request `include: ["reasoning.encrypted_content"]` —
the 1.82.0 docstring: "Includes an encrypted version of reasoning tokens in reasoning item
outputs. This enables reasoning items to be used in multi-turn conversations when using the
Responses API statelessly" (response_create_params.py @ v1.82.0, `include`).

`truncation` (1.82.0 docstring): `"auto"` drops "input items in the middle of the conversation"
when over the context window; `"disabled"` (default) fails with a 400. A cheap safety net, but
not a substitute for deliberate context management.

### 1.4 Other request params (all verified present in 1.82.0 typed params)

Source: [response_create_params.py @ v1.82.0](https://github.com/openai/openai-python/blob/v1.82.0/src/openai/types/responses/response_create_params.py).

- **`instructions`**: "Inserts a system (or developer) message as the first item in the model's
  context." Not carried over when chaining with `previous_response_id` (docstring). Equivalent
  alternative: a `role: "developer"` message in `input` — valid roles are "`user`, `assistant`,
  `system`, or `developer`" ([API reference](https://developers.openai.com/api/docs/api-reference/responses/create)).
  The scaffold's `role: "developer"` first message ([agent/main.py:23](../agent/main.py)) is
  legitimate; `instructions` is the more idiomatic Responses spelling and pairs better with
  `previous_response_id` swapping.
- **`tool_choice`**: `"auto"` (default) | `"required"` | `{"type": "function", "name": ...}`;
  the guide also documents an `allowed_tools` restriction mode
  ([function calling guide](https://developers.openai.com/api/docs/guides/function-calling)).
- **`parallel_tool_calls`**: "The model may choose to call multiple functions in a single turn.
  You can prevent this by setting `parallel_tool_calls` to `false`" (same guide). The scaffold's
  loop already iterates all `function_call` items per response, so parallel calls are handled.
- **`max_output_tokens`**: "An upper bound for the number of tokens that can be generated for a
  response, including visible output tokens and reasoning tokens" (1.82.0 docstring).
- **`temperature` / `top_p`**: both present in 1.82.0 (0–2 sampling docstring). **No `seed`
  parameter exists** — not in 1.82.0 typed params, not in the current
  [API reference](https://developers.openai.com/api/docs/api-reference/responses/create)
  (Chat Completions' `seed` was never ported). ⇒ determinism cannot be requested from the API.
  **UNVERIFIED:** whether `gpt-5.4` *accepts* `temperature` — the
  [gpt-5.4 model page](https://developers.openai.com/api/docs/models/gpt-5.4) lists supported
  features (streaming, structured_outputs, function_calling, prompt_caching, reasoning-token
  support, `reasoning.effort: none|low|medium|high|xhigh`) but never mentions temperature, and
  neither the [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) nor the
  [GPT-5 params cookbook](https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_new_params_and_tools)
  documents sampling params for the family. Treat temperature as unavailable on gpt-5.x and use
  `reasoning: {"effort": ...}` instead; don't build the eval harness on temperature=0.
- **`reasoning`**: in 1.82.0 the type carries `effort: low|medium|high` and `summary`
  ([shared_params/reasoning.py @ v1.82.0](https://github.com/openai/openai-python/blob/v1.82.0/src/openai/types/shared_params/reasoning.py)).
  Newer efforts (`none`, `xhigh` — see the
  [gpt-5.4 page](https://developers.openai.com/api/docs/models/gpt-5.4)) postdate the pin, but
  TypedDict `Literal`s are **not runtime-enforced**, so passing `{"effort": "none"}` through the
  1.82.0 SDK still reaches the server. **UNVERIFIED:** server acceptance of `"none"` for
  gpt-5.4 specifically — smoke-test before relying on it.
- Also present in 1.82.0: `store`, `metadata` (16 k/v pairs, useful for tagging eval runs),
  `background`, `service_tier`, `user`, `stream`. Newer params (`conversation`,
  `text.verbosity`, `prompt_cache_key`, `safety_identifier`,
  [`prompt_cache_options` / `reasoning.context` on GPT-5.6](https://developers.openai.com/api/docs/guides/latest-model))
  are absent from the pinned SDK; the Stainless-generated methods accept `extra_body` to send
  unknown params if ever needed ([responses.py @ v1.82.0](https://github.com/openai/openai-python/blob/v1.82.0/src/openai/resources/responses/responses.py)).

### 1.5 Structured outputs (Stage 4 grader)

Responses spells structured outputs as `text: {"format": {"type": "json_schema", "name": ...,
"schema": ..., "strict": true}}` — *not* Chat Completions' `response_format`
([structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)).
Schema restrictions: `"additionalProperties: false` must always be set in objects", all fields
required, object root (no top-level `anyOf`); limits 5000 properties / 10 nesting levels /
120k chars of strings (same page). The `text` param and `ResponseTextConfigParam` exist in
1.82.0, and the SDK also ships a typed helper — `client.responses.parse(...,
text_format=PydanticModel)` — at that version
([responses.py @ v1.82.0](https://github.com/openai/openai-python/blob/v1.82.0/src/openai/resources/responses/responses.py),
`def parse` / `TextFormatT`). Ideal for forcing the LLM-judge to return
`{"pass": bool, "reasoning": str}`.

### 1.6 Model ids

- **`gpt-5.4` is valid**: dedicated model page, snapshot `gpt-5.4-2026-03-05`, "1,050,000
  context window", Responses endpoint "Supported", `function_calling` and `structured_outputs`
  supported ([gpt-5.4 model page](https://developers.openai.com/api/docs/models/gpt-5.4)). The
  scaffold default `os.getenv("OPENAI_MODEL", "gpt-5.4")`
  ([agent/main.py:14](../agent/main.py)) is therefore a real id.
- Current frontier per the [models index](https://developers.openai.com/api/docs/models):
  `gpt-5.6` (alias of `gpt-5.6-sol`), plus `gpt-5.6-terra` and `gpt-5.6-luna` variants.
- The SDK pin does **not** constrain model choice: `model` is `Required[ResponsesModel]`, a
  string union accepting arbitrary ids passed through to the server
  (response_create_params.py @ v1.82.0). SDK 1.82.0 (released 2025-05-22,
  [release notes](https://github.com/openai/openai-python/releases/tag/v1.82.0)) predates the
  entire gpt-5 family yet calls it fine.
- Safe fallbacks if `gpt-5.4` is unavailable to a given key: `gpt-5.6` (current page), and the
  structured-outputs guide's floor "GPT-4o. For new projects, start with gpt-5.6"
  ([structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)).
  **UNVERIFIED:** availability of any specific id to this account/key — test with the real key.

---

## 2. Anthropic Agent Skills — spec, and honoring it on OpenAI

Assignment requirement: skills "the model discovers and loads on demand," per Anthropic's
standard ([ASSIGNMENT.md:33](../ASSIGNMENT.md), linking
docs.claude.com → [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)).

### 2.1 The spec (all from the [overview page](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview))

- A skill is a **directory** containing a required **`SKILL.md`** with YAML frontmatter, plus
  optional bundled files:

  ```text
  pdf-processing/
  ├── SKILL.md          (frontmatter + main instructions)
  ├── FORMS.md          (specialized guide)
  ├── REFERENCE.md
  └── scripts/fill_form.py
  ```

- **Frontmatter fields** — required: `name`, `description`.
  - `name`: max 64 chars; "only lowercase letters, numbers, and hyphens"; no XML tags; no
    reserved words "anthropic"/"claude".
  - `description`: non-empty, max 1024 chars, no XML tags; "must include both what the Skill
    does and when Claude should use it" — it is the trigger signal.
- **Progressive disclosure — three levels** (table quoted from the overview):

  | Level | When loaded | Token cost | Content |
  |---|---|---|---|
  | 1: Metadata | Always (at startup) | ~100 tokens per skill | `name` + `description` from frontmatter, injected into the system prompt |
  | 2: Instructions | When skill is triggered | Under 5k tokens | SKILL.md body |
  | 3+: Resources | As needed | None until accessed | Bundled files; scripts run via bash, "only their output enters context" |

- **Discovery/loading mechanics (spec):** "Claude loads this metadata at startup and includes
  it in the system prompt"; when a request matches a description, "Claude reads SKILL.md from
  the filesystem using bash," then reads referenced files or runs scripts on demand. I.e. the
  spec's runtime is a filesystem + bash agent; there is no dedicated "load skill" API call in
  the standard itself.

### 2.2 Honoring the standard in an OpenAI-based agent (spec vs adaptation)

- **Spec-conformant parts you can keep verbatim:** on-disk layout (`SKILL.md` + resources),
  frontmatter fields and their constraints, the three-level loading discipline, and
  description-driven triggering.
- **Necessary adaptation (not spec):** this agent has no general bash/filesystem tool, so the
  mechanical equivalents are: (a) at startup, parse frontmatter of every skill dir under
  `agent/skills/` and inject only `name: description` lines into the system prompt (= Level 1);
  (b) expose a `load_skill(name)` function tool that returns the SKILL.md body (= Level 2,
  model-triggered — this preserves "the model discovers and loads on demand"); (c) optionally a
  `read_skill_resource(name, path)` tool for Level 3. What stays deterministic in code vs
  model-driven (e.g. a skill whose steps are executed by a Python function vs. instructions the
  model follows with existing tools) is exactly the architectural discussion the assignment
  flags ([ASSIGNMENT.md:35](../ASSIGNMENT.md)).
- Anthropic's engineering post on the architecture is linked from the overview
  ([Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills))
  — background, not spec.

---

## 3. Structured tracing — OpenTelemetry GenAI semantic conventions (Stage 3)

The conventions moved out of the main semconv repo to
[open-telemetry/semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai)
(the old opentelemetry.io page now says "GenAI semantic conventions have moved").
**Status: Development** (incubating — attribute names may still change), stated at the top of
[gen-ai-spans.md](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md).
Using its *vocabulary* in hand-rolled JSONL traces costs zero dependencies and gives the trace a
defensible, industry-aligned schema:

- **Inference span** ([gen-ai-spans.md](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md)):
  span name "SHOULD be `{gen_ai.operation.name} {gen_ai.request.model}`" (e.g. `chat gpt-5.4`).
  Required: `gen_ai.operation.name` (`chat`, ...), `gen_ai.provider.name` (`openai`).
  Conditionally required: `error.type`, `gen_ai.conversation.id`, `gen_ai.request.model`.
  Recommended: `gen_ai.request.temperature`, `gen_ai.request.max_tokens`,
  `gen_ai.response.id`, `gen_ai.response.model`, `gen_ai.response.finish_reasons`,
  `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`,
  `gen_ai.usage.reasoning.output_tokens`, cache token counters.
- **Execute-tool span** (same doc): `gen_ai.operation.name` = `execute_tool`; span name
  "`execute_tool {gen_ai.tool.name}`"; kind INTERNAL. Attributes: `gen_ai.tool.name`
  (required), `gen_ai.tool.call.id`, `gen_ai.tool.description`, `gen_ai.tool.type`
  (`function`), and opt-in `gen_ai.tool.call.arguments` / `gen_ai.tool.call.result` (opt-in
  because payloads may contain sensitive data — relevant to the tenancy criterion).
- **Agent spans** ([gen-ai-agent-spans.md](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md)):
  `invoke_agent` operation, span name "`invoke_agent {gen_ai.agent.name}`" — a natural
  per-user-turn root span, with `chat` and `execute_tool` spans as children.
- The repo also defines [events](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-events.md)
  and [metrics](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md)
  if turn-level records fit better than spans.

Practical shape: one JSONL file per session; one record per span with
`trace_id`/`span_id`/`parent_span_id`, `start`/`end`, the attributes above. Parseable (Stage 3
requirement, [ASSIGNMENT.md:39](../ASSIGNMENT.md)) and framework-free.

---

## 4. Eval design for a non-deterministic agent (Stage 4)

- **No determinism knob exists.** Responses API has no `seed` (§1.4); temperature on gpt-5.x is
  doubtful (§1.4). Plan for run-to-run variance instead of trying to eliminate it.
- **OpenAI grader taxonomy** ([Graders API reference](https://developers.openai.com/api/docs/api-reference/graders)):
  - `string_check` — "performs a string comparison between input and reference"; ops `eq`,
    `ne`, `like`, `ilike`.
  - `text_similarity` — metrics `cosine`, `fuzzy_match`, `bleu`, `gleu`, `meteor`,
    `rouge_1`…`rouge_l`.
  - `score_model` — "uses a model to assign a score" (LLM-as-judge, scored).
  - `label_model` — model assigns labels (LLM-as-judge, classification).
  - `python` — arbitrary python grading script.
  - `multi` — "combines the output of multiple graders to produce a single score."
  The [evals guide](https://developers.openai.com/api/docs/guides/evals) frames this as
  behavior-driven: "begin by specifying how the system should behave before implementing and
  testing the system," with graders templated over `{{ sample.output_text }}` vs
  `{{ item.correct_label }}`.
- **Anthropic's eval guidance** ([Create strong empirical evaluations](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests)):
  "Design evals that mirror your real-world task distribution"; "Structure questions to allow
  for automated grading (for example, multiple-choice, string match, code-graded, LLM-graded)";
  "More questions with slightly lower signal automated grading is better than fewer questions
  with high-quality human hand-graded evals"; for LLM grading it is "generally best practice to
  use a different model to evaluate than the model used to generate the evaluated output," with
  rubrics that pin scale endpoints and force bare-score outputs.
- **Application to `evals/questions.json`** ([evals/questions.json:1-62](../evals/questions.json)):
  12 questions in 4 categories. Sensible mapping:
  - `simple_lookup` / `filtering_aggregation`: assert on **tool-call sequence/arguments**
    (deterministic, from the Stage 3 trace) + code assertions on facts in the final answer
    (ids, amounts computed independently against the API — the mock data is static per run,
    [api/data.py](../api/data.py)).
  - `multi_step_reasoning` / `ambiguous`: LLM-as-judge with a per-question rubric, judge output
    constrained via `text.format` json_schema or `responses.parse()` (§1.5) to
    `{"pass": bool, ...}`; different model for the judge than the agent.
  - Non-determinism: run each question N times and report pass-rate (or best-of/majority);
    keep judge prompts binary/rubric-anchored per the Anthropic guidance above.

---

## 5. Cross-checks against the local repo

### 5.1 Pins (`requirements.txt`)

[requirements.txt:1-8](../requirements.txt): `fastapi==0.115.6`, `uvicorn==0.34.0`,
`pydantic==2.10.3`, `httpx==0.28.1`, `python-dotenv==1.0.1`, `openai==1.82.0`, `ruff>=0.8.0`,
`mypy>=1.13.0`.

- `openai` v1.82.0 released **2025-05-22**; that release itself added "new streaming helpers
  for background responses" ([release notes](https://github.com/openai/openai-python/releases/tag/v1.82.0))
  — the Responses API (launched March 2025) was already well established in it. Feature
  inventory at that version: see §1.3–§1.5. The current SDK line is 2.x, but
  `requirements.txt` sits at repo root, outside the allowed `agent/`+`evals/` diff
  ([ASSIGNMENT.md:60](../ASSIGNMENT.md)) — **build against 1.82.0, do not upgrade.**
- `DefaultHttpxClient` used in [agent/main.py:6,12](../agent/main.py) exists in 1.82.0 (imported
  from the package root in that tag's codebase).

### 5.2 `agent/main.py` vs documented patterns

- **Sanctioned:** flat tool schemas (§1.1); appending raw `function_call` items and
  `{"type": "function_call_output", "call_id", "output"}` dicts to a manually grown `input`
  list ([agent/main.py:47-50](../agent/main.py)) matches the
  [function calling guide](https://developers.openai.com/api/docs/guides/function-calling);
  `role: "developer"` is a valid input role (§1.4).
- **Wrong for reasoning models (gpt-5.x):** the loop appends *only* `function_call` items back.
  The [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning) requires:
  "ensure all items between the last user message and your function call output are passed into
  the next response untouched" — i.e. append **all** of `response.output` (reasoning items
  included), not a filtered subset. Same for the end of turn: main.py stores only
  `response.output_text` as a plain assistant message
  ([agent/main.py:55-56](../agent/main.py)), while the
  [conversation state guide](https://developers.openai.com/api/docs/guides/conversation-state)
  says to "preserve every item in the response's `output` array." Fix: `conversation +=
  response.output` after each call, then append the `function_call_output` items.
- **Stub tool bugs (template to replace, but note them):**
  `get_invoices(print_string: str)` takes a *required* positional arg while the schema declares
  `required: []` — a model call with `{}` raises `TypeError` in `execute_tool_call`'s
  `registry[name](**args)` ([agent/procurement_tools/invoices.py:32](../agent/procurement_tools/invoices.py),
  [agent/tools.py:25](../agent/tools.py)). The stub is also explicitly marked
  "NOT SAFE: RETURNS INVOICES FOR ALL SUPPLIERS"
  ([agent/procurement_tools/invoices.py:38-39](../agent/procurement_tools/invoices.py)).
  `execute_tool_call` has no try/except and no unknown-tool guard — a `KeyError`/`TypeError`/
  `httpx.HTTPStatusError` kills the process instead of returning an error string to the model.
- **Config:** `OPENAI_MODEL` env var defaults to `gpt-5.4` ([agent/main.py:14](../agent/main.py))
  — a valid id (§1.6) — but `.env.example` does not mention `OPENAI_MODEL`
  ([.env.example:1-5](../.env.example)).

### 5.3 Mock API tenancy model — the security criterion

- `supplier_id` is an **optional** query param on every list/get endpoint
  (e.g. [api/routers/invoices.py:14-15,40](../api/routers/invoices.py),
  [api/routers/purchase_orders.py:14,34](../api/routers/purchase_orders.py),
  [api/routers/contracts.py:14,31](../api/routers/contracts.py),
  [api/routers/catalog.py:14,36](../api/routers/catalog.py),
  [api/routers/analytics.py:13,42](../api/routers/analytics.py)).
- `filter_by_supplier`: "If supplier_id is None → return all items (no filtering)"
  ([api/filtering.py:11-13](../api/filtering.py)). There is no auth of any kind.
- Write paths: `POST /invoices` at least *requires* `supplier_id`
  ([api/routers/invoices.py:57](../api/routers/invoices.py)), but
  `POST /purchase-orders/{id}/acknowledge` acknowledges **any** supplier's PO when
  `supplier_id` is omitted ([api/routers/purchase_orders.py:45-49](../api/routers/purchase_orders.py)).
- `GET /suppliers/{id}` has no tenancy filter at all
  ([api/routers/suppliers.py:26-32](../api/routers/suppliers.py)) — any supplier's profile
  (rating, payment terms) is readable; the agent layer must decide what to expose.
- **Implication** (matches evaluation criterion 4, [ASSIGNMENT.md:22](../ASSIGNMENT.md)): the
  agent must be configured with a fixed supplier identity (e.g. `SUPPLIER_ID` env var) and every
  tool implementation must inject `supplier_id=<pinned>` into its httpx params in **Python** —
  never accept it as a model-visible tool parameter, or the LLM can be prompt-injected into
  reading other suppliers' data. Note the eval questions name *specific* suppliers
  ([evals/questions.json](../evals/questions.json) ids 2, 5, 7, 8, 10, 11), so the harness needs
  to either run per-supplier configs or treat cross-supplier questions as
  internal-analyst-persona runs — a design decision to defend.
