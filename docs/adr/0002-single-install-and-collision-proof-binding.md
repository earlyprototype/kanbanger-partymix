# 2. Single global install, in-MCP provisioning, and collision-proof board binding

Date: 2026-06-09

## Status

Accepted

## Context

The v3 server (this repo) reused the importable module name `kanbanger_mcp` from
the frozen v2 archive. Two installs exposing the same module name shadow each
other on `sys.path`, producing silent "wrong version loads" / "server not
connected" failures.

The mitigation to date — a per-project `.venv` plus `scripts/setup-venv.py` run in
every project — fixes the collision but imposes per-project install friction that
no other MCP server requires. For an adoption-focused tool, that friction is a
liability, not a feature.

The collision is self-inflicted: a separate successor product kept the
predecessor's module name. The root fix is a rename, not a per-project workaround.

The "global vs per-project" question was confused because `setup-venv.py` fused two
unrelated jobs — installing the software and provisioning a board.

## Decision

Separate four concerns and let each sit where it belongs:

1. **Install** — once, globally (`pipx` / `uv tool` / `pip`). Like any MCP server.
2. **Register** — once at user scope, or via an optional committed `.mcp.json` that
   points at the single install.
3. **Provision** — per project, lightweight "onboard this board": scaffold
   `_kanban.md`, wire the GitHub sync target, drop the agent touchpoint. Delivered
   in-MCP (an `init` / first-contact flow), not an external installer.
4. **Bind** — at runtime, auto-detect which board via a collision-proof key.

Concrete choices:

- **Rename the importable module `kanbanger_mcp` -> `kanbanger`.** Confirmed free on
  PyPI, GitHub, and as a module (2026-06-09). Distinct from the frozen v2
  `kanbanger_mcp`, so the collision becomes impossible.
- **Drop per-project venvs.** Install once.
- **Board binding = derived discovery + minted ID.** Discover by walking up to the
  nearest `_kanban.md` (zero-config); take identity from a stable ID minted into the
  board at provision time — not the folder path, which breaks on move/clone.
- **Observability:** extend `kanban-doctor` to print
  `workspace resolved = X -> board = Y -> key = Z`.
- **Archive rebrand:** the frozen v2 (`earlyprototype/kanbanger`) is renamed
  "Kanbanged" — branding only, no code/module change — freeing the `kanbanger` name
  for this successor.

## Consequences

Positive: install-once UX (adoption); conventional and recognisable; clean lineage
(Kanbanger live / Kanbanged retired); correctness made visible via `kanban-doctor`;
the resolution logic plus its test matrix is a strong demonstration artifact.

Negative / risk: correctness now lives in the resolution logic, so it must be
bulletproof and observable, or it fails silently in exactly the cases that matter in
a live demo — nested subfolder, monorepo, git worktree, symlinked path, no `.git`,
moved folder, copied board. Coordinated repo renames ripple through doc references
and redirects.

## Alternatives considered and rejected

- **Naive global server** (unpinned, cwd-only): served the legacy version and
  collided by name. Rejected.
- **Per-project venvs (status quo):** solve the collision but impose non-standard
  friction; only existed because of the naming collision. Rejected once the rename
  removes the cause.
- **A collision-proof key instead of renaming:** machinery to tolerate a
  self-inflicted problem. Rejected — the rename is the root fix.
- **Path-only binding key:** breaks on move/clone, undercutting the
  "collision-proof" property. Rejected for an in-board minted ID plus derived
  discovery.

## Implementation

Tracked in two issues: install/provision split + collision-proof binding (this
repo), and the archive rename to "Kanbanged" (the `earlyprototype/kanbanger` repo).
The module rename gates the rest.
