# Kanbanger Distribution - Complete Package

Version: 2.0  
Date: 2026-01-11  
For: Spec_Engine Integration & Standalone Use

## Package Structure

### Installation
- `INSTALL.sh` - One-command installer for Spec_Engine projects

### Core Application Files
- `setup.py` - Package configuration and dependencies
- `sync_kanban.py` - Main synchronization engine
- `setup_wizard.py` - Interactive configuration wizard
- `spec_engine_integration.py` - Spec_Engine-specific setup automation

### Enforcement Layer

#### Git Hooks (`git-hooks/`)
- `pre-commit` - Checks kanban is synced before commits
- `post-commit` - Auto-syncs kanban after commits
- `install-hooks.sh` - Easy installation script
- `README.md` - Git hooks documentation

#### Cursor AI Rules (`.cursor/rules/project_management/`)
- `kanbanger.mdc` - Enforces kanban usage in AI-assisted development

### Documentation

#### Quick Start
- `START_HERE.md` - Read this first! Quick overview and installation
- `INDEX.md` - Package navigation guide
- `QUICK_REFERENCE.md` - Common commands and workflows

#### Integration
- `SPEC_INTEGRATION.md` - Complete Spec_Engine integration guide
- `LLM_WORKFLOW.md` - LLM-first workflow examples

#### Reference
- `README.md` - Complete kanbanger documentation
- `LLM_GUIDANCE.md` - Instructions for AI assistants to manage kanbans

### Examples
- `example_kanban.md` - Sample kanban board format

### Legal
- `LICENSE` - MIT License

## File Purposes

### For Users (Read These)
1. `START_HERE.md` - Start here
2. `TRANSFER_TO_SPEC_ENGINE.md` - Installation guide
3. `SPEC_INTEGRATION.md` - How it works with Spec_Engine
4. `README.md` - General usage

### For AI Assistants (Share These)
1. `LLM_GUIDANCE.md` - Format rules and best practices
2. `LLM_WORKFLOW.md` - Example conversations

### For Developers
1. `IMPLEMENTATION_SUMMARY.md` - Architecture
2. `TESTING.md` - Test coverage
3. `MIGRATION_STRATEGIES.md` - Advanced patterns

## Usage

### Installation
```bash
cd /path/to/Spec_Engine
bash kanbanger-dist/INSTALL.sh
```

### What Gets Installed
- `.env.example` - Configuration template
- `spec-to-kanban.py` - SPEC converter
- `sync-all-specs.sh` - Batch syncer
- `KANBANGER_INTEGRATION.md` - Project-specific guide
- Updated `.gitignore` - Protects secrets
- `.git/hooks/pre-commit` - Pre-commit enforcement
- `.git/hooks/post-commit` - Auto-sync after commits
- `.cursor/rules/project_management/kanbanger.mdc` - AI enforcement

## Three Layers of Enforcement

1. **Git Hooks** - Commit-level enforcement
2. **Cursor AI Rules** - Planning-level enforcement
3. **LLM Guidance** - Usage-level documentation

Result: Kanban usage becomes unavoidable and automatic.

## Size
- Total: ~250KB text files
- No binaries or dependencies (installed via pip)

## Requirements
- Python 3.8+
- pip
- Git (optional, for hooks)
- GitHub account with repo access

## Dependencies (installed automatically)
- requests>=2.25.0
- python-dotenv>=0.19.0

## Compatibility
- Windows (PowerShell)
- Linux (Bash)
- macOS (Bash/Zsh)
- Any Python 3.8+ environment

## Support
- Issues: https://github.com/earlyprototype/kanbanger/issues
- Spec_Engine: https://github.com/earlyprototype/Spec_Engine
