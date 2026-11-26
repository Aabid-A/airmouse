---
name: to-issues
description: Use when a plan, idea or conversation needs to become trackable work. Splits it into small GitHub issues, each with acceptance criteria, labels and blocking links, then creates them after the user confirms the list.
---

# To Issues

Turn a plan into issues an agent can pick up one at a time.

## Steps

0. **Start from a spec when there is one** (an issue labelled `spec` from
   `to-spec`). Link it from every issue ("Part of #<spec>") and cover its user
   stories between them. Use `GLOSSARY.md` terms. If the work is big and has no
   spec, suggest `grill` then `to-spec` first.
1. **Draft the list first, don't create anything yet.** Break the plan into
   vertical slices: each one delivers something that works end to end, not a
   layer ("engine rules", not "all the models"). Aim for issues that fit one PR.
2. For each issue write:
   - **Title:** a verb phrase ("Add vote counting to the game engine").
   - **Why:** one or two sentences.
   - **Acceptance criteria:** a checklist of observable results. Include the
     check or evidence that proves it (a test, a screenshot, a command output).
   - **Blocked by:** other issues in this list, by title for now.
   - **Context** (lets `dispatch` route it and keeps workers from colliding):
     `Type:` feature, ui, bug, refactor or docs; `Files:` paths or folders
     likely to change (comma-separated; leave empty only if unknown, and it
     will then run alone); glossary terms, ADRs, design references and checks
     that apply.
   - **Labels:** `ready` if it can start now, `blocked` if it waits; plus a type
     such as `enhancement`, `bug` or `documentation`.
3. **Show the whole list to the user and wait for a yes.** Creating issues is
   visible outside this machine. Never create without confirmation.
4. **Create** with `gh issue create` (title, body, labels). Create blockers
   first so you have their numbers, then write `Blocked by #n` into dependent
   issues. Make missing labels with `gh label create` (`spec`, `ready`,
   `in-progress`, `needs-review`, `blocked`, `human-verified`).
5. Report the issue numbers and links, and which one to start with.

## Rules

- Small beats complete. If an issue needs more than one PR, split it.
- No vague criteria ("works well"). Each item should be checkable by someone else.
- Put design intent in the issue (reference file, `STYLE.md`) so the agent doesn't guess.
- Don't edit or close issues you didn't create unless asked.
- No `gh`? Use the GitHub MCP tools. If neither is available, stop and say so.
- Label an issue `human-verified` when a criterion needs the user to check it
  by hand (hardware, feel, a live demo). Its PRs then use `Refs #n`, not `Closes`.
