# Coding standards

Read during **review**, not while building. The reviewer checks the diff
against this file. Keep it for judgement calls only: anything a tool can check
(formatting, banned imports, file locations, types) belongs in `scripts/check.sh`
as a lint rule, test or check, not here.

When a reviewer misses a mistake, add a rule here or, better, a check.
When a rule stops mattering, delete it.

## Project rules

<!-- Your judgement-call rules. Examples:
- Domain terms in code match GLOSSARY.md exactly.
- Entry points (routes, handlers, jobs) orchestrate; services own the logic.
- Every new service has a test through its public interface.
- Errors are handled where they can be acted on; never swallowed silently.
-->

## Baseline smells (always on, always judgement calls)

A project rule above always wins over this list. Report these as "possible X",
never as hard failures, and skip anything tooling already catches.

- **Mysterious name**: a name that doesn't say what it does or holds. Rename it.
- **Duplicated code**: the same logic in more than one place. Extract and share.
- **Feature envy**: a function that uses another module's data more than its own. Move it.
- **Data clumps**: the same few values always passed together. Make them one type.
- **Primitive obsession**: a string or number standing in for a domain concept. Give it a type.
- **Repeated switches**: the same `switch`/`if` chain on one type in several places. Use one map or polymorphism.
- **Shotgun surgery**: one change forces edits in many files. Gather what changes together.
- **Divergent change**: one file edited for unrelated reasons. Split it.
- **Speculative generality**: options, hooks or abstractions the spec didn't ask for. Delete them.
- **Message chains**: `a.b().c().d()` that callers shouldn't depend on. Hide behind one call.
- **Middle man**: a function or class that only passes calls on. Call the target directly.
- **Swallowed errors, sleeps and retries added to make a test pass**: special cases
  hiding a design problem. Fix the cause.

The smell list is adapted from Matt Pocock's `code-review` skill (MIT), after
Fowler's *Refactoring*, chapter 3.
