# Testing strategy

Three tiers, split by **what is real and what is substituted**. The model
is the dividing line: it is the only dependency that cannot be made
deterministic — the Responses API has no `seed`
([RESEARCH.md](RESEARCH.md)) — so the first two tiers script it and the
third accepts non-determinism as the thing under test.

| Tier | Files | Model | Procurement API | Runs in CI | Cost |
|---|---|---|---|---|---|
| **Unit** | `agent/tests/test_{pruning,skills_lib,procurement,registry,session}.py`, `evals/tests/*` | scripted | `httpx.MockTransport` | yes | free |
| **End-to-end** | `agent/tests/test_e2e.py` | scripted | **real uvicorn server over real HTTP** | yes | free |
| **Evals** | `evals/run.py` | **real** | real | no (needs a key) | tokens |

```bash
python -m unittest discover -s agent/tests -t .   # unit + e2e
python -m unittest agent.tests.test_e2e           # e2e only (~1s)
python -m unittest discover -s evals/tests -t .   # harness's own unit tests
python -m evals.run --runs                        # the eval tier, 3 runs
```

## Tier 1 — Unit

Tests at the seams [DESIGN.md](DESIGN.md) pre-agreed, never past them.
`prune()` is exercised as a pure function; `ProcurementClient` over a mock
transport; `Session` through `ask() -> TurnResult` with both the model and
the API substituted. Fast enough to run on every edit.

## Tier 2 — End-to-end

`agent/tests/test_e2e.py` runs **the entire stack for real except the
model**. `setUpModule` starts a genuine `uvicorn api.main:app` on an
ephemeral port; the agent then talks to it over real HTTP sockets, through
the production composition root (`make_session`), the tenant-bound client,
the real tool schemas, skills read from `agent/skills/` on disk, and a
`JsonlSink` writing an actual file. Only `FakeOpenAI` stands in for the
model, scripting which tools get called.

That boundary is deliberate: *whether the model picks the right tools* is
the eval tier's question, and answering it costs money and varies run to
run. *Whether everything downstream of that choice is correct* is a
question with one right answer, and this tier pins it — for free, in about
a second, with no API key.

The API's data is in-memory and resets on every start, so each run gets a
pristine fixture. Tests that mutate state (acknowledging POs) each act as
a **different supplier**, because the server is shared across the module
and tests must not depend on execution order — an earlier version failed
exactly this way, with one test consuming the POs another needed.

### The journeys it covers

| Journey | What it proves |
|---|---|
| Read | A question reaches live data and returns only the Acting Supplier's rows |
| Aggregates | Server-computed totals are reachable and tenant-scoped |
| Existence Ambiguity | Another supplier's invoice and a nonexistent one produce **byte-identical** errors |
| Traversal | `invoice_id="../suppliers"` never reaches the server, and no supplier data appears in the output |
| Fail fast | An unknown supplier is refused at construction |
| Decline | The gate is consulted, the API is never called, **server state is unchanged**, and the turn continues |
| Approve | The PO actually transitions `submitted → acknowledged`, verified by a fresh read |
| Session approval | The human is asked **once**; the second call rides the remembered decision |
| Skills | The menu advertises all three; instructions are absent from the prompt until `load_skill` returns them |
| Skill traversal | `../../.env` is refused |
| Traces | A real JSONL file, every line valid, correlated by `session_id`/`turn`/`seq`, OTel-named, payload-light |
| Conversation | History carries across turns, with the reply preserved as the model's own output item |

Two of those assertions are worth their weight on their own: the decline
journey checks the *server*, not just the envelope (a gate that returns
"declined" while the write lands is the bug that matters), and the approve
journey verifies persistence with a second read rather than trusting the
response body.

## Tier 3 — Evals

`python -m evals.run` runs the 12 assignment questions through real
Sessions against a real model. Three assertion layers, live-computed
ground truth, rubric judge; `--runs` for majority verdicts. See
[SPEC.md](SPEC.md) FR4 and the results discussion in
[../NOTES.md](../NOTES.md).

## What is deliberately not tested

- **The real OpenAI API.** No test calls it; the eval tier does, on
  purpose, and is not part of the test suite.
- **Model judgement in tiers 1–2.** Whether the model *chooses*
  `get_overdue_aging` over summing invoices is an eval question.
- **`api/`.** Upstream code, outside the allowed diff. The e2e tier runs
  it as a black box, exactly as production would.

## Notes for whoever runs this next

- Tests use stdlib `unittest`, not pytest: `requirements.txt` is pinned
  and outside the allowed diff, so no test dependency could be added.
- The e2e tier needs a free TCP port and about a second of startup. If
  `uvicorn` cannot start, the module fails loudly rather than skipping —
  a silently skipped e2e suite is worse than none.
- Two leaks were found by writing these tests and fixed rather than
  papered over: `ProcurementClient` connection pools were never released
  (dozens leak across an eval run), and `make_session` leaked one when its
  fail-fast check rejected a supplier. Hence `Session.close()`.
