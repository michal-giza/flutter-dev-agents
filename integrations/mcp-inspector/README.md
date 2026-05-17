# MCP Inspector — interactive debugging

[MCP Inspector](https://github.com/modelcontextprotocol/inspector)
is Anthropic's official tool for poking at any MCP server
interactively: list tools, call them with arbitrary args, see the
envelopes. Faster than spinning up Claude every time you tweak a
descriptor.

## One-line launch (npx)

```bash
npx @modelcontextprotocol/inspector \
  /path/to/flutter-dev-agents/.venv/bin/python -m mcp_phone_controll
```

This boots the inspector UI on `http://localhost:5173`, connects via
stdio to our server, and lists all 109 tools with their schemas.
Click any tool to invoke it with form-filled args.

## Repo `Makefile` shortcut

The repo's top-level `Makefile` exposes `make inspect`:

```bash
cd /path/to/flutter-dev-agents
make inspect
```

Equivalent to the npx command above but resolves the venv path
automatically and warns if the venv isn't built yet.

## What to check first

| Action | Why |
|---|---|
| Click `mcp_ping`, hit "Call tool" | Verify the right version is loaded — see `git_sha` field |
| Click `check_environment`, "Call tool" | All deps green? Watch for the new `image_cap_pipeline` row |
| Click `describe_capabilities`, level=`basic` | Inspect the 25-tool BASIC tier surface |
| Click `list_devices` | Confirm attached devices visible |
| Click `mcp_ping`, check `image_backends` | Should include at least PIL + sips on macOS |

## What it WON'T do

- Run multi-tool plans (use `run_test_plan` for that).
- Talk to a remote HTTP MCP — Inspector is stdio-only.
- Verify Claude-Desktop-side behaviour (host-specific UX like
  annotation prompts isn't surfaced).

## When to use it vs Claude / Claude Code

- **Use Inspector** when you've changed a descriptor schema or a
  use-case, want to verify the envelope shape directly, and don't
  want the LLM overhead of "explain to Claude what to try."
- **Use Claude / Code** when you're testing the agent-loop behaviour
  (which tools the model chooses, how it composes them).
