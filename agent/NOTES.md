# NOTES — walkthrough guide

What was built, why it's shaped this way, and what was deliberately not
built. Companion docs: [SPEC.md](docs/SPEC.md) (requirements),
[DESIGN.md](docs/DESIGN.md) (module shapes), [CONTEXT.md](CONTEXT.md)
(domain glossary), [docs/adr/](docs/adr/) (decision records),
[docs/RESEARCH.md](docs/RESEARCH.md) (primary-source API research).

## Run it

```bash
uvicorn api.main:app --reload          # the mock API (upstream, untouched)
python -m agent.main --supplier 2      # REPL as SteelWorks
python -m evals.run                    # eval harness (1 run/question)
python -m evals.run --runs             # consistency mode (3 runs, majority)
python -m unittest discover -s agent/tests -t .   # 37 tests
python -m unittest discover -s evals/tests -t .   # 23 tests
```

Config: `.env` with `OPENAI_API_KEY`; optional `OPENAI_MODEL` (default
gpt-5.4), `API_BASE_URL`, `SUPPLIER_ID`, `EVAL_JUDGE_MODEL`.

## Architecture in one paragraph

`Session` is the deep module: one verb, `ask(text) -> TurnResult`, hiding
the Responses tool loop, tenancy, the permission gate, context pruning,
trace emission, and skill loading ([DESIGN.md](docs/DESIGN.md)). Around it
sit ports with two real adapters each — `PermissionPolicy` (console /
auto-deny), `TraceSink` (JSONL / in-memory) — and a tenant-bound
`ProcurementClient` behind an MCP-shaped `ToolRegistry`
([ADR 0002](docs/adr/0002-mcp-shaped-seams-without-mcp-protocol.md)).
The REPL and the eval harness are both thin callers of the same seam, and
tests assert only through it.

## The five load-bearing decisions

1. **Session-scoped tenancy.** One Session ↔ one Acting Supplier, fixed at
   construction. No tool schema has a supplier parameter — the model
   cannot even *express* a cross-tenant request; injection happens in the
   HTTP client. 404s use one wording for "doesn't exist" and "isn't
   yours" (Existence Ambiguity, [CONTEXT.md](CONTEXT.md)). Eval question
   12 is the regression test for this.

   **Worth asking me about:** the adversarial review found a real hole
   here. Resource ids from tool arguments were interpolated straight into
   URL paths, and httpx normalizes dot segments client-side — so
   `get_invoice(invoice_id="../suppliers")` reached `GET /suppliers`,
   an endpoint that ignores the pinned `supplier_id`, and returned the
   whole supplier directory. Nothing but the model's own schema-conformance
   stood in the way, which is exactly the guarantee this design claims
   *not* to depend on. Fixed by coercing every path id through
   `resource_id()` before interpolation
   ([procurement.py](procurement.py)), with tests that assert the
   outbound *path* keeps its resource prefix — the old test only checked
   that `supplier_id` was on the query string, which stayed true
   throughout the exploit.
2. **Claude-Code-style permission gate.** Mutations are Gated Tools: the
   *loop* intercepts them pre-execution and asks the human (y/n/always);
   a `confirm` parameter the model fills in would be the model approving
   itself. Declines return to the model as ordinary tool results.
   Headless default is auto-deny, so an eval run can never execute a side
   effect silently.
3. **Manual conversation list + content-elision pruning.** We own the
   transcript (`conversation += response.output` — all items, reasoning
   included, per the Responses reasoning contract). Pruning elides only
   the *content* of pre-turn tool outputs — never items — so
   `function_call`/`output` pairing can't break, and the stub tells the
   model how to re-fetch.
4. **Traces as the observability substrate.** Flat JSONL, OTel GenAI
   attribute names without the OTel SDK
   ([ADR 0001](docs/adr/0001-otel-genai-vocabulary-without-otel-sdk.md)),
   `session_id/turn/seq` correlation, payload-light. Stage 4 consumes
   them: the eval harness asserts on the same events the sink records
   (returned by value in `TurnResult.events`).
5. **Skills per the Anthropic Agent Skills shape.** `SKILL.md` +
   frontmatter; the system prompt carries only names + descriptions;
   bodies load on demand via `load_skill` (confined to the skills root).
   Skills own the domain decrees the API doesn't encode: Monthly Contract
   Value = annual/12, Delivered PO, Renewal Window, and the
   no-silent-arithmetic rule.

## Eval design (Stage 4)

Three layers per question, matched to category: **behavior** (which tools
ran, with which key args; the gate must stay silent on read-only
questions), **facts** (expected values computed from the API *at eval
time* — the seeded data is time-dependent: a 2025-due "pending" invoice
is dynamically overdue today, and hardcoded answers would rot), and a
**rubric judge** (structured outputs, fed precomputed FACTS so it never
does its own arithmetic — a judge failure means contradiction, not two
models doing math differently). The Responses API has no `seed`
([RESEARCH.md](docs/RESEARCH.md)), so non-determinism is handled by
repetition: `--runs` (default 3) reports majority verdicts and
per-question consistency. `expectations.json` maps each question to its
Session supplier; cross-tenant question 12 asserts scope-down plus zero
mentions of other suppliers' names.

## Process evidence

Design-before-code artifacts (glossary, ADRs, module design, spec) were
produced pre-fork and committed first. Implementation was test-first at
the seams DESIGN.md pre-agreed (60 stdlib-unittest tests; pytest isn't in
the pinned deps), each milestone gated by ruff + mypy and a two-axis
(standards + spec) review, plus a final multi-agent adversarial review
(findings triaged below). Work was tracked as issues #1–#8 on this fork.

## Adversarial review: what it found

A multi-agent review (4 dimension finders → one refuter per finding,
default-to-refuted) produced 22 candidate findings; 12 were refuted on
inspection, 10 survived and were fixed:

| Finding | Fix |
|---|---|
| Path traversal in resource ids → cross-tenant read | `resource_id()` coercion + path-prefix tests |
| `json.loads("null")` etc. → `AttributeError` out of `ask()` | non-dict arguments become an `invalid_args` envelope |
| A mid-turn crash left a `function_call` with no paired output | `finally` block pairs every call id before propagating |
| Judge exceptions / refusals / truncation sank the whole eval run | `JudgeError` + per-question `error` verdict |
| Ground-truth or session-construction failure escaped `run_question` | broad per-question catch, verdict `error` |
| Report written only at the end — a crash lost every result | incremental write after each question, plus `finally` |
| q4 asserted only 2 of 4 overdue ids, and no exact-set check | all ids required + an exact-set judge rubric |
| Missing `OPENAI_API_KEY` surfaced as a raw SDK traceback | explicit guard in the REPL |
| `Ctrl-C`/EOF at an approval prompt crashed the turn | fail-closed: interrupted prompt = decline |
| `--runs 0` silently produced a vacuous pass | rejected at argument parsing |

Refuted examples worth knowing (they look like bugs but aren't): pruning
"losing" data is the specified design (the stub tells the model to
re-fetch); `check_tools` being presence-only matches FR4.2(a); the
`DISABLE_SSL_VERIFY` path is upstream scaffold code, outside this diff.

## Descoped, deliberately

- **Streaming / event-generator interface** — one consumer today; a
  one-consumer seam is speculative. `TraceSink` is the observation
  extension point (DESIGN.md, "Rejected").
- **MCP integration** — hosted MCP can't reach localhost and moves
  execution outside our security boundary; client MCP needs a dependency
  the pinned requirements can't take. The registry seams are
  MCP-congruent so adopting it later is an implementation swap (ADR 0002).
- **LLM summarization for context management** — elision is deterministic
  and can't corrupt figures; summaries can.
- **`/analytics/spend-by-supplier` tool** — scoped to one tenant it
  degenerates into "my totals"; a near-duplicate tool wasn't worth its
  context weight.

## Known limitations (honest list)

- `CLAUDE.md` (repo root) still describes the upstream scaffold — it's
  outside the allowed diff (`agent/` + `evals/` only), so it was left
  stale on purpose.
- The context budget is a chars/4 heuristic, not a tokenizer; it prunes
  conservatively.
- The judge defaults to the same model family as the agent —
  same-family grading bias is acknowledged; `EVAL_JUDGE_MODEL` exists to
  swap it.
- A `TypeError` raised *inside* a tool body is reported as
  `invalid_args` (conflated with bad model arguments); acceptable at this
  tool surface's size.
- Tool outputs are fed back to the model as data; a hostile procurement
  API could attempt prompt injection through them. Out of scope here (the
  API is trusted upstream infrastructure), but the tenancy boundary would
  hold regardless — no instruction can widen the Acting Supplier.
- Sessions are single-threaded by contract (`ask()` is not reentrant).
