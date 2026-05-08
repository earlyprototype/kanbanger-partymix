# Contributing to Kanbanger

Thanks for your interest in contributing to kanbanger! This document provides guidelines for contributing to the project.

## Code of Conduct

Be respectful, collaborative, and constructive. We're all here to make task management better.

## How Can I Contribute?

### Reporting Bugs

**Before submitting a bug report:**
- Check the [Issues](https://github.com/earlyprototype/kanbanger/issues) to see if it's already reported
- Try the latest version from `main` branch
- Check the [Troubleshooting section](README.md#troubleshooting) in the README

**When submitting a bug report, include:**
- **Clear title** - Describe the issue concisely
- **Steps to reproduce** - Exact steps to trigger the bug
- **Expected behaviour** - What should happen
- **Actual behaviour** - What actually happens
- **Environment:**
  - OS (Windows, Linux, macOS)
  - Python version (`python --version`)
  - Kanbanger version or commit hash
- **Relevant files** (anonymised if needed):
  - Your `_kanban.md` structure
  - Error messages and stack traces
  - `.kanban.json` state (remove sensitive IDs if needed)

**Example:**
```markdown
## Bug: Tasks duplicated on sync

**Steps:**
1. Create `_kanban.md` with 3 tasks
2. Run `kanban-sync _kanban.md`
3. Delete `.kanban.json`
4. Run `kanban-sync _kanban.md` again

**Expected:** Tasks not duplicated
**Actual:** Tasks appear twice on GitHub

**Environment:**
- Windows 11
- Python 3.12
- Commit: abc123def
```

### Suggesting Features

**Before suggesting a feature:**
- Check [existing issues](https://github.com/earlyprototype/kanbanger/issues) and [planned features](CHANGELOG.md#unreleased)
- Consider if it fits kanbanger's core philosophy (simplicity, markdown-first, LLM-friendly)

**When suggesting a feature, include:**
- **Use case** - Why do you need this?
- **Proposed solution** - How would it work?
- **Alternatives** - What other approaches did you consider?
- **Impact** - Who benefits? Any drawbacks?

**Example:**
```markdown
## Feature: Multiple status field support

**Use case:** My team uses Priority and Status fields. I want to sync both.

**Proposed solution:** Add config for multiple field mappings in `.env`

**Alternatives:** Separate kanban files per field (too complex)

**Impact:** Benefits teams with complex workflows. May complicate setup.
```

### Contributing Code

#### Development Setup

1. **Fork and clone:**
```bash
git clone https://github.com/YOUR_USERNAME/kanbanger.git
cd kanbanger
```

2. **Create a branch:**
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

3. **Install in development mode:**
```bash
pip install -e .
```

4. **Make your changes:**
- Follow the existing code style
- Add comments for complex logic
- Update documentation if needed

5. **Test your changes:**
```bash
# Create test kanban
cp example_kanban.md test_kanban.md

# Test dry run
kanban-sync test_kanban.md --dry-run

# Test actual sync (use a test project!)
kanban-sync test_kanban.md
```

6. **Update the kanban:**
```bash
# Yes, we dogfood! Update _kanban.md with your changes
nano _kanban.md
kanban-sync _kanban.md
```

7. **Commit your changes:**
```bash
git add .
git commit -m "feat: add amazing feature"
# or
git commit -m "fix: resolve sync bug"
```

8. **Push and create PR:**
```bash
git push origin feature/your-feature-name
```

Then open a Pull Request on GitHub.

#### Commit Message Format

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <description>

[optional body]

[optional footer]
```

**Types:**
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation only
- `style:` - Code style (formatting, no logic change)
- `refactor:` - Code restructuring (no behaviour change)
- `test:` - Adding or updating tests
- `chore:` - Maintenance (dependencies, tooling)

**Examples:**
```bash
feat: add support for GitHub Enterprise
fix: handle Unicode characters in task titles
docs: update README with new examples
refactor: extract GraphQL queries into separate file
chore: update requests dependency to 2.28.0
```

#### Code Style

**Python:**
- Follow [PEP 8](https://pep8.org/) style guide
- Use meaningful variable names
- Keep functions focused (single responsibility)
- Add docstrings for non-obvious functions
- Use type hints where helpful

**Example:**
```python
def sync_task_to_github(task: dict, status: str) -> str:
    """
    Syncs a single task to GitHub Projects.
    
    Args:
        task: Task dict with 'title' and 'description'
        status: Target status column ('Todo', 'InProgress', 'Done')
    
    Returns:
        GitHub item ID of created/updated task
    """
    # Implementation...
```

**Markdown:**
- Use consistent heading levels
- Include code examples with syntax highlighting
- Keep lines under 120 characters where reasonable
- Use UK English spelling

#### Testing Guidelines

Currently, kanbanger doesn't have automated tests (contributions welcome!). When testing:

1. **Test with a test project** - Don't use your production project board
2. **Test all operations:**
   - Create tasks
   - Move tasks between columns
   - Delete tasks (archive)
   - Handle edge cases (empty boards, special characters)
3. **Test different environments:**
   - Windows PowerShell
   - Linux bash
   - macOS zsh (if available)
4. **Document test results** in your PR

**Future testing improvements we'd love:**
- Unit tests for parsing logic
- Integration tests with GitHub API (mocked)
- End-to-end tests with test projects
- CI/CD pipeline with automated testing

### Improving Documentation

Documentation contributions are highly valued!

**Areas to improve:**
- **README.md** - Add examples, clarify confusing sections
- **LLM_GUIDANCE.md** - More examples, edge cases
- **CHANGELOG.md** - Keep it updated
- **Code comments** - Explain complex logic
- **New guides** - Tutorials, videos, blog posts

**Documentation standards:**
- Write for beginners - Don't assume knowledge
- Include examples - Show, don't just tell
- Keep it current - Update when features change
- UK English spelling
- No emoji in documentation (per project rules)

### Contributing to Distribution Package

The `kanbanger-dist/` folder is the production-ready package:

**When updating distribution:**
1. Make changes in root files first
2. Copy updated files to `kanbanger-dist/`
3. Test the distribution package:
```bash
cd /tmp
cp -r /path/to/kanbanger/kanbanger-dist ./test-dist
cd test-dist
pip install -e .
```
4. Update `DIST_README.md` if needed
5. Update version in `MANIFEST.md`

### Translations

We currently support only English. If you'd like to add translations:
- Open an issue to discuss approach first
- Consider i18n framework (e.g., gettext)
- Start with documentation, then CLI messages
- Maintain English as default/fallback

## Pull Request Process

1. **Update documentation** if you've changed behaviour
2. **Update CHANGELOG.md** under `[Unreleased]` section
3. **Update _kanban.md** and sync it (we dogfood!)
4. **Ensure your PR:**
   - Has a clear title and description
   - References any related issues (`Fixes #123`)
   - Includes examples/screenshots if UI changes
   - Has been tested

5. **PR review process:**
   - Maintainer will review within 1-7 days
   - Address feedback and push updates
   - Once approved, maintainer will merge
   - You'll be credited in the release notes

## Project Structure

```
kanbanger/
├── sync_kanban.py              # Core sync engine
├── setup_wizard.py             # Interactive setup
├── setup.py                    # Package config
├── git-hooks/                  # Git hook scripts
├── .cursor/rules/              # Cursor AI enforcement
├── kanbanger-dist/             # Distribution package
├── _kanban.md                  # Our own kanban (dogfooding!)
├── README.md                   # Main documentation
├── LLM_GUIDANCE.md            # AI assistant guide
├── CHANGELOG.md               # Version history
└── CONTRIBUTING.md            # This file
```

**Key files to understand:**
- `sync_kanban.py` - Main logic (parsing, syncing, GraphQL)
- `setup_wizard.py` - Configuration and validation
- `LLM_GUIDANCE.md` - How LLMs should interact with kanbans

## Architecture Overview

**Classes:**
- `LocalBoard` - Parses and manages markdown kanban
- `StateManager` - Handles `.kanban.json` persistence
- `GitHubClient` - GraphQL API communication
- `Syncer` - Orchestrates the sync process

**Flow:**
1. Parse `_kanban.md` → extract tasks + columns
2. Load `.kanban.json` → get existing GitHub item IDs
3. Connect to GitHub → fetch current project state
4. Diff local vs remote → determine changes
5. Apply mutations → create/update/archive on GitHub
6. Save state → update `.kanban.json`

**Key decisions:**
- Task titles as unique IDs (simple, but renaming = new task)
- Draft issues (not repository issues) for cleaner boards
- Archive instead of delete (recoverable)
- Markdown as source of truth (GitHub is just a view)

## Questions?

- **General questions:** Open a [Discussion](https://github.com/earlyprototype/kanbanger/discussions)
- **Bug reports:** Open an [Issue](https://github.com/earlyprototype/kanbanger/issues)
- **Security issues:** Email maintainers (see README for contact)

## Recognition

Contributors will be:
- Listed in release notes
- Credited in README (for significant contributions)
- Added to a CONTRIBUTORS file (coming soon)

## License

By contributing, you agree that your contributions will be licensed under the MIT License (same as the project).

---

**Thank you for contributing to kanbanger!**

Your efforts help make task management more accessible, transparent, and LLM-friendly for everyone.
