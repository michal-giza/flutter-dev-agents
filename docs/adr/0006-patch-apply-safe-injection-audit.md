# ADR-0006: `patch_apply_safe` shell-injection audit

**Status:** accepted
**Date:** 2026-05-15

## Context

`patch_apply_safe` is the use case agents call to apply a unified diff
against a Flutter project, run the quality gate, and auto-rollback on
regression. It is unique in the catalogue because it accepts two
agent-controlled fields that are passed *to git*:

- `project_path`: the working tree to operate in.
- `diff`: the unified-diff body to apply.

If an attacker compromised the agent's prompt (LLM prompt-injection,
upstream RAG poisoning, malicious tool output the model parroted back),
they could try to weaponise these fields into arbitrary command
execution on the developer's machine. The §7 code-review backlog from
[`docs/code-review-2026-05-15.md`](../code-review-2026-05-15.md) flagged
this as needing an explicit audit.

## Audit

The implementation in
[`packages/phone-controll/src/mcp_phone_controll/domain/usecases/patch_safe.py`](../../packages/phone-controll/src/mcp_phone_controll/domain/usecases/patch_safe.py)
runs three git commands (`git status --porcelain`, `git apply --check`,
`git apply`, `git diff --name-only`, `git checkout -- .`, `git clean -fd`)
plus one stat (`.git` existence check). The single subprocess helper is:

```python
async def _run(*cmd: str, cwd: Path) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(cwd),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
```

Three properties make this safe by construction:

1. **`asyncio.create_subprocess_exec(*cmd, ...)`** — the variadic `*cmd`
   becomes the literal argv list. No shell is invoked. Shell
   metacharacters (`;`, `&&`, `$( )`, backticks, redirects) in any
   argument are literal bytes to the child process. There is no path
   that calls `create_subprocess_shell` or `subprocess.run(..., shell=True)`.

2. **`project_path` flows only through `cwd=`.** It is never
   interpolated into argv. The kernel `chdir`s to that path before
   exec; nothing about the path string can affect what argv 0..n look
   like.

3. **`diff` content is written to a file, not passed to git on the
   command line.** Only the file path (`<project>/.mcp-pending.patch`,
   a fixed filename) appears in argv. The diff bytes land in the file
   and git reads them as patch input. Hostile diff bytes — even ones
   that look like shell — are treated as malformed unified-diff syntax
   and rejected by `git apply --check`.

Two regression tests in
[`tests/unit/test_patch_apply_safe.py`](../../packages/phone-controll/tests/unit/test_patch_apply_safe.py)
encode this contract:

- `test_project_path_with_shell_metacharacters_does_not_execute` — a
  `project_path` containing `; touch <canary>` fails the `.git`
  existence check; the canary file is never created.
- `test_diff_with_shell_metacharacters_does_not_execute` — a diff body
  laced with `$(touch …)`, backticks, and `;` is rejected by `git apply
  --check` as malformed; the canary file is never created.

If anyone ever refactors `_run` to use `shell=True` or starts building
command strings via interpolation, those tests break.

## Residual risks (not subprocess injection)

The audit confirmed no command-injection vector, but flagged three
adjacent concerns to keep visible:

1. **Privilege confusion.** `Path(...).expanduser()` resolves `~root` to
   `/root` for any user that can `getpwnam("root")`. Combined with an
   MCP running as root, an agent could operate on a different user's
   working tree. Mitigation: the MCP should never run as root; this is
   documented in `docs/architecture.md` as a deployment rule.

2. **Quality-gate bypass.** `skip_gate=True` lets an agent skip the
   regression gate. This is intentional (some agents want to apply a
   probe-patch and run a tighter custom check), but the field gets
   recorded in the trace repository so an operator reviewing a session
   can spot bypasses.

3. **Side-effects from a clean patch.** Even with this audit, a patch
   that legitimately edits `lib/main.dart` to call `Process.run("rm
   -rf …")` would compromise the project on the next `flutter run`.
   That is a problem for the gate (`run_quick_check` /
   `patch_apply_safe`'s gate runner), not for `_run`'s argv hygiene.

## Decision

No code change. The audit confirms the existing implementation is safe;
the two new tests lock the invariant. This ADR documents both so the
next reviewer doesn't have to re-derive the proof.

## References

- §7.5 of [`docs/code-review-2026-05-15.md`](../code-review-2026-05-15.md)
- CPython [`asyncio.create_subprocess_exec`](https://docs.python.org/3/library/asyncio-subprocess.html#asyncio.create_subprocess_exec)
  docs — explicit "no shell intermediary."
