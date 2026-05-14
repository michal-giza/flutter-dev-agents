# ADR-0001: Cap returned PNG paths at 1920px long-edge

**Status:** accepted
**Date:** 2026-05-14

## Context

Claude's API rejects multi-image conversations when any image exceeds
2000px on the long edge. Modern phone screenshots routinely exceed
this: Galaxy S25 captures at 1080×2340, iPhone Pro Max at 1242×2796,
Galaxy S25 Ultra at 3120×1440. The first three or four screenshots
into a debug session would poison the conversation. Local vision
models (LLaVA, Qwen-VL) work best at ≤ 1024px on the long edge.

This bit us four times in production before we admitted it was an
architectural constraint, not a series of one-off fixes.

## Decision

Cap any PNG path the MCP returns to the agent at **1920 px on the
long edge** (configurable via `MCP_MAX_IMAGE_DIM`; `0` disables;
`896` for local-vision-model use).

Defence in three layers:

1. **Per-use-case caps** inside `TakeScreenshot`, `prepare_for_test`
   (the original live bug), `CompareScreenshot.diff_output_path`, and
   intermediate captures in `WaitForMarker` + `AssertPoseStable`.
2. **Dispatcher seatbelt** (`presentation/image_safety_net.py`) walks
   every response envelope, finds every PNG path, caps in place if
   over-cap.
3. **Hard-refuse guard** — if all backends fail (no cv2 / PIL / sips),
   remove the path from agent-visible fields, return
   `code: "ImageCapFailure"`, `next_action: "install_image_backend"`.

Originals preserved at `<path>.orig.png` so visual diff math keeps
full resolution via `prefer_original(path)`.

Goldens (`tests/fixtures/golden/**`) and release shots
(`<artifacts>/release/**`) are exempt — they have intentional
full-resolution semantics.

Three backends tried in order: **cv2** → **PIL** → **sips** (macOS
native, always available on dev machines).

## Consequences

**Easier.** Long multi-image sessions stay healthy. No need for the
agent to be image-budget-aware. Local 4B vision models work at native
input sizes via `MCP_MAX_IMAGE_DIM=896`. The `image_cap` diagnostic
in the envelope tells the operator what was capped.

**Harder.** Visual-diff workflows must use `prefer_original()`
explicitly when accuracy matters. Storage doubles (capped + original)
until `prune_originals` runs.

**Accepted.** Disk overhead from `.orig.png` companions —
addressed by ADR-0005 indirectly (retention policy).

## Alternatives considered

- **No cap, document the limit** — fails in production every time.
- **Compress to JPEG** — quality loss + Claude rejects on size differently.
- **Strip metadata only** — doesn't reduce pixel count.
- **Cap at 2000px exactly** — too close to limit; pixel-boundary edge cases.

## References

- `src/mcp_phone_controll/data/image_capping.py` — the capping module
- `src/mcp_phone_controll/presentation/image_safety_net.py` — the dispatcher seatbelt
- `tests/integration/test_image_cap_end_to_end.py` — the contract test
- `scripts/audit_artifact_dimensions.py` — historical recovery tool
- Commits `16b645d`, `a20aa5f`, `f66ca15`, `dc353b7`
