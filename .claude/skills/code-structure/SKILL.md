---
name: code-structure
description: Use while building a feature, when deciding where logic belongs, when two flows duplicate the same operation, or before adding a new helper. Encodes this project's architecture so generated code is easy to review. EDIT THIS FILE to match your own architecture.
---

# Code Structure

> This is a template. The default below is a service-layer style. Replace it
> with the structure you want to read in review. The repo's existing
> architecture always wins over this default.

## Rules

1. **Search before writing.** Grep for an existing function that does the job.
   Extend or reuse it. Agents duplicate code by default; don't.
2. **Entry points orchestrate.** Handlers, actions, routes and jobs decide *what*
   and *when*. They validate input, call services, shape the response. No
   business logic inline.
3. **Services own the how.** One module per domain operation, with explicit
   inputs and a structured return value. No hidden globals, no reaching into
   request objects.
4. **Extract on the second use.** When two flows share mechanics, move the shared
   part into a service. Don't extract on the first use.
5. **Small diffs.** Don't refactor unrelated code in a feature PR.

## Where things go

<!-- Fill in your real layout, e.g.:
- src/actions/   entry points
- src/services/  reusable operations
- src/lib/       pure helpers
- tests mirror src/
-->

## Before finishing

- No duplicated logic you could have reused.
- Names say what the function does.
- Each new service has a test.
