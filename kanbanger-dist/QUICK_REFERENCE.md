# Kanbanger Quick Reference Card

## Installation

```bash
cd /path/to/Spec_Engine
bash kanbanger-dist/INSTALL.sh
cp .env.example .env
# Edit .env with your GitHub token
kanban-sync-setup
```

## Common Commands

### Generate Kanban from SPEC
```bash
python spec-to-kanban.py SPECs/project/spec_project.md
```

### Sync to GitHub
```bash
# Single kanban
kanban-sync SPECs/project/_kanban.md

# All kanbans
./sync-all-specs.sh

# Dry run (preview only)
kanban-sync _kanban.md --dry-run
```

### Specify Repo/Project
```bash
kanban-sync _kanban.md --repo owner/repo --project 1
```

## Kanban Format

```markdown
## BACKLOG
*   [ ] Future task

## TODO
*   [ ] Ready to start

## DOING
*   [ ] Currently working

## DONE
*   [x] Completed task
```

**Rules:**
- Use `## ` for headers (level 2)
- Use `*   [ ]` for tasks (asterisk + 3 spaces + checkbox)
- Use `[x]` only in DONE section

## LLM Commands

**To AI assistant:**
```
"Add 'implement caching' to my TODO"
"Move 'fix bug' to DONE"
"Show what's in progress"
"Break down 'build API' into smaller tasks"
```

## File Locations

```
Spec_Engine/
├── .env                    # Your config
├── spec-to-kanban.py       # Converter
├── sync-all-specs.sh       # Batch sync
└── SPECs/
    └── project/
        ├── _kanban.md      # Kanban board
        └── .kanban.json    # State (gitignored)
```

## Environment Variables

**.env file:**
```bash
GITHUB_TOKEN=ghp_your_token
GITHUB_REPO=owner/repo
GITHUB_PROJECT_NUMBER=1  # Optional
```

## Troubleshooting

**Command not found:**
```bash
python -m sync_kanban _kanban.md
```

**No projects linked:**
```
Go to: github.com/owner/repo → Projects → Link a project
```

**Missing Status field:**
```
Project → + New field → Single select → "Status"
Options: Backlog, Todo, InProgress, Done
```

## Column Mapping

| Markdown | GitHub Status |
|----------|---------------|
| BACKLOG  | Backlog       |
| TODO     | Todo          |
| DOING    | InProgress    |
| DONE     | Done          |

## Workflow

```
1. SPEC created
   ↓
2. python spec-to-kanban.py SPECs/project/spec_project.md
   ↓
3. LLM edits _kanban.md
   ↓
4. kanban-sync SPECs/project/_kanban.md
   ↓
5. GitHub Project board updates
```

## Help

```bash
kanban-sync --help
kanban-sync-setup --help
python spec-to-kanban.py --help
```

## Documentation

- `START_HERE.md` - Quick start
- `README.md` - Full documentation
- `SPEC_INTEGRATION.md` - Integration guide
- `LLM_GUIDANCE.md` - For AI assistants

## Support

- Kanbanger: github.com/earlyprototype/kanbanger
- Spec_Engine: github.com/earlyprototype/Spec_Engine
