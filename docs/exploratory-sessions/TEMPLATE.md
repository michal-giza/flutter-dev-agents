# Exploratory session — `<topic>`

> Date: `YYYY-MM-DD`
> Tester: `<name>`
> Time-box: `<minutes>` (cap; stop when it expires)
> Status: `planned` / `in_progress` / `complete` / `abandoned`

## Charter (write BEFORE starting)

### Mission

One sentence. What are you looking for? Examples:

- *"Find UI patterns the Polish locale breaks that the test suite
  doesn't catch yet."*
- *"Reproduce the AVD respawn-loop with the UIAutomator2 helper
  and characterise the trigger."*
- *"Stress-test deep-link routing on the Galaxy S25 with rapid
  consecutive intents."*

### Areas to explore

3–6 concrete surfaces. Be specific.

1. `…`
2. `…`
3. `…`

### What I'm explicitly NOT testing

Drawing the box helps focus the session. e.g.:

- Performance under low memory (separate charter)
- Backend retry semantics (separate charter)

### Hypothesis (optional)

One sentence about what you expect. Lets you compare expected
vs actual at the end.

---

## Session log (fill in DURING)

Append entries in chronological order. **Don't filter** — write
down anything that surprises you. Filtering happens at the end.

### `HH:MM` — `<observation slug>`

- **Trigger**: what action led to this
- **Observed**: what actually happened (screenshots / log lines
  inline as `[screenshot: 07_settings.png]` or
  `[log: BoardFlow PID 3719 respawned ...]`)
- **Expected**: what you thought would happen
- **Reproducible?**: yes / no / sometimes
- **Repro steps**: numbered list

### `HH:MM` — `<observation slug>`

…

---

## Findings (write AFTER time-box ends)

### Automated cases that should land

Each finding → one test case or one audit rule. Discipline #6
says **2–3 new automated cases per session**. If you got 0, the
charter was too narrow.

1. **Rule / test case**: `<should_X_when_Y name>`
   - Owner: `<who>`
   - Target tool / file: `<path>`
   - Severity: `blocker` / `serious` / `minor`
2. `…`
3. `…`

### Findings NOT becoming automated cases (yet)

- Why each one is being deferred (data needed / requires real
  device only available rarely / etc.)

### Charter health check

- Mission as written: still right? If not, what's the better
  next-session charter?
- Time-box: was it about right? Too narrow / too wide?
- Areas: which one was the highest-value? Which one was a dud?

---

## Follow-up

- [ ] File issues / tickets for the automated cases above
- [ ] Close out by linking to the PR that lands them
- [ ] If a new rule was added to an audit tool, link the commit

---

## Format conventions

- File name: `YYYY-MM-DD-<topic-slug>.md` so they sort
  chronologically in the directory
- Keep the charter section short — bullet points, not prose
- Session log is timestamped because re-reading "I saw this then
  THAT" matters more than narrative
- Findings section is the only one others will read after the
  session — make it scannable
- Don't delete entries. If something turned out to be a red
  herring, strikethrough it and note why. The thinking process
  is part of the value.
