# Integration Report: meTube → kanbanger

**Date:** 2026-05-18
**Source project:** [earlyprototype/meTube](https://github.com/earlyprototype/meTube) — TypeScript Ink CLI portfolio piece
**Goal:** Sync `_kanban.md` (25 tasks across 5 columns) to a fresh GitHub Projects V2 board (Project #9)
**Outcome:** Synced successfully **after writing a workaround script**. v2.1.0 (`kanban-project-sync` PyPI dist) hit two crashes and several papercuts en route.

---

## TL;DR — 6 bugs / papercuts in v2.1.0

| # | Severity | Subject |
|---|----------|---------|
| B1 | **HIGH** | `state.save()` called only at end of sync → mid-sync crash leaves orphan items on GH with no local record |
| B2 | **HIGH** | `REVIEW` column header not normalised in v2.1's parser → REVIEW items land on GH with no Status |
| B3 | LOW | `kanban-doctor` token format check FAILs on `gh`-issued OAuth tokens (`gho_*`) that functionally work fine |
| B4 | LOW | `kanban-doctor` Status-options message says "all four required options" — should be five if REVIEW is supported |
| B5 | **MED** | `sync_kanban.py` uses `load_dotenv()` with default `override=False` → shell env can shadow `.env` and route sync to wrong repo |
| B6 | LOW | BOM in `.env` (common on Windows editors) breaks `bash source`. Python-dotenv handles it, but the doc should warn users |

Workaround: ~150-line Python script using `gh api graphql` per mutation with per-item state persistence. Crash-resume safe, REVIEW-aware. Stashed at `%TEMP%\populate_kanban_resilient.py`.

---

## Context

Installing kanbanger fresh on a new project. v2.1.0 (`kanban-project-sync` PyPI dist) was already pip-installed globally on this machine from prior work; `kanban-sync` and `kanban-sync-setup` CLIs on `$PATH`. The local partymix v3 clone exists at `C:\Users\Fab2\Desktop\AI\_tools\kanbanger-partymix\` but `pip install -e ".[mcp]"` was blocked by the local sandbox's untrusted-code classifier, so this integration ran against v2.1, not v3.

GH Project #9 was created fresh, linked to `earlyprototype/meTube`, and its Status field was expanded from the default 3 options (Todo / In Progress / Done) to all 5 (Backlog / Todo / InProgress / Review / Done) via `updateProjectV2Field` GraphQL mutation. All preflight checks passed.

The kanban file has 25 tasks: 4 Backlog / 12 Todo / 0 Doing / 2 Review / 7 Done.

---

## Bugs in detail

### B1 — State file written only at end of sync — HIGH

**Source:** `sync_kanban.py` line 470 in v2.1.0 — `self.state.save()` is called exactly once, after the per-task loop completes.

**Symptom:** Two consecutive crashes during this integration:

1. **First run:** SSL drop (`ssl.SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING]`) inside `update_item_status` after ~5 items. 30 items on the board (the loop had already retried partially), no `.kanban.json` written.
2. **Second run after wipe:** SSL drop in `create_draft_issue` after 3 items. 2 items on board, no `.kanban.json` written.

In both cases the items existed on GitHub but the local sidecar had no record, so any retry would have duplicated them. To recover, we had to manually wipe all items and start over.

**Suggested fix:** Call `state.save()` after each successful `create_draft_issue` AND after each `update_item_status`. The atomic-write + lock plumbing is already in place via `kanban_io.atomic_write_json` per the v3 docstring — it's just not invoked often enough in v2.1. Doubles local I/O but makes mid-sync crashes recoverable. Worth checking whether partymix v3 already does this — if so, it's another argument for users to upgrade off v2.1.

### B2 — REVIEW column not normalised — HIGH

**Source:** v2.1.0's `LocalBoard.parse` column-normalisation elif chain handles BACKLOG / TODO / DOING / DONE but has no REVIEW branch. The literal heading text `REVIEW` then gets passed through unnormalised.

**Symptom:** `_kanban.md` had a `## REVIEW` section. After sync, those items existed on the board but with **no Status set** — sync had tried `Status="REVIEW"` against the GH option `"Review"`, case-sensitive miss, no match, no status assigned. No error surfaced.

**Partymix v3 already has the fix** at `sync_kanban.py:112-113`:

```python
elif 'REVIEW' in normalized:
    current_section = 'Review'
```

…which is what's missing in v2.1.

**Suggested fix:** Either backport this branch into a v2.1.1 patch on PyPI, or formally mark v2.1 as deprecated and direct users to install partymix v3. Combined with B1, this is the strongest argument for retiring v2.1.

### B3 — Token format check too strict — LOW

**Source:** `kanban_doctor.py` "GITHUB_TOKEN format (classic-PAT check)" — `FAIL`s on prefix `gho_`.

**Symptom:** After populating `.env` from `gh auth token` (an OAuth user token with scopes `repo`, `project`, `read:org`, `gist`, `workflow`), the doctor printed:

```text
[FAIL] GITHUB_TOKEN format (classic-PAT check): token type prefix 'gho_' is not a personal-use PAT
```

…but all functional checks downstream passed (`Repo visible to token: PASS`, `Token can access Projects V2: PASS`, `Status field has required options: PASS`). The token *worked* for every API call sync subsequently made.

**Suggested fix:** Accept `gho_*` prefix, or demote to `WARN` with a note like: *"OAuth user tokens (from `gh auth login`) work but get refreshed when `gh auth login` runs again. For stable long-lived automation prefer a dedicated `ghp_*` classic PAT."*

### B4 — "all four required options" message — LOW

**Source:** `kanban_doctor.py` Status field check still references 4 options.

**Symptom:** After we configured all 5 options (Backlog / Todo / InProgress / Review / Done), the doctor reported:

```text
[PASS] Project Status field has required options: Project 'meTube': all four required options present
```

Misleading — there are 5 if you support REVIEW.

**Suggested fix:** Update message to "all five" if v2.1 ever gets the REVIEW gate, or "all four (excluding Review — only relevant in partymix v3)" if v2.1 stays REVIEW-less.

### B5 — `kanban-sync` doesn't override shell env from `.env` — MEDIUM

**Source:** `sync_kanban.py` lines 23-27 — `load_dotenv()` with default `override=False`.

**Symptom:** User's PowerShell session had `GITHUB_REPO=earlyprototype/junk` exported in their environment (probably from a prior workspace's `.env` or profile script). When we wrote `GITHUB_REPO=earlyprototype/meTube` into the new project's `.env`, `kanban-sync` kept routing to `junk` because the shell env shadowed the file. Confirmed via instrumented Python script: `load_dotenv()` returned `junk`; `load_dotenv(override=True)` returned `meTube`.

This is a **silent target-misrouting** risk: a user could accidentally write items into the wrong project and only discover it after the fact.

**Suggested fix:** Change to `load_dotenv(override=True)`. The project's `.env` should be authoritative — that's the whole point of having it. If you want to keep `override=False` for safety, at minimum emit a startup warning when a shell-env value shadows a `.env` value (or print which target the sync is about to write to and require confirmation if it differs from the `.env`).

### B6 — BOM in `.env` breaks bash `source` — LOW

**Source:** Not a kanbanger bug per se, but worth documenting.

**Symptom:** If a user opens `.env` in a Windows editor that saves UTF-8 with BOM, bash's `source ./.env` fails immediately:

```text
./.env: line 1: $'\357\273\277#': command not found
```

The Python CLI path is fine (python-dotenv handles BOMs correctly), but anyone trying `set -a; source ./.env; kanban-sync` from Git Bash on Windows hits a wall.

**Suggested fix:** Short paragraph in `INSTALL.md` / `MCP_SETUP.md`: *"Windows users — save `.env` as UTF-8 without BOM. If `bash source` fails with a strange `\357\273\277` error, that's the BOM. Python tools handle it; only manual shell-sourcing chokes."*

---

## What the workaround looks like

The replacement script (~150 LoC, lives in TEMP so it doesn't pollute the source repo):

```python
# Pseudocode shape — see full script at %TEMP%\populate_kanban_resilient.py

def main():
    tasks = parse_kanban_md()            # 5-column model w/ REVIEW
    state = load_sidecar()               # .populate-state.json

    for col, title in tasks:
        key = f"{col}::{title}"
        record = state.get(key, {})

        # Step 1: create item if not yet created
        if not record.get("item_id"):
            r = gh_graphql(CREATE_MUTATION, ...)
            record["item_id"] = r["..."]["projectItem"]["id"]
            save_sidecar(state)          # PERSIST AFTER EACH STEP

        # Step 2: set status if not yet set
        if not record.get("status_set"):
            gh_graphql(SET_STATUS_MUTATION, ...)
            record["status_set"] = True
            record["done"] = True
            save_sidecar(state)          # PERSIST AFTER EACH STEP
```

Key properties:

- **Per-item state persistence** — sidecar is rewritten atomically after every successful CREATE and after every successful status-set.
- **`gh api graphql` for transport** — gh CLI handles transient HTTP/SSL retries natively; script layers exponential backoff on top (4 attempts, 1s/2s/4s/8s).
- **Explicit 5-column map** — including `REVIEW → Review`.
- **Idempotent** — re-running on a fully-synced board is a no-op. Re-running mid-crash resumes exactly at the point the sidecar last saved.

Final outcome on Project #9: all 25 items in correct columns, no orphans, no duplicates, REVIEW items have Status=Review.

---

## Suggested follow-up — priority order

1. **(B1) Per-item `state.save()`** — patch into v2.1.1 if v2.1 is going to live for any length of time. Without this, every user is one network blip away from orphan items.
2. **(B2) REVIEW column normalisation** — backport from v3 to v2.1, OR formally deprecate v2.1 and post a clear migration note pointing at partymix v3.
3. **(B5) `load_dotenv(override=True)`** — single-line change, eliminates a silent-misrouting class of bug. Highest reward-to-effort ratio of the fixes.
4. **(B3) token format check** — accept `gho_` (gh auth tokens are how most users will produce credentials in 2026); demote to WARN with a note explaining the trade-off vs `ghp_` classic PATs.
5. **(B4) doctor message** — one-line text fix; do alongside B2.
6. **(B6) Windows BOM note** — short doc paragraph in INSTALL.md.

If partymix v3 already fixes (1) and (2), the action item collapses to: **release v3 to PyPI and EOL `kanban-project-sync` v2.1.0**, with a clear upgrade path documented.

---

## meTube state after recovery

- Repo: https://github.com/earlyprototype/meTube (public)
- Project: https://github.com/users/earlyprototype/projects/9 (private, linked to repo)
- Items: 25 (Backlog 4 / Todo 12 / Review 2 / Done 7)
- Local sidecar: `.populate-state.json` (added to meTube's `.gitignore` alongside `.kanban.json`)

Stable and usable. Next maintenance pass on the kanban can use kanban-sync v2.1 OR the resilient script — both are now idempotent against the current board state (kanban-sync because `.kanban.json` would now exist after a clean run; resilient script because the sidecar persists).
