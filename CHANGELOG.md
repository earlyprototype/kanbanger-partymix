# Changelog

All notable changes to kanbanger will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **First-run onboarding is now MCP-native.** The server `instructions` tell
  the assistant to detect a missing board on first contact, ask the user
  before setup, then run the local install and create the canonical 5-column
  board (BACKLOG -> TODO -> DOING -> REVIEW -> DONE). The empty-board resource
  template and the `kanban_awareness` prompt were aligned to 5 columns.

### Removed
- **Deprecated Cursor setup wizard.** `setup_wizard.py` and its
  `kanban-sync-setup` console-script were removed (they wrote a Cursor
  `.cursor/mcp.json` with `${workspaceFolder}` and a 4-column board). Use
  `scripts/setup-venv.py` (the per-project install path) instead. README,
  `docs/setup-flow.md`, and CONTRIBUTING were updated to match.
- **Stale Cursor-era reference docs.** Removed `MCP_SETUP.md`,
  `CURSOR_WORKSPACE_VARIABLES.md`, `WORKSPACE_CONFIG.md`,
  `MCP_IMPLEMENTATION_PLAN.md`, and `install-mcp-to-workspace.ps1` — all
  superseded by `INSTALL.md` + `scripts/setup-venv.py` (they documented the
  removed `.cursor/mcp.json` / `${workspaceFolder}` install path).
- **`kanbanger-dist/` distribution bundle.** Retired the legacy hand-maintained
  v2-era bundle (18 files) in favour of the per-project `setup-venv.py` install
  and the planned PyPI distribution; its pre-commit drift-guard test was removed
  with it. Recoverable via the `dist-final-2026-06-03` git tag.

## v0.0.1 — 2026-05-08

Fork from `earlyprototype/kanbanger` v2.1.0 as `kanbanger-partymix`.
This is the v3.0 successor's starting commit. The predecessor
remains available read-only at the original repo as the v2.x
archive.

No functional changes from v2.1.0 in this commit. Phase 0.5 follow-up
commits land R3 (subprocess timeout) and Finding 7 root-cause work.

## [2.0.0] - 2026-01-11

### Added - Three-Layer Enforcement System

#### Git Hooks
- **Pre-commit hook** - Checks if kanban is synced before allowing commits
  - Detects if `_kanban.md` exists
  - Warns if kanban has never been synced
  - Warns if kanban has unsaved changes
  - Optional override for flexibility
- **Post-commit hook** - Automatically syncs kanban after commits
  - Detects if `_kanban.md` was in the commit
  - Runs `kanban-sync` automatically
  - Shows sync results in terminal
- **Installation script** (`git-hooks/install-hooks.sh`) - Easy one-command setup
- **Documentation** (`git-hooks/README.md`) - Complete guide with examples

#### Cursor AI Rules
- `.cursor/rules/project_management/kanbanger.mdc` - Enforces kanban usage in AI-assisted development
- Forces AI to check `_kanban.md` before starting any task
- Requires all plans to reference kanban tasks
- Includes steps to update kanban during execution
- Automatic reminders to sync after completing tasks
- Prominent "IMPORTANT" section for unavoidable enforcement

#### Complete Distribution Package
- `kanbanger-dist/` - Production-ready package with all files
- Updated `INSTALL.sh` to install git hooks and Cursor rules automatically
- `DIST_README.md` - Comprehensive package overview
- Updated all documentation with enforcement information
- Package now tracked in repository for easy export

### Changed
- Updated `README.md` with enforcement sections and git hooks usage
- Updated `MANIFEST.md` to reflect v2.0 structure
- Updated `INDEX.md` with enforcement layer navigation
- Updated `START_HERE.md` with enforcement workflows
- Refined `.gitignore` to track distribution package

### Fixed
- `UnicodeEncodeError` when printing special characters on Windows
  - Explicitly set UTF-8 encoding for stdout
- GraphQL query bug with optional `projectNumber` variable
  - Fixed conditional inclusion in repository lookup

## [1.0.0] - 2026-01-10

### Added - Core Functionality

#### Synchronization Engine
- Parse markdown kanban files with standard format
- Sync to GitHub Projects V2 via GraphQL API
- Create draft issues for new tasks
- Update Status field when tasks move between columns
- Archive tasks when deleted from markdown
- Smart diff to minimize API calls

#### State Tracking
- `.kanban.json` sidecar file for mapping local tasks to GitHub items
- Tracks `item_id` and `status` for each task
- Prevents duplicate creation on subsequent syncs
- Task titles as unique identifiers

#### Repository-Centric Approach
- Automatically discover projects linked to repository
- Support for organization-owned projects
- Per-repository project lookup via GraphQL
- Multiple projects per repository support

#### Setup Tools
- `setup_wizard.py` - Interactive configuration wizard
  - Validates GitHub token
  - Checks repository access
  - Verifies linked projects
  - Validates Status field configuration
  - Creates `.env` file automatically
  - Generates example kanban
- `.env` file support with `python-dotenv`
- Environment variable configuration
  - `GITHUB_TOKEN`
  - `GITHUB_REPO`
  - `GITHUB_PROJECT_NUMBER` (optional)

#### Documentation
- `README.md` - Complete usage guide
- `LLM_GUIDANCE.md` - Instructions for AI assistants
  - Strict markdown format rules
  - Task management best practices
  - Common operations (add, move, mark done)
  - Example interactions
  - Error prevention guidelines
- `example_kanban.md` - Sample kanban format

#### Spec_Engine Integration
- `spec_engine_integration.py` - Automated integration setup
- SPEC to kanban conversion utilities
- Distribution package for easy transfer
- Integration documentation

### Features

#### Command-Line Interface
- `kanban-sync <file>` - Sync markdown to GitHub
- `--dry-run` flag - Preview changes without syncing
- `--repo` flag - Specify repository explicitly
- `--project` flag - Specify project number
- `kanban-sync-setup` - Run setup wizard

#### Column Mapping
- Normalizes common column name variations
- `BACKLOG` / `BACK LOG` → `Backlog`
- `TODO` / `TO DO` → `Todo`
- `DOING` / `IN PROGRESS` / `IN-PROGRESS` → `InProgress`
- `DONE` / `COMPLETE` / `COMPLETED` → `Done`
- Ignores numbering (e.g., `## 1. TODO` works)

#### Task Format
- Standard markdown checkbox format
- `*   [ ]` for active tasks
- `*   [x]` for completed tasks (in DONE section)
- Task titles as unique identifiers
- Full task description in single line

#### GitHub Integration
- Creates tasks as draft issues (not repository issues)
- Updates Status field on project board
- Archives instead of deleting
- Preserves custom fields
- Supports project metadata

### Technical

#### Architecture
- Class-based structure for maintainability
  - `LocalBoard` - Parse and manage markdown
  - `StateManager` - Handle `.kanban.json` persistence
  - `GitHubClient` - GraphQL API interactions
  - `Syncer` - Orchestrate sync logic
- GraphQL API for GitHub Projects V2
- Mutations for create, update, archive operations
- Efficient diff algorithm

#### Dependencies
- `requests>=2.25.0` - HTTP client
- `python-dotenv>=0.19.0` - Environment variable management
- Python 3.8+ required

#### Security
- `.env` files automatically gitignored
- `.kanban.json` automatically gitignored
- Token validation in setup wizard
- No tokens in logs or output

## [Unreleased]

### Planned Features
- Bidirectional sync (GitHub → Markdown)
- Support for multiple kanban files in one repo
- Webhook support for real-time GitHub updates
- VS Code extension
- Rich progress analytics and charts
- Support for custom field mappings beyond Status
- PyPI publication for easier installation

---

## Version History Summary

- **v2.0.0** - Three-layer enforcement system (git hooks, AI rules, documentation)
- **v1.0.0** - Core sync engine with state tracking and Spec_Engine integration

---

## Links

- **Repository:** https://github.com/earlyprototype/kanbanger
- **Issues:** https://github.com/earlyprototype/kanbanger/issues
- **Releases:** https://github.com/earlyprototype/kanbanger/releases
- **Spec_Engine:** https://github.com/earlyprototype/Spec_Engine
