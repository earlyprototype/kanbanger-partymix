# MCP Server Implementation Plan for Kanbanger

## Overview

Transform kanbanger from a CLI-only tool into a full MCP (Model Context Protocol) server, providing structured tools, resources, and prompts that LLMs can use directly without needing to read files or run terminal commands.

## Key Insights from Research

### From fckgit's `.cursor/mcp.json`
```json
{
    "mcpServers": {
        "timepon": {
            "args": ["C:\\Users\\Fab2\\Desktop\\AI\\_timecop\\mcp-server\\index.js"],
            "env": {
                "TIMEPON_WORKSPACE": "${workspaceFolder}"
            },
            "command": "node"
        }
    }
}
```

**Key Pattern:** Uses `${workspaceFolder}` variable for per-project workspace awareness.

### From thought-bubble MCP Server
- Full TypeScript MCP server implementation
- Provides tools for document visualization
- Uses `@modelcontextprotocol/sdk` package
- Structured as npm package for easy distribution

### From Context7 Documentation
- MCP servers can expose:
  - **Tools**: Callable functions with typed parameters
  - **Resources**: Readable data (like current kanban state)
  - **Prompts**: Injected instructions for LLM context

## Architecture Decision

**Language:** Python (matches existing codebase)  
**Framework:** `mcp-use` Python SDK (well-documented, modern)  
**Transport:** Streamable HTTP (for flexibility) + stdio (for CLI clients)  
**Location:** New `kanbanger_mcp/` directory in project root

## Per-Project Workspace Awareness

### Configuration File Location
```
.cursor/mcp.json          # Cursor-specific (per-project)
~/.cursor/mcp.json        # Global fallback
```

### Environment Variables Pattern
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

**Key Features:**
- `${workspaceFolder}` - Cursor/IDE provides project root
- `${env:VAR}` - Load from environment variables
- Per-project config overrides global

## MCP Server Design

### 1. Resources (Read-Only Data)

Resources expose kanban state for LLM awareness:

```python
@server.resource(
    uri="kanban://current-board",
    name="current_kanban_board",
    title="Current Kanban Board",
    description="Real-time view of _kanban.md",
    mime_type="text/markdown"
)
def get_current_board() -> str:
    """Return current kanban board content."""
    workspace = os.getenv("KANBANGER_WORKSPACE", os.getcwd())
    kanban_path = os.path.join(workspace, "_kanban.md")
    if os.path.exists(kanban_path):
        with open(kanban_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "No kanban board found in workspace"

@server.resource(
    uri="kanban://stats",
    name="kanban_stats",
    title="Kanban Statistics",
    description="Task counts and column distribution",
    mime_type="application/json"
)
def get_kanban_stats() -> str:
    """Return JSON stats about current board."""
    workspace = os.getenv("KANBANGER_WORKSPACE", os.getcwd())
    board = LocalBoard(os.path.join(workspace, "_kanban.md"))
    stats = {
        "backlog": len(board.tasks.get("BACKLOG", [])),
        "todo": len(board.tasks.get("TODO", [])),
        "doing": len(board.tasks.get("DOING", [])),
        "done": len(board.tasks.get("DONE", [])),
        "total": sum(len(tasks) for tasks in board.tasks.values())
    }
    return json.dumps(stats, indent=2)

@server.resource(
    uri="kanban://sync-status",
    name="sync_status",
    title="Sync Status",
    description="Last sync time and GitHub sync state",
    mime_type="application/json"
)
def get_sync_status() -> str:
    """Return sync status from .kanban.json."""
    workspace = os.getenv("KANBANGER_WORKSPACE", os.getcwd())
    state_path = os.path.join(workspace, ".kanban.json")
    if os.path.exists(state_path):
        with open(state_path, 'r', encoding='utf-8') as f:
            state = json.load(f)
            return json.dumps({
                "synced_tasks": len(state.get("items", {})),
                "state_file": state_path
            }, indent=2)
    return json.dumps({"synced_tasks": 0, "state_file": "not found"})
```

### 2. Tools (Callable Functions)

Tools provide structured operations:

```python
@server.tool()
def add_task(title: str, column: str = "TODO", description: str = "") -> str:
    """
    Add a new task to the kanban board.
    
    Args:
        title: Task title (required)
        column: Target column (BACKLOG, TODO, DOING, DONE)
        description: Optional task description
    """
    workspace = os.getenv("KANBANGER_WORKSPACE", os.getcwd())
    kanban_path = os.path.join(workspace, "_kanban.md")
    
    # Read current board
    with open(kanban_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find column section
    column_pattern = f"## {column}"
    if column_pattern not in content:
        return f"Error: Column {column} not found"
    
    # Add task
    task_line = f"*   [ ] {title}"
    if description:
        task_line += f" - {description}"
    
    # Insert after column header
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.strip() == column_pattern:
            lines.insert(i + 1, task_line)
            break
    
    # Write back
    with open(kanban_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    return f"Added task '{title}' to {column}"

@server.tool()
def move_task(title: str, from_column: str, to_column: str) -> str:
    """
    Move a task between columns.
    
    Args:
        title: Task title to move
        from_column: Source column
        to_column: Destination column
    """
    workspace = os.getenv("KANBANGER_WORKSPACE", os.getcwd())
    kanban_path = os.path.join(workspace, "_kanban.md")
    
    # Read, parse, modify, write
    board = LocalBoard(kanban_path)
    
    # Find task
    task = None
    for t in board.tasks.get(from_column, []):
        if t['title'] == title:
            task = t
            break
    
    if not task:
        return f"Error: Task '{title}' not found in {from_column}"
    
    # Move task
    board.tasks[from_column].remove(task)
    if to_column not in board.tasks:
        board.tasks[to_column] = []
    
    # Update checkbox if moving to DONE
    if to_column == "DONE":
        task['completed'] = True
    
    board.tasks[to_column].append(task)
    board.save()
    
    return f"Moved '{title}' from {from_column} to {to_column}"

@server.tool()
def sync_to_github(dry_run: bool = False) -> str:
    """
    Sync kanban board to GitHub Projects.
    
    Args:
        dry_run: If True, show what would be synced without making changes
    """
    workspace = os.getenv("KANBANGER_WORKSPACE", os.getcwd())
    kanban_path = os.path.join(workspace, "_kanban.md")
    
    if dry_run:
        # Run sync in dry-run mode
        result = subprocess.run(
            ["python", "-m", "sync_kanban", kanban_path, "--dry-run"],
            capture_output=True,
            text=True,
            cwd=workspace
        )
    else:
        result = subprocess.run(
            ["python", "-m", "sync_kanban", kanban_path],
            capture_output=True,
            text=True,
            cwd=workspace
        )
    
    if result.returncode == 0:
        return f"Sync {'preview' if dry_run else 'complete'}:\n{result.stdout}"
    else:
        return f"Sync failed:\n{result.stderr}"

@server.tool()
def list_tasks(column: str = None) -> str:
    """
    List tasks from kanban board.
    
    Args:
        column: Optional column filter (BACKLOG, TODO, DOING, DONE)
    """
    workspace = os.getenv("KANBANGER_WORKSPACE", os.getcwd())
    kanban_path = os.path.join(workspace, "_kanban.md")
    
    board = LocalBoard(kanban_path)
    
    if column:
        tasks = board.tasks.get(column, [])
        return json.dumps({column: [t['title'] for t in tasks]}, indent=2)
    else:
        all_tasks = {
            col: [t['title'] for t in tasks]
            for col, tasks in board.tasks.items()
        }
        return json.dumps(all_tasks, indent=2)

@server.tool()
def delete_task(title: str, column: str) -> str:
    """
    Delete a task from the kanban board.
    
    Args:
        title: Task title to delete
        column: Column containing the task
    """
    workspace = os.getenv("KANBANGER_WORKSPACE", os.getcwd())
    kanban_path = os.path.join(workspace, "_kanban.md")
    
    board = LocalBoard(kanban_path)
    
    # Find and remove task
    for i, task in enumerate(board.tasks.get(column, [])):
        if task['title'] == title:
            board.tasks[column].pop(i)
            board.save()
            return f"Deleted task '{title}' from {column}"
    
    return f"Error: Task '{title}' not found in {column}"
```

### 3. Prompts (Context Injection)

Prompts inject awareness into LLM context:

```python
@server.prompt(
    name="kanban_awareness",
    title="Kanban Board Awareness",
    description="Reminds LLM to check and update kanban board"
)
def kanban_awareness_prompt() -> str:
    """Inject kanban awareness into LLM context."""
    return """
# Kanban Board Management

This project uses a kanban board (_kanban.md) for task tracking.

## Available Tools:
- `add_task(title, column, description)` - Add new task
- `move_task(title, from_column, to_column)` - Move task between columns
- `list_tasks(column)` - View tasks
- `sync_to_github(dry_run)` - Sync to GitHub Projects
- `delete_task(title, column)` - Remove task

## Available Resources:
- `kanban://current-board` - View current board state
- `kanban://stats` - Task statistics
- `kanban://sync-status` - GitHub sync status

## Workflow:
1. Before starting work: Check current board state
2. When planning: Add tasks to BACKLOG or TODO
3. When starting: Move task to DOING
4. When complete: Move task to DONE
5. Periodically: Sync to GitHub

## Columns:
- **BACKLOG**: Future ideas and features
- **TODO**: Ready to start
- **DOING**: Currently in progress (limit 1-2 tasks)
- **DONE**: Completed tasks
"""

@server.prompt(
    name="task_planning",
    title="Task Planning Assistant",
    description="Help plan and break down tasks"
)
def task_planning_prompt(goal: str) -> str:
    """Help LLM plan tasks for a goal."""
    return f"""
# Task Planning for: {goal}

Break down this goal into actionable tasks for the kanban board.

## Guidelines:
- Each task should be specific and measurable
- Estimate complexity (S/M/L)
- Identify dependencies
- Suggest appropriate column (BACKLOG/TODO)

## Output Format:
For each task, provide:
1. Title (concise, action-oriented)
2. Description (what needs to be done)
3. Column (where to place it)
4. Dependencies (if any)

After planning, use `add_task()` to add them to the board.
"""
```

## Implementation Steps

### Phase 1: Core MCP Server (Week 1)

1. **Setup Project Structure**
```
kanbanger/
├── kanbanger_mcp/
│   ├── __init__.py
│   ├── server.py          # Main MCP server
│   ├── tools.py           # Tool implementations
│   ├── resources.py       # Resource implementations
│   ├── prompts.py         # Prompt implementations
│   └── utils.py           # Shared utilities
├── setup.py               # Update with mcp extras
└── README.md              # Update with MCP docs
```

2. **Install Dependencies**
```bash
pip install mcp-use
```

3. **Implement Basic Server**
- Create `server.py` with MCPServer initialization
- Implement 2-3 core tools (add_task, list_tasks, sync_to_github)
- Implement 1-2 resources (current-board, stats)
- Test with stdio transport locally

4. **Add Workspace Awareness**
- Read `KANBANGER_WORKSPACE` environment variable
- Fall back to `os.getcwd()` if not set
- Validate workspace has `_kanban.md`

### Phase 2: Full Tool Suite (Week 2)

5. **Implement All Tools**
- `add_task`
- `move_task`
- `delete_task`
- `list_tasks`
- `sync_to_github`
- `get_sync_status`

6. **Implement All Resources**
- `kanban://current-board`
- `kanban://stats`
- `kanban://sync-status`
- `kanban://config` (show current .env settings)

7. **Implement Prompts**
- `kanban_awareness` - General awareness
- `task_planning` - Planning assistant
- `daily_standup` - Daily review prompt

### Phase 3: Integration & Documentation (Week 3)

8. **Create Configuration Templates**
- `.cursor/mcp.json.template`
- `.vscode/mcp.json.template`
- Global config example

9. **Update Documentation**
- Add MCP section to README
- Create MCP_SETUP.md guide
- Update LLM_GUIDANCE.md with MCP patterns
- Add examples to CONTRIBUTING.md

10. **Distribution Package**
- Update `kanbanger-dist/` with MCP server
- Add MCP setup to `setup_wizard.py`
- Create npm package for easy installation

### Phase 4: Testing & Polish (Week 4)

11. **Test with Multiple Clients**
- Cursor IDE
- Claude Desktop
- VS Code with MCP extension
- Direct HTTP calls

12. **Add Error Handling**
- Graceful failures
- Helpful error messages
- Validation of inputs

13. **Performance Optimization**
- Cache board state
- Lazy loading of resources
- Efficient file operations

## Configuration Examples

### Cursor (`.cursor/mcp.json`)
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

### Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`)
```json
{
    "mcpServers": {
        "kanbanger": {
            "command": "python",
            "args": ["-m", "kanbanger_mcp"],
            "env": {
                "KANBANGER_WORKSPACE": "/path/to/your/project",
                "GITHUB_TOKEN": "your_token_here",
                "GITHUB_REPO": "owner/repo",
                "GITHUB_PROJECT_NUMBER": "6"
            }
        }
    }
}
```

### HTTP Server (for web clients)
```bash
# Start MCP server on HTTP
python -m kanbanger_mcp --transport streamable-http --port 8000

# Configure client
{
    "mcpServers": {
        "kanbanger": {
            "url": "http://localhost:8000/sse"
        }
    }
}
```

## Benefits of MCP Integration

### For LLMs
1. **Explicit Tool Visibility** - Tools listed in available tools, not hidden in docs
2. **Structured Parameters** - Type-safe, validated inputs
3. **Real-time State** - Resources always show current board state
4. **Context Injection** - Prompts remind LLM about kanban
5. **Cross-Client** - Works in Cursor, Claude Desktop, VS Code, etc.

### For Users
1. **Consistent Experience** - Same tools across all AI assistants
2. **Less Configuration** - MCP handles connection details
3. **Better Errors** - Structured error responses
4. **Discoverability** - Tools self-document
5. **Portability** - Config travels with project

### For Kanbanger Project
1. **Modern Architecture** - Aligns with MCP ecosystem
2. **Wider Adoption** - Works with any MCP client
3. **Better Enforcement** - Tools are explicit, not optional
4. **Extensibility** - Easy to add new tools/resources
5. **Professional** - Industry-standard protocol

## Success Metrics

- [ ] MCP server runs successfully with stdio transport
- [ ] All 6 core tools implemented and tested
- [ ] All 4 resources return correct data
- [ ] 3 prompts provide useful context
- [ ] Works in Cursor IDE
- [ ] Works in Claude Desktop
- [ ] Documentation complete
- [ ] Distribution package updated
- [ ] Setup wizard includes MCP configuration
- [ ] Zero breaking changes to existing CLI

## Next Steps

1. **Immediate:** Create `kanbanger_mcp/` directory structure
2. **Today:** Implement basic server with 1-2 tools
3. **This Week:** Complete all tools and resources
4. **Next Week:** Documentation and distribution
5. **Following Week:** Testing and refinement

## Questions to Resolve

1. **Package Distribution:** Publish to npm for easy `npx` usage?
2. **Authentication:** How to handle GitHub token in MCP context?
3. **Multi-Board:** Support multiple kanban files in one workspace?
4. **Permissions:** Should some tools require confirmation?
5. **Caching:** How aggressive should resource caching be?

## References

- **MCP-Use Python Docs:** https://github.com/mcp-use/mcp-use
- **Context7 MCP Guide:** https://context7.com/docs/mcp
- **Cursor MCP Docs:** https://docs.cursor.com/context/model-context-protocol
- **fckgit Example:** https://github.com/earlyprototype/fckgit/.cursor/mcp.json
- **thought-bubble MCP:** https://github.com/earlyprototype/thought_bubble/tree/master/thought_bubble_mcp

---

**Status:** Ready to implement  
**Priority:** High (significantly improves LLM integration)  
**Estimated Effort:** 3-4 weeks part-time  
**Dependencies:** None (additive feature)
