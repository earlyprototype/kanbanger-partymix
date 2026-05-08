# kanban-project-sync

Powered by [fckgit](https://github.com/earlyprototype/fckgit) - Trusted by Vibe Warriors

Sync your local markdown kanban boards to GitHub Projects V2. Keep your task management in version control while automatically updating your GitHub project boards.

## What It Does

- **Write tasks in Markdown** → Automatically syncs to GitHub Projects
- **Move tasks between columns** → Updates on GitHub
- **Add new tasks** → Creates draft issues
- **Delete tasks** → Archives on GitHub
- **No manual clicking** → Your markdown file is the source of truth

## Quick Start

### Option A: Automated Setup (Recommended)

Run the interactive setup wizard:

```bash
pip install .
kanban-sync-setup
```

The wizard will:
- Guide you through getting a GitHub token
- Validate your token and repository
- Check if your project is properly linked
- Verify Status field configuration
- Create a `.env` file with your settings
- Generate an example kanban file

### Option B: Manual Setup

### 1. Install

```bash
pip install .
```

### 2. Get Your GitHub Token

1. Go to https://github.com/settings/tokens
2. Click **"Generate new token (classic)"**
3. Name it: `kanban-sync-tool`
4. Select scopes:
   - ✅ `repo` (Full control of private repositories)
   - ✅ `project` (Full control of projects)
5. Click **"Generate token"**
6. Copy the token (starts with `ghp_...`)

### 3. Create .env File

Create a `.env` file in your project directory:

```bash
GITHUB_TOKEN=ghp_your_token_here
GITHUB_REPO=your-username/your-repo-name
```

**Example:**
```bash
GITHUB_TOKEN=ghp_abc123def456ghi789
GITHUB_REPO=earlyprototype/kanbanger
```

### 4. Link Project to Repository

1. Go to your repository on GitHub
2. Click the **"Projects"** tab
3. Click **"Link a project"**
4. Select your existing project (or create a new one)

### 5. Configure Status Field

Your GitHub Project needs a **Status** field with these options:

1. Open your project on GitHub
2. Look for the **Status** field (or create it: **+ New field** → **Single select**)
3. Add these four options:
   - `Backlog`
   - `Todo`
   - `InProgress`
   - `Done`

**Note:** Your existing columns like "Ready", "In progress", "In review" need to be renamed to match these exact names.

### 6. Create Your Kanban Markdown

Create a `_kanban.md` file (or any name you prefer):

```markdown
## BACKLOG
*   [ ] Research new features
*   [ ] Write documentation

## TODO
*   [ ] Fix bug in parser
*   [ ] Update dependencies

## DOING
*   [ ] Implement sync logic

## DONE
*   [x] Setup project structure
*   [x] Install dependencies
```

### 7. Sync!

**Windows (PowerShell):**
```powershell
kanban-sync _kanban.md
```

**Linux/Mac:**
```bash
kanban-sync _kanban.md
```

## Usage

### Basic Commands

```bash
# Dry run (preview without syncing)
kanban-sync _kanban.md --dry-run

# Sync using .env file
kanban-sync _kanban.md

# Specify repo explicitly
kanban-sync _kanban.md --repo username/repo

# Specify project number (if multiple projects linked)
kanban-sync _kanban.md --repo username/repo --project 2
```

### What Happens During Sync

The tool performs a smart diff:

- **New tasks** → Creates draft issues on GitHub
- **Moved tasks** → Updates Status field on GitHub
- **Deleted tasks** → Archives on GitHub
- **Unchanged tasks** → No API calls (efficient!)

### Example Workflow

1. **Edit your markdown file:**
```markdown
## TODO
*   [ ] New feature request  ← Added this

## DOING
*   [ ] Fix critical bug  ← Moved from TODO
```

2. **Run sync:**
```powershell
kanban-sync _kanban.md
```

3. **Output:**
```
[CREATE] New feature request -> Todo
[UPDATE] Fix critical bug: Todo -> InProgress
```

4. **Check GitHub** → Changes are live!

## Features

### Draft Issues (Default)

Tasks are created as **Draft Issues** (not repository issues). This means:

- ✅ Clean project boards without cluttering Issues tab
- ✅ Lightweight task tracking
- ✅ Full custom field support
- ✅ Can convert to real issues later if needed

To convert a draft to an issue:
1. Click the draft card in your project
2. Click "Convert to issue"
3. Choose your repository

### State Tracking

A `.kanban.json` file is created to track GitHub item IDs:

```json
{
  "project_id": "PVT_...",
  "tasks": {
    "Task title": {
      "item_id": "PVTI_...",
      "status": "Todo"
    }
  }
}
```

**Important:** 
- This file should be in `.gitignore` (automatically added)
- Task titles are unique identifiers
- Renaming a task creates a new item (by design)

### Column Name Mapping

The tool normalizes common column names:

| Your Markdown | Maps To |
|--------------|---------|
| `## BACKLOG` | `Backlog` |
| `## TO DO` or `## TODO` | `Todo` |
| `## DOING` or `## IN PROGRESS` | `InProgress` |
| `## DONE` or `## COMPLETE` | `Done` |

Numbers are optional: `## 1. BACKLOG` works too.

## Advanced Usage

### Multiple Projects

If your repo has multiple linked projects:

```bash
kanban-sync _kanban.md --project 2
```

Or set in `.env`:
```bash
GITHUB_PROJECT_NUMBER=2
```

### Custom Kanban Files

Sync different boards:

```bash
kanban-sync docs/_planning.md
kanban-sync sprint/_current.md
```

Each gets its own `.kanban.json` in the same directory.

### Git Hook Integration

Automatic enforcement at commit time with pre-built hooks:

```bash
bash git-hooks/install-hooks.sh
```

**What gets installed:**

1. **pre-commit hook** - Checks before every commit:
   - Ensures `_kanban.md` exists
   - Warns if kanban hasn't been synced
   - Blocks commit if kanban has unsaved changes (with override option)

2. **post-commit hook** - Auto-syncs after commits:
   - Detects if `_kanban.md` was in the commit
   - Automatically runs `kanban-sync`
   - Shows sync results

**Example:**
```bash
$ git commit -m "Update tasks"

⚠️  WARNING: Kanban has unsaved changes!
Commit anyway? (y/N): n

$ kanban-sync _kanban.md
Sync complete!

$ git commit -m "Update tasks"
✓ Kanban check passed

📋 Kanban was updated, syncing to GitHub...
[UPDATE] Fix bug: Todo → Done
Sync complete!
```

See `git-hooks/README.md` for full documentation.

## Troubleshooting

### "kanban-sync: command not found"

**Solution:** Use Python module syntax:
```bash
python -m sync_kanban _kanban.md
```

**Or add to PATH (Windows):**
```powershell
$env:PATH += ";C:\Users\YourName\AppData\Local\Programs\Python\Python312\Scripts"
```

### "No projects found linked to repository"

**Solution:** Link your project to the repository:
1. Go to your repo → Projects tab
2. Click "Link a project"
3. Select your project

### "No 'Status' field found in project"

**Solution:** Add Status field to your project:
1. Open project on GitHub
2. Click "+ New field"
3. Choose "Single select"
4. Name it "Status"
5. Add options: `Backlog`, `Todo`, `InProgress`, `Done`

### "401 Unauthorized" or "403 Forbidden"

**Solution:** Check your GitHub token:
- Ensure `GITHUB_TOKEN` is set correctly in `.env`
- Token needs `repo` and `project` scopes
- Token may be expired - generate a new one

### "Environment variable not set"

**Solution:** Create `.env` file or use explicit flags:
```bash
kanban-sync _kanban.md --repo username/repo
```

### State file out of sync

**Solution:** Delete and recreate:
```bash
rm .kanban.json
kanban-sync _kanban.md
```

**Note:** This may create duplicate items. Manually archive old ones on GitHub.

## Best Practices

1. **Add to .gitignore:**
   ```
   .kanban.json
   .env
   ```

2. **Use descriptive task titles** - They're the unique identifiers

3. **Commit markdown changes** - Let git track your task history

4. **Run dry-run first** - Preview changes before syncing:
   ```bash
   kanban-sync _kanban.md --dry-run
   ```

5. **One board per focus area** - Don't mix unrelated tasks

## Project Structure

```
your-repo/
├── .env                    # Your tokens (gitignored)
├── .gitignore              # Includes .env and .kanban.json
├── _kanban.md              # Your markdown kanban board
├── .kanban.json            # State file (gitignored, auto-created)
└── ...
```

## Setup Wizard

The `kanban-sync-setup` wizard makes configuration painless:

```bash
kanban-sync-setup
```

**What it does:**
1. Checks/creates `.gitignore` to protect secrets
2. Validates your GitHub token
3. Checks repository access
4. Verifies project is linked to repository
5. Validates Status field configuration
6. Creates `.env` file with your settings
7. Optionally creates example kanban file

**Example output:**
```
============================================================
  kanban-project-sync Setup Wizard
============================================================

[Step 1/6] Checking .gitignore
-------------------------------------------------------------
  [OK] .gitignore looks good

[Step 2/6] GitHub Personal Access Token
-------------------------------------------------------------
  [INFO] .env file found
  [OK] Token valid! Logged in as: earlyprototype

[Step 3/6] GitHub Repository
-------------------------------------------------------------
  [INFO] Found in .env: earlyprototype/kanbanger

[Step 4/6] Checking Linked Projects
-------------------------------------------------------------
  [OK] Found 1 linked project(s):
    #6: @earlyprototype's kanbanger

[Step 5/6] Checking Status Field Configuration
-------------------------------------------------------------
  [OK] Status field configured correctly!

[Step 6/6] Saving Configuration
-------------------------------------------------------------
  [OK] .env file created

Setup Complete!
```

## How It Works

1. **Parse** your markdown file into tasks + columns
2. **Load** state from `.kanban.json` to know existing items
3. **Connect** to GitHub via GraphQL API
4. **Fetch** current project items
5. **Diff** local vs remote state
6. **Apply** changes (create/update/archive)
7. **Save** updated state to `.kanban.json`

## Limitations

- Task titles must be unique (used as identifiers)
- Renaming tasks creates new items (by design)
- One Status field per project
- Draft issues only (can convert manually)
- No bidirectional sync (markdown → GitHub only)

## Contributing

Found a bug? Want a feature? Open an issue or PR!

## License

See [LICENSE](LICENSE)

## Three Layers of Enforcement

Kanbanger provides multiple enforcement mechanisms to ensure kanban boards are always up to date:

### 1. Git Hooks (Commit-Level)
- **pre-commit**: Checks if kanban is synced before allowing commits
- **post-commit**: Auto-syncs kanban after successful commits
- Install: `bash git-hooks/install-hooks.sh`

### 2. Cursor AI Rules (Planning-Level)
- Forces AI assistant to check `_kanban.md` before starting work
- Requires all plans to reference kanban tasks
- Reminds to update and sync after completing tasks
- Location: `.cursor/rules/project_management/kanbanger.mdc`

### 3. LLM Guidance (Usage-Level)
- Comprehensive documentation for AI assistants
- Strict markdown format rules
- Task management best practices
- Reference: `LLM_GUIDANCE.md`

**Result:** Kanban becomes unavoidable - enforced at the git, AI, and documentation levels.

## LLM-Assisted Kanban Management

This tool is designed to work seamlessly with AI assistants like ChatGPT, Claude, or GitHub Copilot.

### What LLMs Can Help With

**Creating boards:**
> "Create a kanban board for my e-commerce project"

**Managing tasks:**
> "Add 'implement search feature' to TODO"
> "Move 'fix payment bug' to DONE"
> "I finished these three tasks: X, Y, Z"

**Organization:**
> "Reorganize my TODO by priority"
> "Break down 'build frontend' into smaller tasks"
> "What should I work on next?"

### How It Works

1. **You ask** your AI assistant to edit the kanban file
2. **AI modifies** the markdown using the proper format
3. **You sync** with `kanban-sync _kanban.md`
4. **GitHub updates** automatically

See [LLM_GUIDANCE.md](LLM_GUIDANCE.md) for comprehensive instructions for AI assistants.

### Example Workflow

```
You:  "Claude, add these features to my backlog:
       - User authentication, Dark mode, Export to PDF"

AI:   [Edits _kanban.md, adds to BACKLOG section]
      "Added 3 items to your backlog. Run 'kanban-sync _kanban.md'
       to sync with GitHub."

You:  kanban-sync _kanban.md

Tool: [CREATE] User authentication -> Backlog
      [CREATE] Dark mode -> Backlog
      [CREATE] Export to PDF -> Backlog
      Sync complete!
```

This makes kanban management conversational and natural!

## Credits

Built with love by the Vibe Warriors. Powered by [fckgit](https://github.com/earlyprototype/fckgit).
