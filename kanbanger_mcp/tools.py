"""
Kanbanger MCP Tools

Callable functions that LLMs can use to interact with kanban boards.
"""

import os
import json
import subprocess
from typing import Optional
from mcp_use.server import MCPServer


def get_workspace() -> str:
    """Get the current workspace directory."""
    return os.getenv("KANBANGER_WORKSPACE", os.getcwd())


def get_kanban_path() -> str:
    """Get the path to the kanban board file."""
    return os.path.join(get_workspace(), "_kanban.md")


def register_tools(server: MCPServer):
    """Register all tools with the MCP server."""
    
    @server.tool()
    def add_task(title: str, column: str = "TODO", description: str = "") -> str:
        """
        Add a new task to the kanban board.
        
        Args:
            title: Task title (required, should be concise and action-oriented)
            column: Target column - must be one of: BACKLOG, TODO, DOING, DONE (default: TODO)
            description: Optional task description for additional context
        
        Returns:
            Success message or error description
        
        Example:
            add_task("Implement user authentication", "TODO", "Add JWT-based auth system")
        """
        kanban_path = get_kanban_path()
        
        if not os.path.exists(kanban_path):
            return f"Error: Kanban board not found at {kanban_path}"
        
        # Validate column
        valid_columns = ["BACKLOG", "TODO", "DOING", "DONE"]
        if column not in valid_columns:
            return f"Error: Invalid column '{column}'. Must be one of: {', '.join(valid_columns)}"
        
        # Read current board
        try:
            with open(kanban_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return f"Error reading kanban board: {str(e)}"
        
        # Find column section
        column_header = f"## {column}"
        if column_header not in content:
            return f"Error: Column '{column}' not found in kanban board"
        
        # Build task line
        task_line = f"*   [ ] {title}"
        if description:
            task_line += f" - {description}"
        
        # Insert after column header
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.strip() == column_header:
                lines.insert(i + 1, task_line)
                break
        
        # Write back
        try:
            with open(kanban_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
        except Exception as e:
            return f"Error writing kanban board: {str(e)}"
        
        return f"Successfully added task '{title}' to {column}"
    
    @server.tool()
    def move_task(title: str, from_column: str, to_column: str) -> str:
        """
        Move a task from one column to another.
        
        Args:
            title: Exact title of the task to move
            from_column: Source column (BACKLOG, TODO, DOING, DONE)
            to_column: Destination column (BACKLOG, TODO, DOING, DONE)
        
        Returns:
            Success message or error description
        
        Example:
            move_task("Implement user authentication", "TODO", "DOING")
        
        Note:
            - Task title must match exactly
            - Moving to DONE automatically marks task as completed [x]
            - Moving from DONE back unchecks the task [ ]
        """
        kanban_path = get_kanban_path()
        
        if not os.path.exists(kanban_path):
            return f"Error: Kanban board not found at {kanban_path}"
        
        # Validate columns
        valid_columns = ["BACKLOG", "TODO", "DOING", "DONE"]
        if from_column not in valid_columns:
            return f"Error: Invalid from_column '{from_column}'"
        if to_column not in valid_columns:
            return f"Error: Invalid to_column '{to_column}'"
        
        try:
            with open(kanban_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return f"Error reading kanban board: {str(e)}"
        
        lines = content.split('\n')
        
        # Find the task in from_column
        task_line = None
        task_index = None
        in_from_column = False
        
        for i, line in enumerate(lines):
            if line.strip() == f"## {from_column}":
                in_from_column = True
                continue
            elif line.strip().startswith("## ") and in_from_column:
                break  # Entered next column
            
            if in_from_column and title in line and line.strip().startswith("*"):
                task_line = line
                task_index = i
                break
        
        if task_line is None:
            return f"Error: Task '{title}' not found in {from_column}"
        
        # Remove from source column
        lines.pop(task_index)
        
        # Update checkbox based on destination
        if to_column == "DONE":
            task_line = task_line.replace("[ ]", "[x]")
        else:
            task_line = task_line.replace("[x]", "[ ]")
        
        # Find destination column and insert
        for i, line in enumerate(lines):
            if line.strip() == f"## {to_column}":
                lines.insert(i + 1, task_line)
                break
        
        # Write back
        try:
            with open(kanban_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
        except Exception as e:
            return f"Error writing kanban board: {str(e)}"
        
        return f"Successfully moved '{title}' from {from_column} to {to_column}"
    
    @server.tool()
    def delete_task(title: str, column: str) -> str:
        """
        Delete a task from the kanban board.
        
        Args:
            title: Exact title of the task to delete
            column: Column containing the task (BACKLOG, TODO, DOING, DONE)
        
        Returns:
            Success message or error description
        
        Example:
            delete_task("Old deprecated feature", "BACKLOG")
        
        Warning:
            This permanently removes the task from the local markdown file.
            Consider moving to DONE instead of deleting for record keeping.
        """
        kanban_path = get_kanban_path()
        
        if not os.path.exists(kanban_path):
            return f"Error: Kanban board not found at {kanban_path}"
        
        try:
            with open(kanban_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return f"Error reading kanban board: {str(e)}"
        
        lines = content.split('\n')
        
        # Find and remove the task
        task_found = False
        in_column = False
        
        for i, line in enumerate(lines):
            if line.strip() == f"## {column}":
                in_column = True
                continue
            elif line.strip().startswith("## ") and in_column:
                break
            
            if in_column and title in line and line.strip().startswith("*"):
                lines.pop(i)
                task_found = True
                break
        
        if not task_found:
            return f"Error: Task '{title}' not found in {column}"
        
        # Write back
        try:
            with open(kanban_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
        except Exception as e:
            return f"Error writing kanban board: {str(e)}"
        
        return f"Successfully deleted task '{title}' from {column}"
    
    @server.tool()
    def list_tasks(column: Optional[str] = None) -> str:
        """
        List tasks from the kanban board.
        
        Args:
            column: Optional column filter (BACKLOG, TODO, DOING, DONE).
                   If not provided, returns tasks from all columns.
        
        Returns:
            JSON string with task information
        
        Example:
            list_tasks()  # All tasks
            list_tasks("DOING")  # Only tasks in DOING column
        
        Output format:
            {
                "BACKLOG": ["Task 1", "Task 2"],
                "TODO": ["Task 3"],
                "DOING": ["Task 4"],
                "DONE": ["Task 5", "Task 6"]
            }
        """
        kanban_path = get_kanban_path()
        
        if not os.path.exists(kanban_path):
            return json.dumps({"error": f"Kanban board not found at {kanban_path}"})
        
        try:
            with open(kanban_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return json.dumps({"error": f"Error reading kanban board: {str(e)}"})
        
        lines = content.split('\n')
        tasks = {}
        current_column = None
        
        for line in lines:
            if line.strip().startswith("## "):
                current_column = line.strip()[3:].strip()
                if current_column not in tasks:
                    tasks[current_column] = []
            elif current_column and line.strip().startswith("*"):
                # Extract task title (remove checkbox and description)
                task_text = line.strip()[1:].strip()  # Remove *
                if task_text.startswith("[ ]") or task_text.startswith("[x]"):
                    task_text = task_text[3:].strip()  # Remove checkbox
                # Remove description if present
                if " - " in task_text:
                    task_text = task_text.split(" - ")[0].strip()
                tasks[current_column].append(task_text)
        
        # Filter by column if specified
        if column:
            if column in tasks:
                return json.dumps({column: tasks[column]}, indent=2)
            else:
                return json.dumps({column: []}, indent=2)
        
        return json.dumps(tasks, indent=2)
    
    @server.tool()
    def sync_to_github(dry_run: bool = False) -> str:
        """
        Sync the kanban board to GitHub Projects V2.
        
        Args:
            dry_run: If True, shows what would be synced without making changes (default: False)
        
        Returns:
            Sync results or error message
        
        Example:
            sync_to_github(dry_run=True)  # Preview changes
            sync_to_github()  # Actually sync
        
        Requirements:
            - GITHUB_TOKEN environment variable must be set
            - GITHUB_REPO environment variable must be set
            - GITHUB_PROJECT_NUMBER environment variable (optional, will auto-detect)
        
        Note:
            This creates/updates/archives draft issues in the GitHub Project.
            Local _kanban.md is the source of truth.
        """
        workspace = get_workspace()
        kanban_path = get_kanban_path()
        
        if not os.path.exists(kanban_path):
            return f"Error: Kanban board not found at {kanban_path}"
        
        # Check for required environment variables
        if not os.getenv("GITHUB_TOKEN"):
            return "Error: GITHUB_TOKEN environment variable not set"
        if not os.getenv("GITHUB_REPO"):
            return "Error: GITHUB_REPO environment variable not set"
        
        # Build command
        cmd = ["python", "-m", "sync_kanban", kanban_path]
        if dry_run:
            cmd.append("--dry-run")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=workspace,
                encoding='utf-8'
            )
            
            if result.returncode == 0:
                mode = "preview" if dry_run else "complete"
                return f"Sync {mode}:\n\n{result.stdout}"
            else:
                return f"Sync failed:\n\n{result.stderr}"
        except Exception as e:
            return f"Error running sync: {str(e)}"
    
    @server.tool()
    def get_sync_status() -> str:
        """
        Get the current GitHub sync status.
        
        Returns:
            JSON string with sync status information
        
        Output format:
            {
                "synced_tasks": 15,
                "state_file": "/path/to/.kanban.json",
                "last_sync": "2026-01-21T02:30:00Z"  (if available)
            }
        
        Note:
            This reads the .kanban.json state file which tracks
            the mapping between local tasks and GitHub Project items.
        """
        workspace = get_workspace()
        state_path = os.path.join(workspace, ".kanban.json")
        
        if not os.path.exists(state_path):
            return json.dumps({
                "synced_tasks": 0,
                "state_file": "not found",
                "message": "No sync state found. Run sync_to_github() first."
            }, indent=2)
        
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            return json.dumps({
                "synced_tasks": len(state.get("items", {})),
                "state_file": state_path,
                "github_items": list(state.get("items", {}).keys())
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "error": f"Error reading sync state: {str(e)}"
            }, indent=2)
