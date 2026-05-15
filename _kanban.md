# Kanbanger Development Kanban

## BACKLOG
*   [ ] Enhanced CLI tool for direct task management (add, move, list without MCP)
*   [ ] Add bidirectional sync (GitHub → Markdown)
*   [ ] Support for multiple kanban files in one repo
*   [ ] Webhook support for real-time GitHub updates
*   [ ] VS Code extension
*   [ ] Rich progress analytics and charts
*   [ ] Support for custom field mappings beyond Status

## TODO
*   [ ] Decide setup.py vs __version__ as version source-of-truth before PyPI publish (audit D10)

## DOING

## DONE (Recent)
*   [x] Bundle 1b: D9 helper extraction, move_task strict-gate, S7 Rework title revalidation
*   [x] Bug A: add_task appends at column bottom; delete_task compacts blanks (byte-exact round-trip)
*   [x] kanban-doctor preflight diagnostic (collision + version + schema_version checks)
*   [x] Per-project venv install pattern (setup-venv.py + INSTALL.md; resolves kanbanger_mcp import collision)
*   [x] Implement MCP server for LLM integration (resources, tools, prompts)

## DONE
*   [x] Consider PyPI publication
*   [x] Set up GitHub Issues templates
*   [x] Add CONTRIBUTING.md guide
*   [x] Create release/tag on GitHub
*   [x] Update dist folder with git hooks and complete package
*   [x] Create git hooks for kanban enforcement
*   [x] Add prominent IMPORTANT section to Cursor rules
*   [x] Define explicit triggers for adding/moving tasks in Cursor rules
*   [x] Core sync engine (create, update, archive)
*   [x] Repository-centric GraphQL queries
*   [x] State tracking with .kanban.json
*   [x] Setup wizard (kanban-sync-setup)
*   [x] LLM guidance documentation
*   [x] Spec_Engine integration package
*   [x] Clean public repository
*   [x] Fix GraphQL query bug
*   [x] Commit and push to GitHub
*   [x] Create Cursor rules for enforcement
