# Verification Guide

This guide defines how implementation claims should be verified before documentation is updated.

---

## Completion Rule

Only mark a checklist item complete when all of the following are true:

*   Code exists for the behavior.
*   The behavior has focused tests or a documented manual verification path.
*   The relevant feature document has been updated.
*   The checklist item includes a concrete verification note.

Avoid marking a feature complete based only on a planner stub unless the roadmap item explicitly targets planning behavior.

---

## Test Commands

Run the full suite:

```bash
python3 -m unittest
```

Run a phase-specific suite:

```bash
python3 -m unittest tests.test_phase5_completion
python3 -m unittest tests.test_phase6_completion
```

Use `python3` in this environment because `python` may not be installed as a command.

---

## Verification Note Format

Checklist verification notes should be short and concrete:

```text
Verification: <module/helper> performs <observable behavior> and is covered by <test or command>.
```

For pending tasks, use:

```text
Verification target: <specific behavior that must work before completion>.
```

---

## Status Synchronization

When implementation state changes, update these files together:

*   [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md)
*   [ROADMAP.md](ROADMAP.md)
*   [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)
*   The relevant feature document, such as [ADVANCED_MEDIA_RUNTIME.md](ADVANCED_MEDIA_RUNTIME.md) or [HEADLESS_API_OPERATIONS.md](HEADLESS_API_OPERATIONS.md)

The checklist carries detailed evidence. The roadmap carries milestone-level status. The implementation status page carries the quick reader summary.

---

## Conservative Claims

Use `[Completed]` only for implemented and verified behavior. Use `[Future]` for roadmap intent, even when the design is clear. Use `[Planned]` for scoped work that is expected soon but not yet implemented.

If a feature is partially implemented, keep the roadmap status conservative and split the checklist item into completed and pending sub-items.
