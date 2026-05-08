# Kanbanger Distribution Package v2.0

Complete, production-ready package for integrating kanbanger into your projects.

## What's New in v2.0

### Three Layers of Enforcement

1. **Git Hooks** (Commit-Level)
   - Pre-commit: Checks kanban is synced before commits
   - Post-commit: Auto-syncs after commits
   - Easy installation: `bash git-hooks/install-hooks.sh`

2. **Cursor AI Rules** (Planning-Level)
   - Forces AI to check `_kanban.md` before starting work
   - Requires all plans to reference kanban tasks
   - Automatic reminders to update and sync

3. **LLM Guidance** (Documentation-Level)
   - Comprehensive instructions for AI assistants
   - Strict markdown format rules
   - Best practices and examples

**Result:** Kanban usage becomes automatic and unavoidable at every level.

## Package Contents

### Installation & Setup
- `INSTALL.sh` - One-command installer for Spec_Engine projects
- `setup_wizard.py` - Interactive configuration wizard
- `setup.py` - Package configuration

### Core Application
- `sync_kanban.py` - Main synchronization engine
- `spec_engine_integration.py` - Spec_Engine-specific integration

### Git Hooks (`git-hooks/`)
- `pre-commit` - Pre-commit enforcement hook
- `post-commit` - Auto-sync hook
- `install-hooks.sh` - Easy installation script
- `README.md` - Complete git hooks documentation

### Cursor AI Rules (`.cursor/`)
- `rules/project_management/kanbanger.mdc` - AI enforcement rules

### Documentation
- `START_HERE.md` - Quick start guide
- `README.md` - Complete documentation
- `INDEX.md` - Package navigation
- `MANIFEST.md` - File inventory
- `QUICK_REFERENCE.md` - Command cheat sheet
- `SPEC_INTEGRATION.md` - Spec_Engine integration guide
- `LLM_WORKFLOW.md` - LLM usage examples
- `LLM_GUIDANCE.md` - AI assistant instructions

### Examples
- `example_kanban.md` - Sample kanban format

### Legal
- `LICENSE` - MIT License

## Quick Install

### For Spec_Engine Projects

```bash
cd /path/to/Spec_Engine
bash kanbanger-dist/INSTALL.sh
```

This automatically installs:
- Kanbanger package
- Git hooks (pre-commit, post-commit)
- Cursor AI rules
- Helper scripts (spec-to-kanban.py, sync-all-specs.sh)
- Configuration files

### For Standalone Projects

```bash
# 1. Install package
pip install -e kanbanger-dist/

# 2. Install git hooks
bash kanbanger-dist/git-hooks/install-hooks.sh

# 3. Install Cursor rules (if using Cursor)
mkdir -p .cursor/rules/project_management
cp kanbanger-dist/.cursor/rules/project_management/kanbanger.mdc \
   .cursor/rules/project_management/

# 4. Configure
cp kanbanger-dist/.env.example .env
nano .env  # Add your GitHub token

# 5. Run setup wizard
kanban-sync-setup
```

## What Gets Installed

### In Your Project Root
- `.env.example` - Configuration template
- `.gitignore` - Updated with kanbanger entries
- `spec-to-kanban.py` - SPEC converter (Spec_Engine only)
- `sync-all-specs.sh` - Batch syncer (Spec_Engine only)
- `KANBANGER_INTEGRATION.md` - Project-specific guide

### Git Hooks
- `.git/hooks/pre-commit` - Enforces kanban sync
- `.git/hooks/post-commit` - Auto-syncs after commits

### Cursor Rules
- `.cursor/rules/project_management/kanbanger.mdc` - AI enforcement

## Usage

### Basic Workflow

```bash
# 1. Edit your kanban
nano _kanban.md

# 2. Git will check it's synced before commit
git add _kanban.md
git commit -m "Update tasks"
# → Pre-commit hook checks sync status

# 3. After commit, auto-sync runs
# → Post-commit hook syncs to GitHub automatically
```

### With AI Assistant

```
You: "Claude, add 'implement caching' to TODO"
AI:  [Edits _kanban.md] "Added. Run: kanban-sync _kanban.md"
You: kanban-sync _kanban.md
```

### For Spec_Engine

```bash
# Generate kanban from SPEC
python spec-to-kanban.py SPECs/project/spec_project.md

# Sync to GitHub
kanban-sync SPECs/project/_kanban.md

# Or sync all at once
./sync-all-specs.sh
```

## Enforcement in Action

### Git Hooks

**Before commit:**
```bash
$ git commit -m "Update code"

⚠️  WARNING: Kanban has unsaved changes!
Commit anyway? (y/N): n

$ kanban-sync _kanban.md
Sync complete!

$ git commit -m "Update code"
✓ Kanban check passed
```

**After commit:**
```bash
[main abc123] Update code

📋 Kanban was updated, syncing to GitHub...
[UPDATE] Fix bug: Todo → Done
Sync complete!
```

### Cursor AI Rules

When you use Cursor AI, the assistant will:
1. Check `_kanban.md` before starting any task
2. Reference which tasks it's working on
3. Update kanban as it completes work
4. Remind you to sync at the end

**Example:**
```
AI: "Before we start, I checked _kanban.md. 
     I see 'implement caching' in TODO. 
     I'll move it to DOING and begin work..."
     
[AI implements feature]

AI: "Complete! I've moved 'implement caching' to DONE.
     Don't forget to sync: kanban-sync _kanban.md"
```

## Configuration

### Environment Variables

Create `.env` file:
```bash
GITHUB_TOKEN=ghp_your_token_here
GITHUB_REPO=username/repo-name
GITHUB_PROJECT_NUMBER=1  # optional
```

### GitHub Token

Get from: https://github.com/settings/tokens

Required scopes:
- `repo` - Repository access
- `project` - Project management

### Setup Wizard

Interactive configuration:
```bash
kanban-sync-setup
```

Validates:
- GitHub token
- Repository access
- Linked projects
- Status field configuration

## File Structure After Installation

```
your-project/
├── .env                          # Configuration
├── .env.example                  # Template
├── .gitignore                    # Updated
├── _kanban.md                    # Your kanban board
├── .kanban.json                  # State tracking (auto-generated)
├── .cursor/
│   └── rules/
│       └── project_management/
│           └── kanbanger.mdc     # AI rules
├── .git/hooks/
│   ├── pre-commit                # Enforcement
│   └── post-commit               # Auto-sync
└── kanbanger-dist/               # This package (optional to keep)
```

## Documentation Quick Reference

### Get Started
1. `START_HERE.md` - 5-minute quick start
2. `INDEX.md` - Package navigation
3. `QUICK_REFERENCE.md` - Command cheat sheet

### Usage
- `README.md` - Complete documentation
- `LLM_WORKFLOW.md` - Using with AI assistants
- `SPEC_INTEGRATION.md` - Spec_Engine integration

### Enforcement
- `git-hooks/README.md` - Git hooks guide
- `.cursor/rules/project_management/kanbanger.mdc` - AI rules
- `LLM_GUIDANCE.md` - AI assistant instructions

### Reference
- `MANIFEST.md` - File inventory
- `example_kanban.md` - Sample format

## Troubleshooting

### "kanban-sync: command not found"
```bash
python -m sync_kanban _kanban.md
```

### Git hooks not running
```bash
chmod +x .git/hooks/pre-commit
chmod +x .git/hooks/post-commit
```

### Cursor rules not working
Ensure file is at:
`.cursor/rules/project_management/kanbanger.mdc`

### Reset state tracking
```bash
rm .kanban.json
kanban-sync _kanban.md
```

## System Requirements

- **Python:** 3.8+
- **Git:** Any recent version
- **Cursor:** Latest version (for AI rules)
- **OS:** Windows, Linux, macOS

## Dependencies

Auto-installed via pip:
- `requests>=2.25.0`
- `python-dotenv>=0.19.0`

## Package Size

Approximately 250KB of text files. No binaries.

## Compatibility

Works with:
- Spec_Engine projects
- Standalone projects
- Any Git repository
- Any GitHub account with project access

## Support

- **GitHub Issues:** https://github.com/earlyprototype/kanbanger/issues
- **Spec_Engine:** https://github.com/earlyprototype/Spec_Engine

## Version History

### v2.0 (2026-01-11)
- Added git hooks (pre-commit, post-commit)
- Added Cursor AI rules for enforcement
- Updated all documentation
- Complete enforcement layer

### v1.0 (2026-01-10)
- Initial distribution package
- Core sync engine
- Spec_Engine integration
- LLM guidance

## License

MIT License - See LICENSE file

---

**Ready to install?**

```bash
cd /path/to/your-project
bash kanbanger-dist/INSTALL.sh
```

Or for standalone use:

```bash
pip install -e kanbanger-dist/
bash kanbanger-dist/git-hooks/install-hooks.sh
kanban-sync-setup
```

**Let's get tracking!**
