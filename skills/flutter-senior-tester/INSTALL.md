# Installing `flutter-senior-tester`

This skill auto-applies the senior-tester discipline whenever
the agent works on Flutter test files, repositories, Blocs, use
cases, or opens `pubspec.yaml`.

## Where the canonical source lives

```
flutter-dev-agents/skills/flutter-senior-tester/SKILL.md
```

The repo owns it. Any change to the discipline goes there first;
installations are copies / symlinks.

## Install targets

### Claude Code (CLI)

Per-user (recommended — applies to every project on this machine):

```bash
mkdir -p ~/.claude/skills/flutter-senior-tester
cp flutter-dev-agents/skills/flutter-senior-tester/SKILL.md \
   ~/.claude/skills/flutter-senior-tester/SKILL.md
```

Verify Claude Code picked it up — in a fresh session, type:

```
/skills
```

You should see `flutter-senior-tester` in the list. It will
auto-activate when you open any of the `paths:` patterns
declared in the frontmatter.

### Claude Desktop App (macOS / Windows)

Claude Desktop manages skills through the app UI:

1. Open Claude Desktop → **Settings** → **Capabilities** →
   **Skills**
2. Click **Add Skill** → **From File**
3. Select:
   ```
   ~/Desktop/flutter-dev-agents/skills/flutter-senior-tester/SKILL.md
   ```
4. Enable **Auto-activate based on file paths** (uses the
   `paths:` field in the SKILL.md frontmatter)

After this, opening any Flutter project in a Claude Desktop
workspace will activate the skill when you touch a path that
matches the trigger patterns.

If your version of Claude Desktop instead reads from a folder,
the standard location is:

```
~/Library/Application Support/Claude/skills/flutter-senior-tester/SKILL.md
```

Copy the SKILL.md there if the UI import isn't available:

```bash
mkdir -p "$HOME/Library/Application Support/Claude/skills/flutter-senior-tester"
cp flutter-dev-agents/skills/flutter-senior-tester/SKILL.md \
   "$HOME/Library/Application Support/Claude/skills/flutter-senior-tester/SKILL.md"
```

### Repo-local (per-project override)

If a specific Flutter project needs a tuned variant (e.g.
different `feature_kind` defaults), drop a project-local copy:

```bash
mkdir -p <project>/.claude/skills/flutter-senior-tester
cp flutter-dev-agents/skills/flutter-senior-tester/SKILL.md \
   <project>/.claude/skills/flutter-senior-tester/SKILL.md
# edit the local copy as needed
```

Project-local skills override user-global ones for sessions
opened in that project.

## Keep the installations in sync

The repo SKILL.md is the source of truth. Whenever it changes:

```bash
cp flutter-dev-agents/skills/flutter-senior-tester/SKILL.md \
   ~/.claude/skills/flutter-senior-tester/SKILL.md

cp flutter-dev-agents/skills/flutter-senior-tester/SKILL.md \
   ~/Desktop/claude_skills/skills/flutter-senior-tester/SKILL.md
```

Or symlink instead of copying so updates are automatic:

```bash
ln -sfn \
   "$(pwd)/flutter-dev-agents/skills/flutter-senior-tester/SKILL.md" \
   ~/.claude/skills/flutter-senior-tester/SKILL.md
```

(Caution: symlinks may not be followed by Claude Desktop's UI
import — for the Desktop app, prefer the file-import flow.)

## Dependencies

The skill is most valuable when **mcp-phone-controll** is
registered as an MCP server in the same Claude session. With it,
the skill auto-invokes:

- `design_test_plan` BEFORE writing tests
- `audit_test_quality` AFTER writing tests
- `audit_release_readiness` BEFORE merging

Without the MCP server, the skill falls back to applying the
discipline manually (the agent states the 8 principles, asks
for ACs, generates names, etc.). The discipline is the
high-leverage piece; the tools are just enforcement.

To register the MCP server in Claude Code:

```bash
claude mcp add phone-controll -- python -m mcp_phone_controll
```

In Claude Desktop: Settings → MCP Servers → Add Server →
configure with the same command above.

## Auto-trigger paths

The skill activates when the agent works on any of these:

| Pattern | Why |
|---|---|
| `**/pubspec.yaml` | Signals Flutter project-level work |
| `**/test/**/*.dart` | Writing/editing unit + widget tests |
| `**/integration_test/**/*.dart` | Writing/editing integration tests |
| `**/lib/features/**/*.dart` | Editing feature code — should think about tests |
| `**/lib/**/use_cases/*.dart`, `**/usecases/*.dart` | Use cases need 100% test coverage per project rule |
| `**/lib/**/repositories/*.dart` | Repos need Either-pattern + failure-path coverage |
| `**/lib/**/bloc/*.dart`, `**/cubit/*.dart` | Blocs need BaseBloc + widget tests with providers |

If the patterns are too aggressive for some projects, edit the
`paths:` list in the SKILL.md frontmatter — narrower glob =
less trigger.

## Uninstall

```bash
rm -rf ~/.claude/skills/flutter-senior-tester
rm -rf ~/Desktop/claude_skills/skills/flutter-senior-tester
# Plus remove from Claude Desktop via Settings → Skills if added there
```

## Companion skills already on the user's machine

- `flutter-ui-linter` — pre-handover UI bugs (overflow, layout
  crashes, design-system violations)
- `flutter-ads-consent` — mandatory pattern for ads / UMP / ATT
- `mcp-phone-controll-testing` — on-device test methodology
- `aso-release-prep` — app-store-listing readiness

`flutter-senior-tester` complements `mcp-phone-controll-testing`:
the latter covers ON-DEVICE testing methodology (Patrol, real-
device test flow), this one covers TEST-CODE DISCIPLINE (what
to write, how to structure, when to gate). They activate
together when both apply.
