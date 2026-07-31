# Traces use OTel GenAI vocabulary as flat JSONL, without the OTel SDK

Stage 3 requires machine-parseable traces, and our eval harness (Stage 4) asserts on them, so the schema is load-bearing. We emit flat JSONL events (one line = one event, `session_id`/`turn`/`seq` correlation) whose attribute names are borrowed from the OpenTelemetry GenAI semantic conventions (`gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.tool.name`, `gen_ai.tool.call.id`) — but we do not depend on the OTel SDK. Reasons: the assignment forbids agent frameworks and favors zero-dependency code; the GenAI conventions are still status-Development (an SDK pin would chase a moving spec); and plain `json.dumps` keeps tracing a ~40-line concern. The half-adoption is deliberate: names align with the emerging standard so the traces are future-portable to real OTel backends, while the emitter stays ours.

## Considered Options

- Full OTel SDK with spans/exporters — rejected: heavy dependency, spec still in Development, reads as a framework in a no-frameworks assignment.
- Invented schema — rejected: no migration path, and reviewers can't map it to anything they know.
- Nested per-turn JSON documents — rejected: requires buffering a whole turn (a crash loses exactly the turn you need) and encodes ordering twice; the nested view is recoverable from flat events with a groupby.
