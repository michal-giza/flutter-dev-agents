# Tomorrow afternoon — the 90-minute first task

**Date:** Saturday 2026-05-16.
**Time budget:** 90 minutes, undivided.
**Why one task and not five:** the trap when starting a curriculum
is doing many small things and ending the day with no validated
artifact. We pick **one** concrete thing that ships and produces
feedback.

---

## The task

**Write Lesson 1 of the flagship course in publishable form.**

The Lesson 1 outline is already drafted at
`docs/teaching/lesson-01-the-4am-test.md`. Your job is to turn it
into the *publishable* version — the version that goes on your blog
or in a private repo for prospective students.

What "publishable" means:

1. **You ran the worked example end-to-end** from a clean directory.
   Time yourself. Note any gotcha.
2. **The exercise 2.1 ("add list_devices") has a tested solution** in
   a separate file you don't show students.
3. **You wrote `lesson-01-troubleshooting.md`** with at least 3 real
   failure modes you hit (no `adb` on PATH; Polish-locale phone;
   wrong Python version).
4. **The lesson's narrative reads well to someone who isn't you.**
   You read it out loud and don't cringe.

That's it. One lesson. Polished. Tested. Publishable.

---

## Anti-task list (things NOT to do tomorrow)

- ~~Write Lessons 2-8.~~ One lesson at a time. Validate before
  writing the next.
- ~~Build a marketing landing page.~~ The landing site is already
  drafted. Tomorrow isn't the day to revise it.
- ~~Run a benchmark.~~ Benchmarks are a separate session.
- ~~Add new tools to flutter-dev-agents.~~ No code changes.
- ~~Read all 6 instructor-prep readings.~~ Read 1, maybe 2 if you're
  fast. (See "If you finish early" below.)

The discipline: **one ship per session**. The lesson is the ship.

---

## Hour-by-hour breakdown

### Minutes 0-10: Set up + clean-room

Open a fresh terminal. `cd` to an empty directory. **Do not have
flutter-dev-agents open.** You're testing the lesson as a student
would.

```bash
mkdir ~/teaching-test && cd ~/teaching-test
```

Open the lesson file in your editor. Read Phase 1 (the worked
example) once, top to bottom, *without typing*.

### Minutes 10-40: Type the worked example

Follow your own instructions exactly. Don't skip ahead. Don't
"improve" the code mid-flight.

Notes to keep open:

- Anywhere you have to look something up.
- Anywhere the instructions are ambiguous.
- Anywhere your IDE wants to autocomplete differently than the
  lesson expects.

These are your refinement points.

### Minutes 40-60: Do exercise 2.1 yourself

You wrote the half-blank scaffold. Now solve it. **Save the
solution** in a separate file:
`docs/teaching/lesson-01-solutions.md` (not visible to students;
add to .gitignore-of-publication).

Time yourself. If it took you, knowing the codebase, more than 15
minutes, the exercise is too hard for a student. Tighten the
scaffold.

### Minutes 60-75: Write the troubleshooting doc

Open `docs/teaching/lesson-01-troubleshooting.md`. Document each
failure mode you hit or expect a student to hit:

```
## adb: command not found
Symptom: `subprocess.run(["adb", ...])` raises FileNotFoundError.
Fix: brew install android-platform-tools (macOS) /
     apt install adb (Linux).

## "no devices/emulators found"
Symptom: list_devices returns empty.
Fix: enable USB debugging, accept the dialog. Or: start an emulator
with `emulator -avd <name>`.

## Polish-locale phone returns Polish error strings
... etc.
```

Aim for 3-5 entries. Each one is real.

### Minutes 75-85: Read your lesson out loud

Read Phases 0-4 of `lesson-01-the-4am-test.md` aloud. Slowly.
Anything that makes you cringe — wrong tone, ambiguous instruction,
unsupported claim — mark with `[?]` and fix after.

This catches more issues than any other pass. It's worth the 10
minutes.

### Minutes 85-90: Commit + write tomorrow's note

```bash
cd ~/Desktop/flutter-dev-agents
git add docs/teaching/lesson-01-*
git commit -m "lesson 1: publishable draft + troubleshooting"
```

Write a 2-line note in `docs/teaching/learning-log.md`:
- What surprised you about your own lesson.
- What you'll change in Lesson 2's drafting workflow as a result.

That's it. Lesson 1 is shipped.

---

## If you finish early (rare but possible)

Use the remaining time to read **one** of:

1. **The Carpentries Instructor Training Curriculum overview**
   — https://carpentries.github.io/instructor-training/
   (~20 minutes, the lesson-template section is the gold).
2. **Andy Matuschak — Why books don't work**
   — https://andymatuschak.org/books/ (~25 minutes, sharpens
   the "exercises matter" intuition).

Both are short. Both will change how you write Lesson 2.

**Do not** start writing Lesson 2 itself tomorrow. The point of
the one-task discipline is to feel what it's like to ship a single
validated lesson. Lessons 2-8 come next week.

---

## How to know it worked

Sunday morning:

- [ ] Re-read your published Lesson 1 once. Still good?
- [ ] DM it to 3 Flutter developers you know. Ask: "Could you do
  this in 90 minutes?"
- [ ] Don't push back on their feedback. Write it down. Use it for
  Lesson 2.

If 2 out of 3 say "yes, I think so" — Lesson 1 is validated. Move
to Lesson 2 next weekend.

If 2 out of 3 say "no, this is unclear" — rewrite Lesson 1 next
weekend instead. Don't move on with a broken first lesson; the
funnel leaks.

---

## Why this specific task and not something else

You have a backlog of options:

1. ✅ Write Lesson 1 (what we're doing)
2. Write Lessons 1-8 outline-only
3. Build the n8n cohort-payment flow
4. Email 10 prospective students with the course outline
5. Record a video demo
6. Split tool_registry.py per the code review

(1) wins because:

- **It's the smallest validated unit.** You can't sell a course
  without at least one well-tested lesson. Everything else
  presupposes this.
- **It's the highest-information action.** Until you've written
  one lesson and tested it on real people, every plan for
  Lessons 2-8 is guesswork.
- **It has 24-hour feedback.** DM 3 people Sunday morning, hear
  back by Monday. Compare to (4), which has weeks of latency.
- **It teaches you about your own teaching.** You'll discover what
  takes you longer than expected, what you over-explain, what
  you under-explain.

The other options are all valid — just not first.

---

## After tomorrow

Mark `docs/teaching/strategy.md` Week 1 as ✅ done. Week 2 starts
next Saturday: draft Lesson 2 the same way. By Week 4 you have
half the flagship written and 3 weeks of student feedback.

This is how a credible course is built. Not by writing all 8
lessons in a marathon and discovering on launch day that Lesson 3
is incomprehensible.
