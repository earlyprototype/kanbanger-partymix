# Kanbanger Distribution Package

Welcome! This folder contains everything you need to integrate kanbanger with your Spec_Engine project.

## What is This?

**Kanbanger** syncs markdown kanban boards to GitHub Projects V2, enabling:
- Text-based task management (fast, versionable)
- Visual GitHub project boards (beautiful, shareable)
- LLM-driven task management (conversational)
- Automatic sync from Spec_Engine SPECs

## Quick Start (5 Minutes)

### 1. Copy This Folder to Your Spec_Engine Project

```bash
cp -r kanbanger-dist /path/to/Spec_Engine/
cd /path/to/Spec_Engine
```

### 2. Run the Installer

```bash
bash kanbanger-dist/INSTALL.sh
```

This will:
- Install kanbanger package
- Update .gitignore with necessary entries
- Create helper scripts (spec-to-kanban, sync-all)
- Install git hooks (pre-commit, post-commit)
- Install Cursor AI rules for enforcement
- Set up integration files

### 3. Configure GitHub

```bash
# Create config from template
cp .env.example .env

# Edit with your details
nano .env
```

Add your GitHub token from: https://github.com/settings/tokens
(Scopes needed: `repo`, `project`)

### 4. Run Setup Wizard

```bash
kanban-sync-setup
```

Validates everything is connected properly.

### 5. Create Your First Kanban

```bash
# Generate from a SPEC
python spec-to-kanban.py SPECs/your_project/spec_your_project.md

# Sync to GitHub
kanban-sync SPECs/your_project/_kanban.md
```

Done! Check your GitHub Project board.

---

## What's in This Folder

### Core Files
- `setup.py` - Package installation
- `sync_kanban.py` - Main sync engine
- `setup_wizard.py` - Interactive configuration
- `spec_engine_integration.py` - Spec_Engine integration setup
- `INSTALL.sh` - One-command installer

### Enforcement Layer
- `git-hooks/` - Pre-commit and post-commit hooks
  - `pre-commit` - Checks kanban is synced before commits
  - `post-commit` - Auto-syncs after commits
  - `install-hooks.sh` - Installation script
  - `README.md` - Git hooks documentation
- `.cursor/rules/project_management/kanbanger.mdc` - Cursor AI enforcement rules

### Documentation

**Start Here:**
- `START_HERE.md` - This file
- `TRANSFER_TO_SPEC_ENGINE.md` - Detailed transfer instructions

**Integration:**
- `SPEC_INTEGRATION.md` - Complete Spec_Engine integration guide
- `LLM_WORKFLOW.md` - LLM-first workflow examples

**Reference:**
- `README.md` - General kanbanger documentation
- `LLM_GUIDANCE.md` - AI assistant instructions
- `TESTING.md` - Testing scenarios
- `IMPLEMENTATION_SUMMARY.md` - Technical details
- `MIGRATION_STRATEGIES.md` - Mid-project adoption

### Examples
- `example_kanban.md` - Sample kanban file
- `.gitignore` - Recommended entries

### Legal
- `LICENSE` - MIT License

---

## Folder Structure After Installation

```
Spec_Engine/
├── .env                           # Your config (create from .env.example)
├── .env.example                   # Config template (created)
├── .gitignore                     # Updated with kanbanger entries
├── spec-to-kanban.py              # SPEC → kanban converter (created)
├── sync-all-specs.sh              # Sync all kanbans (created)
├── KANBANGER_INTEGRATION.md       # Usage guide (created)
├── kanbanger-dist/                # This folder (keep or delete after install)
├── .cursor/
│   └── rules/
│       └── project_management/
│           └── kanbanger.mdc      # AI enforcement rules (created)
├── .git/hooks/
│   ├── pre-commit                 # Checks kanban before commits (created)
│   └── post-commit                # Auto-syncs after commits (created)
└── SPECs/
    └── your_project/
        ├── spec_your_project.md
        ├── _kanban.md             # Generated kanban
        └── .kanban.json           # State (gitignored)
```

---

## Recommended Reading Order

1. **START_HERE.md** (this file) - Quick overview
2. **TRANSFER_TO_SPEC_ENGINE.md** - Detailed installation
3. **SPEC_INTEGRATION.md** - Integration concepts and patterns
4. **LLM_WORKFLOW.md** - How to use with AI assistants
5. **README.md** - General kanbanger features
6. **LLM_GUIDANCE.md** - For AI assistants helping you
7. **TESTING.md** - Test scenarios
8. **MIGRATION_STRATEGIES.md** - Advanced topics

---

## Common Workflows

### Daily Task Management

```bash
# LLM edits your kanban
"Claude, add 'implement caching' to TODO"

# Sync to GitHub
kanban-sync SPECs/my_project/_kanban.md

# GitHub board updates automatically
```

### New SPEC Creation

```bash
# 1. Create SPEC (your workflow)
create_spec new_feature

# 2. Generate kanban
python spec-to-kanban.py SPECs/new_feature/spec_new_feature.md

# 3. Sync to GitHub
kanban-sync SPECs/new_feature/_kanban.md
```

### Sync All SPECs

```bash
# Sync all kanban boards at once
./sync-all-specs.sh
```

---

## Troubleshooting

### "SPECs directory not found"

Run installer from Spec_Engine root:
```bash
cd /path/to/Spec_Engine
bash kanbanger-dist/INSTALL.sh
```

### "kanban-sync: command not found"

Use Python module syntax:
```bash
python -m sync_kanban _kanban.md
```

Or add to PATH:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### "No projects found linked to repository"

Link a project:
1. Go to your repo on GitHub
2. Click "Projects" tab
3. Click "Link a project"
4. Create or select a project

### "No 'Status' field found"

Add Status field to your GitHub Project:
1. Open project on GitHub
2. Click "+ New field"
3. Choose "Single select"
4. Name it "Status"
5. Add options: `Backlog`, `Todo`, `InProgress`, `Done`

---

## Three Layers of Enforcement

Kanbanger ensures kanban boards stay updated through:

1. **Git Hooks** - Commit-level checks and auto-sync
2. **Cursor AI Rules** - Forces AI to reference kanban in all plans
3. **LLM Guidance** - Documentation for proper usage

**Result:** Kanban usage becomes automatic and unavoidable.

## The Vision

**Spec_Engine** provides structured autonomous execution.  
**Kanbanger** provides visual tracking and team collaboration.  
**LLMs** provide conversational task management.

Together they enable:
```
SPEC (planned) → Kanban (tracked) → GitHub (visualized) → Team (informed)
```

You get structured AI development with beautiful visual dashboards and enforced tracking!

---

## Support

- **Kanbanger:** https://github.com/earlyprototype/kanbanger
- **Spec_Engine:** https://github.com/earlyprototype/Spec_Engine

---

## Next Steps

1. ✅ Read this file
2. ✅ Run `bash INSTALL.sh` from your Spec_Engine project
3. ✅ Configure `.env`
4. ✅ Run `kanban-sync-setup`
5. ✅ Generate your first kanban
6. ✅ Sync to GitHub
7. 🎉 Start using conversational kanban management!

**Ready? Let's go!**

```bash
cd /path/to/Spec_Engine
bash kanbanger-dist/INSTALL.sh
```
