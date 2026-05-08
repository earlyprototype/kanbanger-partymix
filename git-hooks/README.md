# Kanbanger Git Hooks

Git hooks to enforce kanban usage in your repository.

## What They Do

### pre-commit
**Runs before every commit**
- Checks if `_kanban.md` exists
- Warns if kanban has never been synced
- Warns if kanban has unsaved changes (modified since last sync)
- Blocks commit unless user confirms (optional override)

### post-commit
**Runs after every commit**
- Detects if `_kanban.md` was in the commit
- Automatically syncs kanban to GitHub
- Shows sync results

## Installation

### Quick Install

```bash
cd your-project
bash git-hooks/install-hooks.sh
```

### Manual Install

```bash
# Copy hooks to .git/hooks/
cp git-hooks/pre-commit .git/hooks/pre-commit
cp git-hooks/post-commit .git/hooks/post-commit

# Make executable
chmod +x .git/hooks/pre-commit
chmod +x .git/hooks/post-commit
```

### Windows (PowerShell)

```powershell
# Copy hooks
Copy-Item git-hooks\pre-commit .git\hooks\pre-commit
Copy-Item git-hooks\post-commit .git\hooks\post-commit
```

Note: You may need Git Bash or WSL to run the hooks on Windows.

## Usage

Once installed, the hooks run automatically:

```bash
# Edit your kanban
nano _kanban.md

# Try to commit
git add _kanban.md
git commit -m "Update tasks"

# Pre-commit hook checks if synced
# If not synced recently, you'll be warned

# After commit, post-commit hook syncs automatically
```

## Behavior

### Pre-Commit Hook

**Scenario 1: Kanban doesn't exist**
```
❌ ERROR: No _kanban.md found!
Create a kanban board before committing
```
Blocks commit.

**Scenario 2: Never synced**
```
⚠️  WARNING: Kanban has never been synced to GitHub
Sync before committing: kanban-sync _kanban.md
Commit anyway? (y/N):
```
Allows override.

**Scenario 3: Unsaved changes**
```
⚠️  WARNING: Kanban has unsaved changes!
_kanban.md was modified after last sync.
Commit anyway? (y/N):
```
Allows override.

**Scenario 4: All good**
```
✓ Kanban check passed
```
Commit proceeds.

### Post-Commit Hook

**If `_kanban.md` was committed:**
```
📋 Kanban was updated, syncing to GitHub...
  [CREATE] New task => Todo
  [UPDATE] Existing task: Todo => Done
Sync complete!
```

**If `_kanban.md` not in commit:**
Hook runs silently, no output.

## Disabling Hooks

### Temporarily (one commit)

```bash
git commit --no-verify -m "message"
```

### Permanently

```bash
rm .git/hooks/pre-commit
rm .git/hooks/post-commit
```

## Customization

Edit the hook files directly in `.git/hooks/` after installation:

- Make pre-commit stricter (block instead of warn)
- Change post-commit behavior
- Add additional checks

## Troubleshooting

### Hook doesn't run

Check if executable:
```bash
ls -la .git/hooks/
chmod +x .git/hooks/pre-commit
chmod +x .git/hooks/post-commit
```

### "kanban-sync: command not found"

The post-commit hook will try:
1. `kanban-sync` command
2. `python -m sync_kanban` as fallback

Ensure kanbanger is installed:
```bash
pip install -e .
```

### Windows compatibility

Git hooks are bash scripts. On Windows:
- Install Git Bash (comes with Git for Windows)
- Or use WSL
- Git will automatically use bash to run hooks

## Best Practices

1. **Install hooks in all team repositories** - Consistent enforcement
2. **Don't commit `.git/hooks/`** - Each developer installs locally
3. **Keep `git-hooks/` folder in repo** - Version control the hook source
4. **Document for team** - Include installation in onboarding

## For Teams

Add to your README:

```markdown
## Setup

After cloning:
1. Install dependencies: `pip install -e .`
2. Install git hooks: `bash git-hooks/install-hooks.sh`
3. Create kanban: `cp example_kanban.md _kanban.md`
4. Initial sync: `kanban-sync _kanban.md`
```

## Uninstall

```bash
rm .git/hooks/pre-commit
rm .git/hooks/post-commit
```

The hooks only affect your local repository.
