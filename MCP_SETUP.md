# Kanbanger MCP Server Setup Guide

This guide explains how to set up the Kanbanger MCP (Model Context Protocol) server for enhanced LLM integration.

## What is MCP?

MCP (Model Context Protocol) is a standard protocol that allows LLMs to interact with external tools and data sources in a structured way. Instead of LLMs reading files and running terminal commands, they can call typed functions directly.

## Benefits of MCP Integration

- **Explicit Tool Visibility**: Tools appear in the LLM's available tools list
- **Structured Parameters**: Type-safe, validated inputs
- **Real-time Resources**: LLM can always see current board state
- **Context Injection**: Prompts remind LLM about kanban usage
- **Cross-Client**: Works in Cursor, Claude Desktop, VS Code, etc.
- **Better Enforcement**: Tools are explicit, not optional

## Prerequisites

1. **Install MCP dependencies:**
```bash
pip install -e ".[mcp]"
```

2. **Verify installation:**
```bash
python -m kanbanger_mcp --help
```

## Setup for Cursor IDE

### 1. Create Configuration File

Create `.cursor/mcp.json` in your project root with **actual values** (not `${env:VAR}` placeholders):

```json
{
    "mcpServers": {
        "kanbanger": {
            "command": "python",
            "args": ["-m", "kanbanger_mcp"],
            "env": {
                "KANBANGER_WORKSPACE": "${workspaceFolder}",
                "GITHUB_TOKEN": "ghp_your_actual_token_here",
                "GITHUB_REPO": "owner/repo",
                "GITHUB_PROJECT_NUMBER": "7"
            }
        }
    }
}
```

**Important Notes:**
- Use `${workspaceFolder}` for workspace path (Cursor resolves this automatically)
- Put **actual values** for GitHub credentials (not `${env:GITHUB_TOKEN}`)
- The installer script reads your `.env` and populates these automatically
- Add `.cursor/mcp.json` to `.gitignore` to avoid committing secrets

**Quick Setup:** Run `install-mcp-to-workspace.ps1` - it reads your `.env` and creates this file for you!

### 2. Keep .env File for CLI Usage

Your `.env` file is still needed for the CLI tool (`kanban-sync`):


```env
GITHUB_TOKEN=your_github_token_here
GITHUB_REPO=owner/repo
GITHUB_PROJECT_NUMBER=6  # Optional, will auto-detect
```

### 3. Restart Cursor

Close and reopen Cursor to load the MCP server.

### 4. Verify Connection

Ask the AI: "What MCP tools do you have available?"

You should see:
- `add_task`
- `move_task`
- `delete_task`
- `list_tasks`
- `sync_to_github`
- `get_sync_status`

## Setup for Claude Desktop

### 1. Locate Configuration File

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### 2. Add Kanbanger Server

Edit the configuration file:

```json
{
    "mcpServers": {
        "kanbanger": {
            "command": "python",
            "args": ["-m", "kanbanger_mcp"],
            "env": {
                "KANBANGER_WORKSPACE": "/full/path/to/your/project",
                "GITHUB_TOKEN": "your_github_token_here",
                "GITHUB_REPO": "owner/repo",
                "GITHUB_PROJECT_NUMBER": "6"
            }
        }
    }
}
```

**Important:** Use absolute paths for `KANBANGER_WORKSPACE` in Claude Desktop.

### 3. Restart Claude Desktop

Close and reopen Claude Desktop.

### 4. Verify

In a new conversation, ask: "What tools do you have access to?"

## Setup for VS Code (with MCP Extension)

### 1. Install MCP Extension

Install the MCP extension for VS Code (if available).

### 2. Create Configuration

Create `.vscode/mcp.json`:

```json
{
    "mcpServers": {
        "kanbanger": {
            "command": "python",
            "args": ["-m", "kanbanger_mcp"],
            "env": {
                "KANBANGER_WORKSPACE": "${workspaceFolder}",
                "GITHUB_TOKEN": "${env:GITHUB_TOKEN}",
                "GITHUB_REPO": "${env:GITHUB_REPO}",
                "GITHUB_PROJECT_NUMBER": "${env:GITHUB_PROJECT_NUMBER}"
            }
        }
    }
}
```

### 3. Reload Window

Run "Developer: Reload Window" from the command palette.

## Running as HTTP Server

For web-based clients or remote access:

### 1. Start Server

```bash
python -m kanbanger_mcp --transport streamable-http --port 8000
```

### 2. Configure Client

```json
{
    "mcpServers": {
        "kanbanger": {
            "url": "http://localhost:8000/sse"
        }
    }
}
```

### 3. Production Deployment

For production, use a process manager:

```bash
# With systemd, supervisor, or pm2
pm2 start "python -m kanbanger_mcp --transport streamable-http --host 0.0.0.0 --port 8000" --name kanbanger-mcp
```

## Available MCP Capabilities

### Tools (Callable Functions)

| Tool | Purpose |
|------|---------|
| `add_task` | Add new task to board |
| `move_task` | Move task between columns |
| `delete_task` | Remove task from board |
| `list_tasks` | View tasks (all or filtered) |
| `sync_to_github` | Sync board to GitHub Projects |
| `get_sync_status` | Check GitHub sync state |

### Resources (Read-Only Data)

| Resource | Purpose |
|----------|---------|
| `kanban://current-board` | View current board markdown |
| `kanban://stats` | Task counts and distribution |
| `kanban://sync-status` | GitHub sync information |
| `kanban://config` | Current configuration |

### Prompts (Context Injection)

| Prompt | Purpose |
|--------|---------|
| `kanban_awareness` | General kanban usage guidance |
| `task_planning` | Help break down goals into tasks |
| `daily_standup` | Daily review and planning |
| `github_sync_check` | Sync reminder and guidance |

## Usage Examples

### Example 1: Adding a Task

```
User: "Add a task to implement user authentication in the TODO column"

LLM: [Calls add_task tool]
add_task(
    title="Implement user authentication",
    column="TODO",
    description="Add JWT-based authentication system"
)

Result: "Successfully added task 'Implement user authentication' to TODO"
```

### Example 2: Moving a Task

```
User: "I'm starting work on the authentication task"

LLM: [Calls move_task tool]
move_task(
    title="Implement user authentication",
    from_column="TODO",
    to_column="DOING"
)

Result: "Successfully moved 'Implement user authentication' from TODO to DOING"
```

### Example 3: Checking Board State

```
User: "What tasks are currently in progress?"

LLM: [Accesses kanban://current-board resource or calls list_tasks("DOING")]
list_tasks(column="DOING")

Result: {
    "DOING": [
        "Implement user authentication",
        "Fix bug in payment gateway"
    ]
}
```

### Example 4: Syncing to GitHub

```
User: "Sync the board to GitHub"

LLM: [Calls sync_to_github tool]
sync_to_github(dry_run=False)

Result: "Sync complete:
  [CREATE] Implement user authentication => InProgress
  [UPDATE] Fix bug in payment gateway: InProgress => InProgress
  ..."
```

## Troubleshooting

### MCP Server Not Appearing

1. **Check installation:**
```bash
python -m kanbanger_mcp --help
```

2. **Verify configuration file location:**
- Cursor: `.cursor/mcp.json` in project root
- Claude Desktop: See paths above

3. **Check logs:**
- Cursor: View → Output → Select "MCP" from dropdown
- Claude Desktop: Help → View Logs

### Tools Not Working

1. **Verify workspace:**
```bash
echo $KANBANGER_WORKSPACE  # Should be project root
```

2. **Check kanban file exists:**
```bash
ls _kanban.md  # Should exist in workspace
```

3. **Verify environment variables:**
```bash
echo $GITHUB_TOKEN  # Should be set
echo $GITHUB_REPO   # Should be owner/repo format
```

### Permission Errors

If you see permission errors:

1. **Check file permissions:**
```bash
ls -la _kanban.md
chmod 644 _kanban.md  # If needed
```

2. **Verify Python can write:**
```bash
python -c "open('_kanban.md', 'a').close()"
```

### Server Won't Start

1. **Check port availability (HTTP mode):**
```bash
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows
```

2. **Try different port:**
```bash
python -m kanbanger_mcp --transport streamable-http --port 8001
```

3. **Check Python version:**
```bash
python --version  # Should be 3.8+
```

## Advanced Configuration

### Custom Workspace Location

Override workspace in config:

```json
{
    "mcpServers": {
        "kanbanger": {
            "command": "python",
            "args": ["-m", "kanbanger_mcp"],
            "env": {
                "KANBANGER_WORKSPACE": "/custom/path/to/project",
                ...
            }
        }
    }
}
```

### Multiple Projects

Configure separate servers for each project:

```json
{
    "mcpServers": {
        "kanbanger-project-a": {
            "command": "python",
            "args": ["-m", "kanbanger_mcp"],
            "env": {
                "KANBANGER_WORKSPACE": "/path/to/project-a",
                "GITHUB_REPO": "owner/project-a",
                ...
            }
        },
        "kanbanger-project-b": {
            "command": "python",
            "args": ["-m", "kanbanger_mcp"],
            "env": {
                "KANBANGER_WORKSPACE": "/path/to/project-b",
                "GITHUB_REPO": "owner/project-b",
                ...
            }
        }
    }
}
```

### Debug Mode

Enable debug logging:

```bash
python -m kanbanger_mcp --debug
```

Or in config:

```json
{
    "mcpServers": {
        "kanbanger": {
            "command": "python",
            "args": ["-m", "kanbanger_mcp", "--debug"],
            ...
        }
    }
}
```

## Security Considerations

1. **Never commit `.cursor/mcp.json` with secrets**
   - Add to `.gitignore` if it contains tokens
   - Use `${env:VAR}` syntax to load from environment

2. **Use environment variables for tokens**
   - Store in `.env` (already in `.gitignore`)
   - Or use system environment variables

3. **Limit workspace access**
   - MCP server only accesses `KANBANGER_WORKSPACE`
   - Cannot read files outside workspace

4. **Review tool calls**
   - Some IDEs show tool call confirmations
   - Enable if you want to approve each action

## Next Steps

1. **Test the integration:**
   - Ask AI to add a test task
   - Move it through columns
   - Sync to GitHub

2. **Read the prompts:**
   - Try "Show me the kanban_awareness prompt"
   - Use "Help me plan tasks for [goal]"

3. **Explore resources:**
   - "Show me kanban://stats"
   - "What's the current sync status?"

4. **Integrate into workflow:**
   - Use daily_standup prompt each morning
   - Sync regularly with sync_to_github

## Support

- **Documentation:** See `README.md` and `LLM_GUIDANCE.md`
- **Issues:** https://github.com/earlyprototype/kanbanger/issues
- **Discussions:** https://github.com/earlyprototype/kanbanger/discussions

---

**MCP Server Version:** 2.1.0  
**Last Updated:** 2026-01-21
