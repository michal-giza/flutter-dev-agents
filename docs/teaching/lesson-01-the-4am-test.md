# Lesson 1 — The 4 AM Test

> *I have six Flutter apps. Last Tuesday at 4 AM, one of them ran a
> test, captured a screenshot, and posted to Slack — while I slept.
> Here's how, in 90 minutes.*

**Audience:** You know Flutter. You've installed Python before. You
have not heard of MCP, and that's fine.

**Time:** 90 minutes (10/20/35/15/10 split — see structure below).

**You will build:** A working MCP server with one tool that captures
an Android screenshot. Claude Code calls it. The screenshot lands
on disk. End-to-end.

**You won't build (yet):** Patrol tests, multi-project locks, hot
reload, AR vision pipelines. Those come later. We're proving the
loop works first.

---

## Structure (Carpentries pattern — 5 phases, 90 min)

```
0:00  Mini-lecture (10 min)        — Why an MCP, why a factory
0:10  Live walkthrough (20 min)    — Worked example, full code
0:30  Your exercise (35 min)       — Faded guidance, you type
1:05  Review + Q&A (15 min)        — What you should ask yourself
1:20  Independent (10 min)         — Plug it into one of YOUR apps
```

---

## Phase 0 — Mini-lecture: Why a factory beats a workshop

A workshop is one developer, hand-shaping each app. A factory is
small composable tools that other things drive. Tesla's factory
isn't impressive because the robots are clever — it's impressive
because each station does one well-defined thing, and the
orchestrator chooses the order.

Your apps are the products. The orchestrator is an agent (Claude,
or a local 4B model, or you typing). The stations are tools — each
one does one well-defined thing on a real device.

**Why "MCP" specifically?** Model Context Protocol is a standard
that lets agents call tools over JSON-RPC. It's *not* magic. By the
end of this lesson you'll have read the bytes on the wire.

**Why not "just write a CLI"?** A CLI works. An MCP server works
PLUS the LLM can introspect the tool catalogue, fix its own
argument mistakes, and chain calls. We're betting the LLM gets
better at this over time, and we want to be on that train.

**Worth pausing on:** the agent will make mistakes. Half this
course is about teaching you to design tools that survive an
unreliable narrator. We start that in Lesson 2. Today is the
happy path.

**Citations:**
- MCP spec: https://modelcontextprotocol.io
- Karpathy's "build the production thing" framing —
  https://karpathy.ai/zero-to-hero.html
- This course's repo: https://github.com/michal-giza/flutter-dev-agents

---

## Phase 1 — Live walkthrough (worked example, 20 min)

You'll watch (or read) this section. **Do not type yet.** Cognitive
load research is very specific on this: typing while you're trying
to understand structure overflows working memory. Read first.

### The minimum viable MCP — 50 lines

We're going to build a one-tool MCP that takes a screenshot using
`adb`. Five files:

```
my-first-mcp/
├── pyproject.toml             # deps + entry point
├── server.py                  # the MCP server itself
└── tests/
    └── test_smoke.py          # one test
```

**File 1 — `pyproject.toml`** (15 lines):

```toml
[project]
name = "my-first-mcp"
version = "0.0.1"
requires-python = ">=3.11"
dependencies = ["mcp>=1.2.0"]

[project.scripts]
my-first-mcp = "server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**File 2 — `server.py`** (35 lines):

```python
"""A single-tool MCP server: take an Android screenshot via adb."""

from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime
from pathlib import Path

from mcp.server import Server
from mcp.types import TextContent, Tool

app = Server("my-first-mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="take_screenshot",
            description="Capture an Android screenshot to ~/screenshots/",
            inputSchema={
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Filename label."},
                },
                "required": [],
            },
        )
    ]


@app.call_tool()
async def call_tool(name: str, args: dict) -> list[TextContent]:
    if name != "take_screenshot":
        return [TextContent(type="text", text=f'{{"ok":false,"error":"unknown tool {name}"}}')]
    label = args.get("label", "shot")
    out_dir = Path.home() / "screenshots"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"{stamp}-{label}.png"
    result = subprocess.run(
        ["adb", "exec-out", "screencap", "-p"], capture_output=True, timeout=15
    )
    if result.returncode != 0:
        return [TextContent(type="text", text=f'{{"ok":false,"error":"adb failed: {result.stderr.decode()}"}}')]
    out_path.write_bytes(result.stdout)
    return [TextContent(type="text", text=f'{{"ok":true,"path":"{out_path}"}}')]


def main():
    from mcp.server.stdio import stdio_server
    asyncio.run(_run())


async def _run():
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())
```

**File 3 — `tests/test_smoke.py`** (10 lines):

```python
"""Tiny smoke test: the tool list responds to a list_tools call."""

import asyncio

from server import list_tools


def test_list_tools_returns_take_screenshot():
    tools = asyncio.run(list_tools())
    assert len(tools) == 1
    assert tools[0].name == "take_screenshot"
```

### What's worth noticing

1. **The schema is the API.** Claude reads `inputSchema` to know how
   to call you. The schema is JSON Schema; the same one OpenAPI uses.
   It's not a Python thing.
2. **The return shape matters.** A list of `TextContent` items. Claude
   reads the `text` field. We're returning JSON-as-string by hand —
   in the real `phone-controll`, the dispatcher wraps this for us, but
   here we do it explicitly so you see the bytes.
3. **`subprocess.run` is the actual work.** Every "fancy" agent tool
   is, at the bottom, a subprocess or an HTTP call. Don't be
   intimidated by the LLM stuff. The leaf-level work is normal Python.
4. **Error structure matters even in 50 lines.** We return
   `{"ok": false, "error": "..."}` not a raw exception. Reason: the
   LLM has to act on the error. A traceback is human-readable; a
   structured JSON envelope is machine-readable. We'll go deeper on
   this in Lesson 3.

### Run it

```bash
uv venv && uv pip install mcp
claude mcp add my-first-mcp -- python /path/to/server.py
# In a Claude Code session:
> use my-first-mcp to take a screenshot labeled "test"
```

Claude calls your tool. You get a PNG. **Stop and feel that.** You
just wrote an LLM-callable tool with no framework magic.

---

## Phase 2 — Your exercise (faded guidance, 35 min)

Now you type. Two tasks, increasing in independence.

### Exercise 2.1 — Add a second tool (worked-half-blank, 15 min)

Add a tool called `list_devices` that runs `adb devices` and returns
the parsed device list. The MCP-shaped scaffold is below; **you
fill in the body where marked.**

```python
@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(name="take_screenshot", description="...", inputSchema={...}),
        Tool(
            name="list_devices",
            description="List adb-attached Android devices.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, args: dict) -> list[TextContent]:
    if name == "take_screenshot":
        # ... existing body ...
        pass

    if name == "list_devices":
        # YOUR CODE HERE.
        # Run `adb devices`, parse the output, return JSON.
        # Expected output shape: {"ok": true, "data": [{"serial": "...", "state": "..."}]}
        pass
```

Don't peek at the answer. If you're stuck for 5+ minutes, the
hint is: `adb devices` returns lines like `R3CYA05CHXB\tdevice`,
tab-separated.

### Exercise 2.2 — Independent (20 min)

Pick **one** of your real Flutter apps. Plug your MCP into Claude
Code. From Claude Code, ask it to:

1. List your connected devices.
2. Take a screenshot labeled `before`.
3. Take a screenshot labeled `after`.

Then in your terminal:

```bash
ls -la ~/screenshots/
```

You should see two PNGs with reasonable file sizes. If the second
screenshot is identical to the first (same hash), debug why.

**This is the lesson's pass/fail bar.** If you don't get to two
distinct PNGs in your real folder, stop and figure out where it
broke before moving to Lesson 2. Common failure modes are documented
in `docs/teaching/lesson-01-troubleshooting.md` (write this as you
hit issues).

---

## Phase 3 — Review + Q&A (15 min)

Questions you should be able to answer before moving on:

1. **What's the wire format between Claude Code and your MCP?**
   (JSON-RPC over stdin/stdout, framed by Content-Length headers.)
2. **Where would you add a third tool? What's the minimum diff?**
   (One Tool entry in list_tools; one branch in call_tool.)
3. **Why does the return value carry `"ok": true/false` instead of
   raising exceptions?** (LLM has to act on it; tracebacks are
   for humans.)
4. **What's the role of the JSON Schema in `inputSchema`?**
   (Tells the LLM what arguments are valid; the LLM uses it to
   format calls.)

If any answer is "I don't know," re-read Phase 1 before continuing.

---

## Phase 4 — Independent extension (10 min)

This bit isn't required for moving on. It's where curious students
push further:

- Add a `take_screenshot` `serial` arg so you can target a specific
  device when more than one is attached.
- Time how long `subprocess.run(["adb", "exec-out", ...])` takes.
  (Probably 1-3 seconds. Worth noticing for Lesson 8 when we
  optimise.)
- Read the actual bytes by setting `MCP_LOG_FORMAT=json` if you've
  installed `flutter-dev-agents`. See what the dispatcher sees.

---

## What you've now learned (Bloom's taxonomy)

- **Remember**: the MCP message shape (`list_tools`, `call_tool`).
- **Understand**: why tool descriptions and schemas matter to the LLM.
- **Apply**: built two tools, one with guided code and one independent.
- **Analyze**: identified failure modes if your second screenshot is
  identical to the first.

We haven't yet hit **Evaluate** (judge between alternatives) or
**Create** (design new tools without scaffolding). Those come in
Lessons 3 + 7.

---

## What's coming in Lesson 2

You'll refactor your two-tool MCP into 3 layers: use case →
repository → descriptor. Identical behaviour; different shape.
Then we'll show you a bug that the layered version catches and
the flat version doesn't.

If you finished Lesson 1 in under 90 minutes, you're ahead. Use
the time to skim `src/mcp_phone_controll/domain/usecases/observation.py`
and notice how it maps to what you just wrote.

If you took longer than 90 minutes, that's fine. Write down where
you got stuck — it's the highest-value feedback for the course.

---

## Citations + further reading

- **MCP spec** — https://modelcontextprotocol.io
- **`mcp` Python package** — https://github.com/modelcontextprotocol/python-sdk
- **JSON-RPC 2.0** — https://www.jsonrpc.org/specification
- **adb `screencap`** — Android docs
- **The production reference**: this course's
  `flutter-dev-agents/packages/phone-controll/src/mcp_phone_controll/domain/usecases/observation.py`
- **Karpathy's framing** — https://karpathy.ai/zero-to-hero.html
- **Sweller, Cognitive Load Theory** — for *teachers* of this
  material; not required reading for students.

---

## For the instructor (you, Michal)

Before publishing this lesson:

- [ ] Run the worked example yourself, end-to-end, from a clean
  checkout. Time yourself. Should be ~15 minutes for you, ~45 for
  a student.
- [ ] Test exercise 2.1 with **no prior knowledge.** Ask a friend
  who knows Python but not MCP. Their stuck-points are your
  refinement notes.
- [ ] Have the "real-app" exercise (2.2) handy with 2-3 known
  failure modes documented (Polish-locale phone, no device
  connected, `adb` not on PATH). This is your `lesson-01-
  troubleshooting.md` companion doc.
- [ ] Don't add a "Lesson 1 also covers X" creep. The discipline of
  one big idea per lesson is the lesson.
