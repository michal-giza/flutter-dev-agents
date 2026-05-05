# Adding a new MCP package

The umbrella holds N MCPs side-by-side. Each is an independent Python package with its own pyproject, entry points, and tests. Cross-MCP code sharing happens through workspace dependencies — never copy-paste.

## When to add a new MCP vs. extend an existing one

Add a new MCP when the surface is a **distinct concern with its own lifecycle**:

- "deploy to App Store" — different toolchain, different async lifecycle, different security model than `phone-controll`.
- "analytics replay" — long-lived event-stream consumer, irrelevant to device control.
- "design-system snapshot tester" — needs Figma OAuth, different artifacts.

**Don't** add a new MCP just because a feature is big. The dev-session module (debug session control) is a candidate to extract eventually, but it lives inside `phone-controll` for now because it's the same lifecycle (one developer, one set of devices, one factory) — until we have a concrete reason to separate.

## The recipe

### 1. Scaffold the package

```bash
cd ~/Desktop/flutter-dev-agents/packages
cp -R phone-controll <new-name>
cd <new-name>
# rename the python package directory and the entry point in pyproject.toml
```

Edit `packages/<new-name>/pyproject.toml`:

```toml
[project]
name = "<new-name>"
version = "0.1.0"
dependencies = [...]    # only what this MCP needs

[project.scripts]
<new-name> = "<new_package>.__main__:main"
```

### 2. Strip down to your domain

Delete domain entities / repositories / use cases that don't apply to your MCP. Keep:

- `Result` / `Err` / `Ok` / `Failure` (with `next_action`)
- `BaseUseCase`
- `ToolDispatcher` / `ToolDescriptor`
- `AsyncProcessRunner`
- The skill-of-failure-envelopes pattern

These are universal. Eventually we'll factor them into a shared package under `packages/_shared/` — until then, copy is fine. The cost of duplication is low; the cost of premature abstraction is higher.

### 3. Write your domain layer

Entities, failures (with `next_action`), repository protocols, use cases. **Domain depends on nothing**.

### 4. Write your data + infrastructure layer

Repositories implementing the domain protocols, parsers, subprocess wrappers.

### 5. Wire the container + presentation

`container.py` composes everything. `tool_registry.py` registers each tool with a description ≤ 40 words.

### 6. Add an HTTP sub-router (optional, recommended)

In the umbrella's HTTP adapter, mount a router at `/<new-name>/*` exposing your tools. Following the pattern keeps the door open to extracting the package into a standalone MCP later.

### 7. Tests

- Pure-function tests for parsers.
- Use-case tests against fake repositories.
- Tool-registry coverage test asserting your expected tool names match.
- HTTP-adapter test if you exposed a sub-router.

### 8. Documentation

- `packages/<new-name>/README.md` — how to install + register + use.
- A section in the umbrella `README.md` listing your package.
- A test plan template in `examples/templates/<new-name>-smoke.yaml` if applicable.

### 9. CI

GitHub Actions iterates `packages/*` automatically — your tests run on every PR with no further config.

## CI image (planned, not yet built)

Each package can opt into a Docker image for CI:

- `packages/<new-name>/docker/Dockerfile.ci` — Linux x86_64, headless toolchain, the package itself pre-installed.
- `.github/workflows/ci-<new-name>.yml` — runs the package's headless tests inside the image.

For `phone-controll` this means an Android-emulator-in-Docker image. iOS cannot be containerised (Apple-side); native macOS runs handle iOS flows.

## What this gets you

- **Independent versioning** — each MCP releases on its own cadence.
- **Clean extraction** — `git filter-repo --subdirectory-filter packages/<name>` peels any package back into its own repo if the project grows beyond the umbrella.
- **Atomic refactors** — change a shared type in one PR; CI catches every consumer.
- **One install** — for the developer, `uv pip install -e ".[dev]"` once and every MCP is on PATH.
