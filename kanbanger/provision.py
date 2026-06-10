"""
kanbanger.provision — shared, idempotent project-provisioning helpers.

Single source of truth for "make a workspace ready for kanbanger". Both the
in-MCP `setup_project` tool (kanbanger.tools) AND the deprecated external
`scripts/setup-venv.py` import from here, so the two paths can never drift
(ADR 0002, issue #15 step 3).

Provisioning is the LIGHTWEIGHT, per-project half (distinct from INSTALL, which
is a single global `pipx install` — see ADR 0002). It writes only project-local
files and is safe to re-run:

  * `_kanban.md`        — the board, canonical 5-column schema, with a stable
                          board key minted into it (ADR 0002 collision-proof
                          binding). Scaffolded only if absent. An existing
                          board is NEVER clobbered, with ONE sanctioned
                          additive exception: a board lacking a key gets the
                          single `<!-- kanbanger:board-id: ... -->` marker
                          comment inserted under its title — every other byte
                          preserved.
  * `CLAUDE.md`         — the always-loaded agent touchpoint stanza (and
                          `AGENTS.md` likewise) telling agents to drive the
                          board via the MCP tools and never hand-edit it.
  * `.mcp.json`         — wires the project to the GLOBAL `kanbanger-mcp`
                          command, with EMPTY GitHub-sync placeholders.
  * `.gitignore`        — keeps a stray `.venv/` out of version control.

NOTE on secrets: the GitHub-sync slots (GITHUB_TOKEN / GITHUB_REPO /
GITHUB_PROJECT_NUMBER) are written ONLY as `${VAR:-}` shell-style placeholders
in `.mcp.json`. No real secret is ever written by this module; the user fills
them into their environment (or a local, gitignored `.env` / shell profile).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from kanban_io import (
    atomic_write_text,
    extract_board_key,
    insert_board_key,
    kanban_lock,
    mint_board_key,
)

# ---------------------------------------------------------------------------
# Constants (single home — previously duplicated in scripts/setup-venv.py)
# ---------------------------------------------------------------------------

GITIGNORE_ENTRY = ".venv/"
GITIGNORE_HEADER = (
    "# Local virtualenv (if any) — kanbanger installs globally; see ADR 0002"
)
CLAUDE_MD_START = "<!-- kanbanger:start -->"
CLAUDE_MD_END = "<!-- kanbanger:end -->"

KANBAN_FILENAME = "_kanban.md"
MCP_JSON_FILENAME = ".mcp.json"
CLAUDE_MD_FILENAME = "CLAUDE.md"
AGENTS_MD_FILENAME = "AGENTS.md"
GITIGNORE_FILENAME = ".gitignore"

# The supported install path is a single global `kanbanger-mcp` on PATH
# (pipx/pip). Provisioning wires .mcp.json to THAT command, not a per-project
# venv interpreter (ADR 0002).
GLOBAL_MCP_COMMAND = "kanbanger-mcp"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ProvisionResult:
    """Structured outcome of a provisioning run.

    `created` / `updated` / `already_present` / `skipped` hold short
    human-readable notes (one per provisioned concern). `summary()` renders
    the whole thing as a plain-text block suitable for an MCP tool return or
    a console print.
    """

    project_dir: str
    created: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    already_present: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Provisioned kanbanger in: {self.project_dir}", ""]
        if self.created:
            lines.append("Created:")
            lines.extend(f"  + {item}" for item in self.created)
        if self.updated:
            lines.append("Updated:")
            lines.extend(f"  ~ {item}" for item in self.updated)
        if self.already_present:
            lines.append("Already present (left as-is):")
            lines.extend(f"  = {item}" for item in self.already_present)
        if self.skipped:
            lines.append("Skipped:")
            lines.extend(f"  - {item}" for item in self.skipped)
        lines.append("")
        lines.append(
            "GitHub sync is OFF until you fill the placeholders in "
            f"{MCP_JSON_FILENAME} (GITHUB_TOKEN / GITHUB_REPO / "
            "GITHUB_PROJECT_NUMBER) via your environment or a local, "
            "gitignored .env — no secrets are stored in the repo."
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Path / formatting helpers
# ---------------------------------------------------------------------------


def to_forward_slashes(p) -> str:
    return str(p).replace("\\", "/")


# ---------------------------------------------------------------------------
# .mcp.json
# ---------------------------------------------------------------------------


def build_mcp_config(project_dir: Path) -> dict:
    """Build a project `.mcp.json` that targets the GLOBAL kanbanger install.

    Post-ADR-0002 there is no per-project venv to pin to, so the command is the
    ``kanbanger-mcp`` console script installed globally (pipx/pip) and resolved
    on PATH — exactly how any other MCP server is wired.

    The GitHub-sync env slots are EMPTY ``${VAR:-}`` placeholders: the value is
    taken from the user's environment at launch and defaults to empty. NEVER
    write a real token here.
    """
    project_path_fwd = to_forward_slashes(project_dir)
    return {
        "mcpServers": {
            "kanbanger": {
                "command": GLOBAL_MCP_COMMAND,
                "args": [],
                "env": {
                    "KANBANGER_WORKSPACE": "${KANBANGER_WORKSPACE:-"
                    + project_path_fwd
                    + "}",
                    # Sync-config slots — empty placeholders only. Fill via the
                    # environment / a local .env; do not paste secrets here.
                    "GITHUB_TOKEN": "${GITHUB_TOKEN:-}",
                    "GITHUB_REPO": "${GITHUB_REPO:-}",
                    "GITHUB_PROJECT_NUMBER": "${GITHUB_PROJECT_NUMBER:-}",
                },
            }
        }
    }


def ensure_mcp_json(project_dir: Path, result: ProvisionResult) -> None:
    """Write `.mcp.json` if absent. If present, leave it untouched.

    Unlike the old installer (which backed up and overwrote), the provisioning
    contract is "don't clobber what the project already has". An existing
    `.mcp.json` is reported as already-present so the user can reconcile it by
    hand if needed.
    """
    mcp_json = project_dir / MCP_JSON_FILENAME
    if mcp_json.exists():
        result.already_present.append(
            f"{MCP_JSON_FILENAME} (left as-is; verify it targets "
            f"`{GLOBAL_MCP_COMMAND}` with empty GitHub-sync slots)"
        )
        return
    config = build_mcp_config(project_dir)
    mcp_json.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    result.created.append(
        f"{MCP_JSON_FILENAME} (targets global `{GLOBAL_MCP_COMMAND}`; "
        "empty GitHub-sync placeholders)"
    )


# ---------------------------------------------------------------------------
# .gitignore
# ---------------------------------------------------------------------------


def ensure_gitignore_has_venv(project_dir: Path, result: ProvisionResult | None = None) -> None:
    """Idempotently ensure `.venv/` is gitignored.

    A stray local venv is harmless if you never make one, but if you do, it
    should stay out of version control (global install is the supported path —
    ADR 0002).
    """
    gitignore = project_dir / GITIGNORE_FILENAME
    block = f"\n{GITIGNORE_HEADER}\n{GITIGNORE_ENTRY}\n"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if GITIGNORE_ENTRY in content:
            if result is not None:
                result.already_present.append(f"{GITIGNORE_FILENAME} (.venv/ already ignored)")
            return
        sep = "" if content.endswith("\n") else "\n"
        gitignore.write_text(content + sep + block, encoding="utf-8")
        if result is not None:
            result.updated.append(f"{GITIGNORE_FILENAME} (added {GITIGNORE_ENTRY})")
    else:
        gitignore.write_text(block.lstrip("\n"), encoding="utf-8")
        if result is not None:
            result.created.append(f"{GITIGNORE_FILENAME} (with {GITIGNORE_ENTRY})")


# ---------------------------------------------------------------------------
# CLAUDE.md / AGENTS.md touchpoint
# ---------------------------------------------------------------------------


def build_claude_md_block(project_dir: Path) -> str:
    """The Kanbanger onboarding stanza injected into a project's CLAUDE.md.

    This is the always-loaded, pre-launch touchpoint. The server's own
    ``instructions`` string carries the same intent, but an LLM can't see it
    until the server is already running -- so in a project where the MCP isn't
    loaded yet, this stanza is the only thing telling the agent to (a) drive
    the board through the MCP tools rather than hand-editing ``_kanban.md``,
    (b) keep the board project-scoped, and (c) how to recover/provision when
    the board or MCP config is missing (e.g. on a fresh clone).
    """
    return f"""{CLAUDE_MD_START}
## Kanbanger: task board for this project

This project tracks work on a Kanban board managed by the **Kanbanger MCP
server**. The board lives at `_kanban.md` in the project root and is
**project-scoped** -- configured here via `.mcp.json`, not globally.
The board belongs to this project.

**For AI agents:**
- **Always use the Kanbanger MCP tools** (`list_tasks`, `add_task`, `move_task`,
  `delete_task`, `sync_to_github`, `get_sync_status`) to read or change the
  board. **Never hand-edit `_kanban.md`** -- direct edits bypass validation,
  locking, and atomic writes and will eventually corrupt the board or its
  GitHub sync.
- On first contact, read the `kanban://current-board` resource before acting.
- **REVIEW gates DONE.** AI-completed work goes to REVIEW via `propose_done`,
  never straight to DONE; a human approves REVIEW -> DONE via `approve_done`.
  Never move your own work directly to DONE.

**If the Kanbanger tools aren't available** in this session, kanbanger may not
be installed globally, or this project may not be provisioned yet (no
`_kanban.md` / `.mcp.json`). Install once
(`pipx install git+https://github.com/earlyprototype/kanbanger-partymix.git`),
then provision this project by calling the MCP `setup_project` tool (or, for
CLI parity, run `kanbanger init` in the project root), and restart the session.
{CLAUDE_MD_END}
"""


def _upsert_touchpoint(target: Path, block: str) -> str:
    """Idempotently add (or refresh) the marker-delimited block in `target`.

    Returns one of: "created", "refreshed", "appended", "unchanged" — so the
    caller can record the right note.

    - File absent          -> create it with the stanza.            ("created")
    - File present, no tag  -> append the stanza (content preserved). ("appended")
    - File present, tagged  -> replace the block between the markers; a re-run
      after a partymix upgrade refreshes the stanza without duplicating.
      ("refreshed" if the text changed, else "unchanged")
    """
    if not target.exists():
        target.write_text(block, encoding="utf-8")
        return "created"

    content = target.read_text(encoding="utf-8")
    start_idx = content.find(CLAUDE_MD_START)
    if start_idx != -1:
        end_idx = content.find(CLAUDE_MD_END, start_idx + len(CLAUDE_MD_START))
        if end_idx != -1:
            end_idx += len(CLAUDE_MD_END)
            new_content = content[:start_idx] + block.rstrip("\n") + content[end_idx:]
            if new_content != content:
                target.write_text(new_content, encoding="utf-8")
                return "refreshed"
            return "unchanged"
        # Orphan start marker (truncated/edited file): replace from that point.
        new_content = content[:start_idx] + block
        target.write_text(new_content, encoding="utf-8")
        return "refreshed"

    sep = "" if content.endswith("\n") else "\n"
    target.write_text(content + sep + "\n" + block, encoding="utf-8")
    return "appended"


def ensure_claude_md_has_kanbanger(project_dir: Path, result: ProvisionResult | None = None) -> None:
    """Idempotently add (or refresh) the Kanbanger stanza in <project>/CLAUDE.md."""
    claude_md = project_dir / CLAUDE_MD_FILENAME
    block = build_claude_md_block(project_dir)
    outcome = _upsert_touchpoint(claude_md, block)
    if result is None:
        return
    note = f"{CLAUDE_MD_FILENAME} (kanbanger touchpoint)"
    if outcome == "created":
        result.created.append(note)
    elif outcome in ("refreshed", "appended"):
        result.updated.append(f"{note} — {outcome}")
    else:  # unchanged
        result.already_present.append(f"{note} (already up to date)")


def ensure_agents_md_has_kanbanger(project_dir: Path, result: ProvisionResult | None = None) -> None:
    """Mirror the touchpoint into AGENTS.md, but only if AGENTS.md already exists.

    AGENTS.md is the cross-tool agent-guidance convention (Cursor, etc.). We do
    NOT create one from scratch — that would impose a file the project may not
    want — but if the project already keeps an AGENTS.md, agents reading it
    should get the same "drive the board via the MCP, never hand-edit"
    direction. CLAUDE.md is always (re)written; AGENTS.md is augmented only
    when present.
    """
    agents_md = project_dir / AGENTS_MD_FILENAME
    if not agents_md.exists():
        if result is not None:
            result.skipped.append(
                f"{AGENTS_MD_FILENAME} (not present — not created; the CLAUDE.md "
                "touchpoint covers agents. Add the stanza here too if you keep one.)"
            )
        return
    block = build_claude_md_block(project_dir)
    outcome = _upsert_touchpoint(agents_md, block)
    if result is None:
        return
    note = f"{AGENTS_MD_FILENAME} (kanbanger touchpoint)"
    if outcome == "created":
        result.created.append(note)
    elif outcome in ("refreshed", "appended"):
        result.updated.append(f"{note} — {outcome}")
    else:
        result.already_present.append(f"{note} (already up to date)")


# ---------------------------------------------------------------------------
# _kanban.md board scaffold
# ---------------------------------------------------------------------------


def build_kanban_board(project_name: str) -> str:
    """Return the canonical 5-column board markdown for a new project.

    Schema order is the canonical BACKLOG -> TODO -> DOING -> REVIEW -> DONE.
    Each column carries one placeholder line describing its role so a human (or
    agent) sees the intended workflow immediately. This mirrors the schema in
    the server's `instructions` string and the `kanban_workspace` test fixture.
    """
    return f"""# {project_name} Kanban

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
"""


def _default_project_name(project_dir: Path) -> str:
    name = project_dir.name
    return name if name else "Project"


def scaffold_kanban_board(project_dir: Path, result: ProvisionResult | None = None) -> None:
    """Create `_kanban.md` if absent, and ensure it carries a minted board key.

    Board-content rules (ADR 0002, issue #15 step 4 — collision-proof
    binding):

      * Board ABSENT  -> scaffold the canonical 5-column schema with a
        freshly minted board key (`<!-- kanbanger:board-id: ... -->`)
        directly under the title. Reported as created.
      * Board PRESENT, NO key -> the ONE sanctioned modification of an
        existing board: additively insert the single board-key marker
        comment under the title. Every other byte is preserved (read raw,
        no newline translation, atomic write under the kanban lock).
        Reported as updated ("minted board key").
      * Board PRESENT, key already minted -> untouched byte-for-byte,
        reported as already-present.

    The WHOLE check-then-act sequence runs under the kanban lock: the board
    may be live under a running MCP server, and two concurrent provisions
    must not both see "no board" and have the second clobber the first's
    minted key (TOCTOU). Existence is therefore checked INSIDE the critical
    section — if the board appears while we waited for the lock, we fall
    through to the existing-board minting logic instead of overwriting it.

    Idempotent: the key is minted at most once, so re-runs are no-ops and
    the key is stable for the board's lifetime (it IS the board's identity
    — see kanbanger.binding).
    """
    board_path = project_dir / KANBAN_FILENAME
    with kanban_lock(str(project_dir)):
        if not board_path.exists():
            board = build_kanban_board(_default_project_name(project_dir))
            board_key = mint_board_key()
            board_path.write_text(insert_board_key(board, board_key), encoding="utf-8")
            if result is not None:
                result.created.append(
                    f"{KANBAN_FILENAME} (canonical 5-column board: "
                    "BACKLOG -> TODO -> DOING -> REVIEW -> DONE; "
                    f"board key {board_key} minted)"
                )
            return

        # Existing board: mint the key additively if (and only if) it is
        # missing. Raw bytes in, raw bytes out (newline="") so the original
        # content round-trips exactly regardless of CRLF/LF style.
        text = board_path.read_bytes().decode("utf-8")
        existing_key = extract_board_key(text)
        if existing_key is not None:
            if result is not None:
                result.already_present.append(
                    f"{KANBAN_FILENAME} (board already exists — NOT modified; "
                    f"board key already minted)"
                )
            return
        board_key = mint_board_key()
        atomic_write_text(
            str(board_path), insert_board_key(text, board_key), newline=""
        )
    if result is not None:
        result.updated.append(
            f"{KANBAN_FILENAME} (minted board key {board_key} — one marker "
            "comment added under the title; all other content preserved)"
        )


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def provision_project(
    project_dir,
    *,
    scaffold_board: bool = True,
    write_mcp_json: bool = True,
    write_gitignore: bool = True,
    write_claude_md: bool = True,
    write_agents_md: bool = True,
) -> ProvisionResult:
    """Idempotently provision `project_dir` for kanbanger.

    Runs each enabled step and returns a `ProvisionResult` describing what was
    created vs already present. Safe to re-run: a second call on an already
    provisioned project is a no-op (everything reported as already-present /
    up to date).

    The flags exist so the deprecated `scripts/setup-venv.py` can keep its
    `--no-*` switches without duplicating logic. The in-MCP `setup_project`
    tool calls this with defaults.

    Raises FileNotFoundError if `project_dir` is not an existing directory —
    provisioning targets a real workspace, it does not create the workspace
    root itself.
    """
    project_path = Path(project_dir).resolve()
    if not project_path.is_dir():
        raise FileNotFoundError(f"project directory not found: {project_path}")

    result = ProvisionResult(project_dir=to_forward_slashes(project_path))

    if scaffold_board:
        scaffold_kanban_board(project_path, result)
    if write_mcp_json:
        ensure_mcp_json(project_path, result)
    if write_gitignore:
        ensure_gitignore_has_venv(project_path, result)
    if write_claude_md:
        ensure_claude_md_has_kanbanger(project_path, result)
    if write_agents_md:
        ensure_agents_md_has_kanbanger(project_path, result)

    return result
