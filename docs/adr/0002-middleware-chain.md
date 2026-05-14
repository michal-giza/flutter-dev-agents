# ADR-0002: Dispatcher as a middleware chain, not a god method

**Status:** accepted
**Date:** 2026-05-14

## Context

The `ToolDispatcher.dispatch()` method grew to ~120 LOC handling
seven cross-cutting concerns inline: Patrol-active tracking, rate
limiting, circuit breakers, output truncation, image-cap seatbelt,
trace recording, auto-narrate. Every new concern added another
else-branch. Testing one concern required either reaching into
private state (`d._auto_narrate_every = 2`) or running the whole
dispatcher.

## Decision

Split each concern into a `Middleware` class with optional
`pre_dispatch(name, args) -> envelope | None` and
`post_dispatch(name, args, envelope) -> envelope` hooks. The
dispatcher walks the chain:

1. Run `pre_dispatch` hooks in order. Any may short-circuit.
2. Invoke the use case.
3. Run `post_dispatch` hooks in **reverse** order (LIFO so wrappers
   compose).

Short-circuits still flow through the post-dispatch hooks of
middlewares that already pre-traversed, so trace + seatbelt see the
rejection envelope.

Canonical chain (order matters):

```
PatrolGuard → RateLimiter → OutputTruncation
→ ImageSafetyNet → TraceRecorder → AutoNarrate
```

Dispatcher constructor accepts `middlewares=` for full control;
default chain via `build_default_chain()`.

## Consequences

**Easier.** Each middleware is independently unit-testable (12 new
tests in `test_middleware_chain.py`). Adding a new concern — OTel
spans, prom counters, sandbox enforcement, Reflexion middleware — is
one new class instead of another else-branch. The dispatcher is back
to a ~20-line orchestrator.

**Harder.** One indirection. Reading the dispatch sequence requires
also reading the chain config. Mitigated by keeping the default
chain in one obvious place (`build_default_chain`).

**Accepted.** Slightly more allocation per dispatch (loop overhead).
Negligible vs the I/O the actual tool does.

## Alternatives considered

- **Aspect-oriented decorators** — Python's syntax is ugly for this.
- **Per-tool hooks** — would push concerns into tool descriptors,
  defeating the cross-cutting goal.
- **Leave the god method** — works, but every future concern adds
  branching complexity.

## References

- `src/mcp_phone_controll/presentation/middleware.py`
- `src/mcp_phone_controll/presentation/tool_registry.py` — `ToolDispatcher`
- `tests/unit/test_middleware_chain.py`
- Commit `c675a0c`
