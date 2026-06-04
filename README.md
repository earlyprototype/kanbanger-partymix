# kanbanger-partymix

> Successor to [`github.com/earlyprototype/kanbanger`](https://github.com/earlyprototype/kanbanger)
> (v2.x archive, read-only). This repo is the v3.0 codebase home; see the
> [kanbanger-platform planning workspace](https://github.com/earlyprototype/kanbanger-platform)
> for strategic context.

**MCP-First Task Management** - Let AI manage your kanban board, sync to GitHub Projects V2

## What is kanbanger-partymix?

kanbanger-partymix is an **MCP (Model Context Protocol) server** that gives AI assistants structured tools to manage your tasks. Your kanban board lives in markdown (`_kanban.md`) and automatically syncs to GitHub Projects.

**Key Benefit**: AI can directly add, move, and sync tasks without you touching files or running commands.

## Quick Start

```mermaid
graph LR
    A[Clone] --> B[setup-venv.py]
    B --> C[AI creates board]
    C --> D[AI manages tasks]
    D --> E[Auto-sync to GitHub]
    
    style A fill:#4CAF50
    style B fill:#2196F3
    style D fill:#9C27B0
    style E fill:#4CAF50
```

### 1. Clone kanbanger-partymix (once)

```bash
git clone https://github.com/earlyprototype/kanbanger-partymix.git
```

### 2. Provision your project (per project)

From your project's root directory, run the per-project installer (adjust the
path to wherever you cloned this repo):

```bash
python /path/to/kanbanger-partymix/scripts/setup-venv.py
```

It creates a per-project `.venv`, installs kanbanger into it, and writes a
`.mcp.json` pinned to that venv. See **[INSTALL.md](INSTALL.md)** for the full
flow and how to supply GitHub credentials.

### 3. Open a fresh Claude Code session

The kanbanger MCP server loads automatically. On first contact, if the project
has no board yet, the assistant tells you Kanbanger isn't set up here and
**asks** whether to set it up — say yes and it creates the canonical 5-column
`_kanban.md` for you.

### 4. Use It!

**With AI (MCP mode):**
```
You: "Add a task to implement user auth to the TODO column"
AI: [Calls add_task tool] ✅ Task added!

You: "Move that task to DOING"
AI: [Calls move_task tool] ✅ Task moved!

You: "Sync to GitHub"
AI: [Calls sync_to_github tool] ✅ Synced!
```

**Manual mode (still works!):**
```bash
# Edit _kanban.md manually, then:
kanban-sync _kanban.md
```

## How It Works

### MCP Integration (Recommended)

Your AI assistant gets these **tools**:
- `add_task(title, column, description)` - Add tasks
- `move_task(title, from, to)` - Move between columns
- `delete_task(title, column)` - Remove tasks
- `list_tasks(column?)` - View tasks
- `sync_to_github(dry_run)` - Push to GitHub
- `get_sync_status()` - Check sync state

And these **resources** (always visible):
- `kanban://current-board` - Live board state
- `kanban://stats` - Task counts
- `kanban://sync-status` - GitHub sync info

Plus **context prompts**:
- `kanban_awareness` - Reminds AI about board
- `task_planning` - Helps break down goals
- `daily_standup` - Morning review
- `github_sync_check` - Sync reminders

### The Workflow

```mermaid
graph TD
    Open[Open project in IDE] --> AI{Using AI?}
    
    AI -->|Yes| MCP[AI uses MCP tools]
    AI -->|No| Manual[Edit _kanban.md manually]
    
    MCP --> Tasks[_kanban.md updated]
    Manual --> Tasks
    
    Tasks --> Sync[Sync to GitHub<br/>via tool or command]
    Sync --> Team[Team sees updates]
    
    style MCP fill:#2196F3
```

## Kanban Board Format

Create `_kanban.md` in your project root:

```markdown
# Project Kanban

## BACKLOG
*   [ ] Future feature ideas
*   [ ] Nice-to-have improvements

## TODO
*   [ ] Ready to start
*   [ ] Prioritized tasks

## DOING
*   [ ] Currently active work

## REVIEW
*   [ ] Awaiting review before Done

## DONE
*   [x] Completed tasks
*   [x] Finished features
```

**That's it!** No special syntax, just markdown.

## Configuration

### Per-Project Setup (Automatic)

`scripts/setup-venv.py` writes a `.mcp.json` in your project root, with the
`command` pinned to that project's own `.venv` python:

```json
{
    "mcpServers": {
        "kanbanger": {
            "command": "/abs/path/to/project/.venv/Scripts/python.exe",
            "args": ["-m", "kanbanger_mcp"],
            "env": {
                "KANBANGER_WORKSPACE": "${KANBANGER_WORKSPACE:-/abs/path/to/project}",
                "GITHUB_TOKEN": "${GITHUB_TOKEN:-}",
                "GITHUB_REPO": "${GITHUB_REPO:-}",
                "GITHUB_PROJECT_NUMBER": "${GITHUB_PROJECT_NUMBER:-}"
            }
        }
    }
}
```

**Key points:**
- `${VAR:-default}` - Claude Code substitution syntax (not Cursor's `${env:VAR}`).
- **Per-project venv** - the pinned `.venv` python avoids the `kanbanger_mcp`
  import collision between installs (see [INSTALL.md](INSTALL.md)).
- **Per-project** - each project gets its own independent `.mcp.json` + venv.

### GitHub credentials

Don't hardcode secrets in `.mcp.json`. Provide real values via the project's
gitignored `.claude/settings.local.json` `env` block, which Claude Code injects
into the MCP server spawn:

```json
{
  "env": {
    "GITHUB_TOKEN": "ghp_...",
    "GITHUB_REPO": "owner/repo",
    "GITHUB_PROJECT_NUMBER": "6"
  }
}
```

**Get a GitHub Token:**
1. GitHub Settings → Developer Settings → Personal Access Tokens
2. Generate new token (classic)
3. Required scopes: `repo`, `project`, `read:org`

## Commands

| Command | Purpose |
|---------|---------|
| `python scripts/setup-venv.py` | Provision a project's venv + `.mcp.json` |
| `kanban-doctor` | Preflight / diagnose a project's install |
| `kanban-sync _kanban.md --dry-run` | Preview changes (safe) |
| `kanban-sync _kanban.md` | Sync to GitHub |
| `python -m kanbanger_mcp --help` | MCP server options |

**Or just ask your AI!**
- "Add task X to TODO"
- "Move task Y to DOING"
- "Sync to GitHub"

## Why MCP-First?

### Traditional Approach (Fragile)
```
User: "Add a task"
AI: *Reads _kanban.md*
AI: *Edits file with search/replace*
AI: *Runs terminal command*
AI: *Hopes nothing broke*
```

### MCP Approach (Robust)
```
User: "Add a task"
AI: add_task("Task name", "TODO") ✅
```

**Benefits:**
- ✅ Type-safe, validated operations
- ✅ AI always aware of board state (resources)
- ✅ Context injected automatically (prompts)
- ✅ Works across all AI clients (Cursor, Claude, etc.)
- ✅ No parsing errors or file corruption

## Multiple Projects

Each project gets its own venv + MCP server:

```
ProjectA/
├── .venv/                        # Project-local kanbanger install
├── .mcp.json                     # Pinned to ProjectA/.venv
├── _kanban.md
└── .claude/settings.local.json   # GitHub creds (gitignored)

ProjectB/
├── .venv/
├── .mcp.json                     # Pinned to ProjectB/.venv
├── _kanban.md
└── .claude/settings.local.json
```

Run `setup-venv.py` once per project — each `.mcp.json` is pinned to its own
venv, so the projects stay fully isolated.

## Documentation

- **[INSTALL.md](INSTALL.md)** - Per-project install (the authoritative setup guide)
- **[Setup Flow Diagram](docs/setup-flow.md)** - Visual guide
- **[LLM Guidance](LLM_GUIDANCE.md)** - How AI should use kanbanger
- **[Contributing](CONTRIBUTING.md)** - How to contribute

## Git Hooks (Optional Enforcement)

Want to ensure the board is always synced? Install git hooks:

```bash
cd git-hooks
./install-hooks.sh  # or install-hooks.ps1 on Windows
```

- **Pre-commit**: Checks board is synced before commit
- **Post-commit**: Auto-syncs after commit

## Troubleshooting

### MCP Tools Not Showing

1. **Check the config exists:**
```bash
ls .mcp.json
```

2. **Check the venv resolves kanbanger:**
```bash
.venv/Scripts/python -c "import kanbanger_mcp; print(kanbanger_mcp.__file__)"
```

3. **Restart Claude Code** - required after `.mcp.json` changes.

4. **Run the doctor** - `kanban-doctor` reports common install problems.

### Sync Failures

1. **Verify credentials:**
```bash
# Check .env exists
cat .env

# Test token
curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user
```

2. **Check project exists:**
   - Go to your repo on GitHub
   - Verify Project is linked
   - Check Status field has: Backlog, Todo, InProgress, Review, Done

### Wrong Workspace

If the MCP server can't find `_kanban.md`:

1. **Use the project-local config** - `.mcp.json` in the project root (not global)
2. **Check the workspace** - did Claude Code open the correct folder?
3. **Restart Claude Code** - reloads configuration

## FAQ

**Q: Can I use CLI without MCP?**  
A: Yes! `kanban-sync _kanban.md` works standalone.

**Q: Does MCP work in other IDEs?**  
A: Yes! Cursor, Claude Desktop, VS Code (with extension), any MCP client.

**Q: What if I already use GitHub Projects?**  
A: Kanbanger syncs one-way: local → GitHub. Your project becomes a view of your markdown.

**Q: Can I use with multiple GitHub Projects?**  
A: Yes, different project per workspace. Each workspace configured independently.

**Q: Is PyPI available?**  
A: Not yet. We're focusing on API stability first. Use git installation for now.

## Examples

### AI Workflow
```
Morning:
You: "Show me daily standup prompt"
AI: [Shows standup review with current board state]

You: "Add task to implement OAuth to TODO"
AI: ✅ Added

You: "I'm starting work on OAuth"  
AI: ✅ Moved to DOING

Afternoon:
You: "OAuth is done"
AI: ✅ Moved to DONE

Evening:
You: "Sync everything to GitHub"
AI: ✅ Synced - 1 created, 1 updated
```

### Manual Workflow
```bash
# Edit _kanban.md in your editor
vim _kanban.md

# Preview changes
kanban-sync _kanban.md --dry-run

# Sync for real
kanban-sync _kanban.md
```

## Project Status

- ✅ MCP Server
- ✅ GitHub Projects V2 sync
- ✅ Per-project venv install (`setup-venv.py`)
- ✅ First-run onboarding (AI offers to create the board)
- ✅ Git hooks
- ✅ `kanban-doctor` preflight
- 🔄 Bidirectional sync (planned)
- 🔄 Multiple kanban files (planned)
- 🔄 VS Code extension (planned)

## License

MIT - See [LICENSE](LICENSE)

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

## Credits

Built with the Model Context Protocol (MCP) ecosystem. Inspired by the workspace-aware patterns in [fckgit](https://github.com/earlyprototype/fckgit).

---

**Made with ❤️ for developers who want AI-assisted task management without leaving their editor.**
