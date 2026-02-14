# CLAUDE.md

## Philosophy

### Core Beliefs

We build software through small, verified steps:

- **Incremental progress over big bangs** — Small changes that compile and pass tests
- **Learn before implementing** — Study existing code and plan before writing
- **Clear intent over clever code** — Be boring and obvious
- **Single responsibility** — Per function, per class, per module
- **Avoid premature abstractions** — Don't generalize until you have three concrete cases
- **Consistency over preference** — Match existing patterns even if you'd do it differently

### Working Principles

- **Verify before claiming** — Run tests and confirm output before asserting success
- **Minimize blast radius** — Make the smallest change that solves the problem
- **Ask when uncertain** — Stop and ask rather than guessing or assuming
- **Challenge, don't comply** — When the user suggests an approach, evaluate it critically. If you see problems, risks, or better alternatives, say so. Agreeing to avoid friction wastes time and produces worse outcomes.
- **Finish what you start** — Complete the current task fully before moving to the next
- **One problem at a time** — Don't solve multiple issues in a single change
- **Leave the codebase better than you found it** — Within files you're already touching, fix cosmetic issues (typos, whitespace, formatting). Do not remove code or refactor working logic.

### Architecture & Code Style

**Architecture:**
- Composition over inheritance — use dependency injection
- Interfaces over singletons — enable testing and flexibility
- Explicit over implicit — clear data flow and dependencies
- Fail fast — descriptive error messages with context
- Handle errors at the appropriate level — never silently swallow exceptions

**Code style:**
- Match, don't invent — find similar code and follow its pattern exactly
- Follow existing conventions — match the project's style, not your preferences
- Use project tooling — the project's formatter, linter, and build system
- No commented-out code — version control is the archive
- No TODO comments without tracking — every TODO must be in BUGS_AND_TODOS.md

### Testing

**Test-Driven Development is mandatory:**
1. **Red** — Write a failing test first
2. **Green** — Write minimal code to pass
3. **Refactor** — Improve while keeping tests green

**Test quality:**
- Test behavior, not implementation — verify what the code does, not how
- One logical assertion per test — if it fails, you know exactly what broke
- Tests must be deterministic — no flakiness
- Avoid over-mocking — mock external dependencies, not internal code

**Integration tests verify wiring:** Unit tests prove functions work in isolation. Integration tests must prove functions are actually called in the correct sequence. For every function in a workflow, write an integration test that verifies the function's effect through externally observable side effects.

### Critical Rules

**Never:**
- Commit secrets or credentials (API keys, tokens, passwords, .env files)
- Disable, skip, or delete tests to make them pass
- Use `--no-verify` to bypass commit hooks
- Claim work is complete without running tests and verifying output
- Push directly to main or force push to shared branches
- Continue after 3 failed attempts — stop and reassess

### When Blocked

When you hit a wall (3 failed attempts, unclear path forward, unexpected behavior):

1. **Stop** — Do not attempt workarounds without developer input
2. **Notify** — If `~/.claude/hooks/notify.sh` exists, fire a notification so the developer knows you need attention:
   ```bash
   echo '{"hook_event_name":"Notification","message":"Blocked — need your input","cwd":"'"$(pwd)"'"}' | ~/.claude/hooks/notify.sh
   ```
3. **Report:**
   - What I was trying to do
   - What I tried
   - What failed and why
   - What I need from you to move forward
4. **Wait** — Get developer guidance before proceeding

This prevents errors from compounding. A workaround on task 2 becomes a shaky foundation for tasks 3, 4, and 5.

---

## Planning

### Context First

You must understand context before writing any code. Before starting work, ensure you've read the files in the Context Files section.

### Planning by Task Size

| Size | Examples | Required |
|------|----------|----------|
| **Trivial** | Typo fix, config tweak, single-line change | Proceed directly |
| **Small** | Bug fix in one file, add simple function | Confirm approach with user before coding |
| **Medium** | Feature touching multiple files, refactoring | `/superpowers:brainstorm` then `/superpowers:write-plan` |
| **Large** | New system, architectural change, multi-component feature | `/superpowers:brainstorm` then `/superpowers:write-plan`, plus identify parallel work opportunities |

### Execution

After planning is complete, use `/superpowers:execute-plan` to implement work in controlled batches with review checkpoints.

### Pre-Execution Audit

For Medium/Large tasks, before writing any code, verify the implementation plan covers the design document:

1. Compare the design document (from brainstorming) to the implementation plan
2. Check: Does every design intention have a corresponding plan task?
3. If gaps found, present them: "The design document mentions X, but the plan doesn't cover it."
4. Resolve gaps before proceeding — add missing tasks or confirm they're intentionally deferred

This catches intent-to-plan drift at the cheapest possible point.

### Progress Check-ins

For Medium/Large tasks, check in with the developer after completing each plan step:

> "Completed: [step name]"
>
> "Summary: [2-3 sentences describing what was built]"
>
> "Still on track?"

If `~/.claude/hooks/notify.sh` exists, fire a notification before the check-in so the developer knows a response is needed:
```bash
echo '{"hook_event_name":"Notification","message":"Step complete — check-in ready","cwd":"'"$(pwd)"'"}' | ~/.claude/hooks/notify.sh
```

This is a lightweight direction check, not a formal review. The developer can:
- Confirm and continue
- Redirect if the approach has drifted
- Disable check-ins with "skip the check-ins" or similar instruction

Trivial and Small tasks skip check-ins.

### Step Reviews

For Medium/Large tasks, invoke the code-reviewer agent after completing major implementation steps — not every small change, but logical chunks like "models module complete" or "pipeline orchestrator implemented."

Step reviews provide actual code analysis, not just self-reported summaries. They catch drift from the implementation plan while there's still time to course-correct.

The final review in pre-commit still applies — step reviews are additive, not a replacement.

### Parallel Work

For Large tasks, evaluate whether work can be split across parallel tracks (separate branches/worktrees).

Parallel work is safe when **ALL** of the following are true:
- Tasks do not modify the same files
- Tasks do not modify shared interfaces or types
- Tasks do not depend on each other's output
- Tasks do not modify the same configuration

If any condition is false, work sequentially or coordinate carefully.

### Update Tracking

After planning, update BUGS_AND_TODOS.md with any new tasks identified.

### Session Resumption

At session start, check `docs/plans/` for any plan with `**Status:** In Progress` (regex: `\*\*Status:\*\* In Progress`). If found, prompt:

> "Found in-progress work: `{filename}` ({progress summary}). Resume this work?"

If yes, run `/resume-plan`. This ensures work isn't forgotten across session boundaries.

---

## Use-Case Catalog

### Purpose

Prevent code duplication by documenting existing solutions organized by business domain. When implementing new features, check the catalog first to discover if the problem has already been solved.

### Location

`docs/use-cases/`

### Structure

- **INDEX.md** — Lists all domains with descriptions
- **FORMAT.md** — Defines how to document use-cases (entry format, when to document, maintenance guidelines)
- **{domain}.md** — One file per domain containing all use-cases for that area

See `docs/use-cases/FORMAT.md` for entry format and documentation guidelines.

---

## Context Files

Read these at the start of every session:

- `VERSION_HISTORY.md` — Current version and recent changes
- `BUGS_AND_TODOS.md` — Active tasks and backlog
- `DEVELOPMENT.md` — Architectural decisions and patterns

If any of these files are missing, incomplete, or don't answer your questions about the current task, stop and ask before proceeding.

---

## Commands

| Task | Command |
|------|---------|
| Run | `python -m story_video` |
| Test | `pytest` |
| Test (skip slow) | `pytest -m "not slow"` |
| Format | `ruff format` |
| Format check | `ruff format --check` |
| Lint | `ruff check` |
| Lint fix | `ruff check --fix` |
| Install | `pip install -e ".[dev]"` |
