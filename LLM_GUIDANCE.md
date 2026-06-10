# LLM Guidance — Using Kanbanger

Kanbanger is an **MCP server**. If you are an AI assistant in a project that has
Kanbanger configured, you manage the board by **calling the MCP tools** — not by
editing `_kanban.md` by hand, and not by shelling out to a CLI.

This is the single most important rule, so it comes first:

> **Always use the Kanbanger MCP tools. Never hand-edit `_kanban.md`.**
> Direct edits bypass the server's validation, file locking, and atomic writes,
> and they desync the board from its GitHub Project. The tools exist precisely so
> you don't have to parse or rewrite the markdown yourself.

## The board is project-scoped

The board is `<workspace>/_kanban.md` for the **current project** — where
`<workspace>` is the `KANBANGER_WORKSPACE` env var, or the project's working
directory if that's unset. The kanbanger **install** is global (one
`kanbanger-mcp` on PATH), but the **board** is per-project, wired
by each project's own `.mcp.json`. There is no single global board. The board
belongs to the project you're in.

## First contact

Before doing anything, read the `kanban://current-board` resource (or check for
`_kanban.md` in the workspace) to see the current state.

If `_kanban.md` does **not** exist, Kanbanger isn't set up in this project yet.
Don't silently create it — tell the user and ask. If they agree, call the
`setup_project` tool, which provisions the project idempotently (canonical
5-column board, `.mcp.json`, agent touchpoint) — see
[Board format](#board-format-for-reference) below for the schema it scaffolds.

## The tools

| Tool | Use it to |
|------|-----------|
| `list_tasks(column?)` | Read the board (optionally filter to one column) |
| `add_task(title, column, description?)` | Add a task |
| `move_task(title, from_column, to_column)` | Move a task between columns |
| `delete_task(title, column)` | Remove a task |
| `propose_done(title)` | Move an AI-completed task to REVIEW (see gate below) |
| `approve_done(title)` | Approve a REVIEW task to DONE (human action) |
| `reject_review(title, reason)` | Send a REVIEW task back with feedback |
| `sync_to_github(dry_run?)` | Push the board to its GitHub Project |
| `get_sync_status()` | Check sync state |
| `setup_project()` | Provision this workspace (board scaffold, `.mcp.json`, touchpoints) — idempotent |

Read-only resources, always available: `kanban://current-board`,
`kanban://stats`, `kanban://sync-status`.

## The REVIEW gate — AI never marks its own work DONE

The board has five columns: **BACKLOG → TODO → DOING → REVIEW → DONE.**

REVIEW is the AI/human handoff gate. When you finish a task:

1. Call `propose_done(title)` — this moves it to **REVIEW**, not DONE.
2. A human (or a designated reviewer) verifies and calls `approve_done(title)`
   → **DONE**, or `reject_review(title, reason)` to send it back for rework.

**Never move your own work straight to DONE.** This contract is enforced by the
tools, not just convention.

## Board format (for reference)

You rarely write this by hand — `add_task` does it for you — but when creating a
board for the first time, use this exact shape:

```markdown
# <Project Name> Kanban

## BACKLOG
*   [ ] Future / unprioritised work

## TODO
*   [ ] Ready to start, prioritised

## DOING
*   [ ] In progress (keep to 1-3 items)

## REVIEW
*   [ ] AI-completed work awaiting human approval

## DONE
*   [x] Completed, human-approved work
```

Format rules the parser enforces:

- Columns are level-2 headers (`## `).
- Tasks are `*   [ ]` (asterisk + three spaces + checkbox); `[x]` only in DONE.
- Column names (case-insensitive): `BACKLOG`, `TODO` / `TO DO`,
  `DOING` / `IN PROGRESS`, `REVIEW`, `DONE` / `COMPLETE`.
- Keep titles unique — duplicate titles break sync and exact-title tool matching.

## Writing good tasks

- **Specific and actionable:** "Implement user authentication API", not "Work on auth".
- One clear deliverable per task; break big tasks down before adding them.
- Keep DOING to 1-3 items so focus stays real.
- If a title is ambiguous, confirm with the user before adding.

## GitHub sync

Preview with `sync_to_github(dry_run=True)`, then push with `sync_to_github()`.
The linked GitHub Project's Status field must have all five options
(`Backlog` / `Todo` / `InProgress` / `Review` / `Done`, case-sensitive), or
REVIEW items land with no status. Sync is one-way: local markdown → GitHub.

## If the tools aren't there

If you don't see the Kanbanger tools in this session but the project has a
`.mcp.json` referencing kanbanger, the global install is probably missing on
this machine. Tell the user to install it once
(`pipx install git+https://github.com/earlyprototype/kanbanger-partymix.git`)
and restart the session. If `.mcp.json` itself is missing, the project isn't
provisioned yet — tell the user to run `kanbanger init` from the project root
(or call `setup_project` once the server is available).
**Don't fall back to hand-editing the board.**
