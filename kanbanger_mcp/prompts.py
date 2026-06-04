"""
Kanbanger MCP Prompts

Context injection and guidance for LLMs working with kanban boards.
"""

from mcp.server.fastmcp import FastMCP


def register_prompts(server: FastMCP):
    """Register all prompts with the MCP server."""
    
    @server.prompt(
        name="kanban_awareness",
        title="Kanban Board Awareness",
        description="Reminds LLM to check and update the kanban board during work"
    )
    def kanban_awareness_prompt() -> str:
        """Inject kanban awareness into LLM context."""
        return """# Kanban Board Management

This project uses a kanban board (_kanban.md) for task tracking and syncs with GitHub Projects V2.

## Available MCP Tools:
- `add_task(title, column, description)` - Add new task to board
- `move_task(title, from_column, to_column)` - Move task between columns
- `delete_task(title, column)` - Remove task from board
- `list_tasks(column)` - View tasks (all or by column)
- `sync_to_github(dry_run)` - Sync board to GitHub Projects
- `get_sync_status()` - Check GitHub sync state

## Available MCP Resources:
- `kanban://current-board` - View current board markdown
- `kanban://stats` - Task counts and distribution
- `kanban://sync-status` - GitHub sync information
- `kanban://config` - Current configuration

## Workflow Best Practices:
1. **Before starting work:** Check current board state (kanban://current-board)
2. **When planning:** Add tasks to BACKLOG or TODO
3. **When starting:** Move task to DOING (limit 1-2 tasks in progress)
4. **When AI-complete:** Move task to REVIEW (a human approves REVIEW -> DONE; never move to DONE yourself)
5. **Periodically:** Sync to GitHub with sync_to_github()

## Column Definitions:
- **BACKLOG**: Future ideas, features, and tasks not yet prioritized
- **TODO**: Ready to start, prioritized tasks
- **DOING**: Currently in progress (keep this small - focus!)
- **REVIEW**: AI-completed work awaiting human approval
- **DONE**: Completed tasks, human-approved (keep for record)

## Task Format:
- Use clear, action-oriented titles
- Add descriptions for context when needed
- Keep titles concise (under 60 characters)
- Use imperative mood ("Add feature" not "Adding feature")

## When to Update Board:
- Starting a new task → move to DOING
- Finishing AI work → move to REVIEW (a human approves REVIEW → DONE)
- Planning new work → add to BACKLOG or TODO
- Changing priorities → reorder or move tasks
- After significant progress → sync to GitHub

Remember: The kanban board is the source of truth for project status!"""
    
    @server.prompt(
        name="task_planning",
        title="Task Planning Assistant",
        description="Help break down goals into actionable kanban tasks"
    )
    def task_planning_prompt(goal: str) -> str:
        """Help LLM plan and break down tasks for a goal."""
        return f"""# Task Planning for: {goal}

Break down this goal into specific, actionable tasks suitable for the kanban board.

## Planning Guidelines:
1. **Specific**: Each task should have a clear, measurable outcome
2. **Actionable**: Start with action verbs (Implement, Create, Fix, Update, etc.)
3. **Sized Appropriately**: Tasks should be completable in a reasonable timeframe
4. **Independent**: Minimize dependencies where possible
5. **Testable**: Clear criteria for "done"

## Task Breakdown Process:
1. Identify major components or phases
2. Break each component into concrete tasks
3. Estimate complexity (S/M/L)
4. Identify dependencies
5. Determine appropriate starting column

## Output Format:
For each task, provide:
- **Title**: Concise, action-oriented (e.g., "Implement user login API")
- **Description**: What needs to be done and why
- **Column**: BACKLOG (future) or TODO (ready now)
- **Complexity**: S (small), M (medium), L (large)
- **Dependencies**: Other tasks that must complete first (if any)

## After Planning:
Use the `add_task()` tool to add each task to the board:
```
add_task("Task title", "TODO", "Task description")
```

Now, break down the goal "{goal}" into tasks:"""
    
    @server.prompt(
        name="daily_standup",
        title="Daily Standup Review",
        description="Review current board state and plan daily work"
    )
    def daily_standup_prompt() -> str:
        """Generate a daily standup / review prompt."""
        return """# Daily Standup Review

Let's review the current kanban board and plan today's work.

## Review Process:
1. **Check DOING column** (kanban://current-board)
   - What's currently in progress?
   - Should any tasks move to DONE?
   - Are any tasks blocked?

2. **Review TODO column**
   - What's the highest priority?
   - What can be started today?
   - Are tasks still relevant?

3. **Check DONE column**
   - What was completed recently?
   - Should anything be synced to GitHub?

4. **Plan Today**
   - What will you work on?
   - Move selected task(s) to DOING
   - Limit work in progress (1-2 tasks max)

## Questions to Consider:
- Are there any blockers?
- Do any tasks need to be broken down further?
- Is the board up to date?
- When was the last GitHub sync?

## Actions:
1. Use `list_tasks()` to see current state
2. Use `move_task()` to update task positions
3. Use `add_task()` if new work identified
4. Use `sync_to_github()` if board has changed significantly

Let's start by checking the current board state:"""
    
    @server.prompt(
        name="review_gate_etiquette",
        title="REVIEW Gate Etiquette",
        description="Teach AI agents the propose_done / approve_done / "
                    "reject_review contract"
    )
    def review_gate_etiquette_prompt() -> str:
        """Inject REVIEW-gate etiquette into LLM context."""
        return """# REVIEW Gate Etiquette

This board uses a REVIEW column as a gate between AI-completed work
and DONE. REVIEW is part of the canonical 5-column schema (BACKLOG
-> TODO -> DOING -> REVIEW -> DONE) — the platform guarantees it
exists on every board. The contract has three primitives:

## When you finish a task

Call `propose_done(title)` to move the task from DOING to REVIEW.
This signals "I think this is done; please review."

Do NOT call `move_task(title, from_column="DOING", to_column="DONE")`
directly. That path bypasses the gate and is reserved for the
board's human or PM reviewer via `approve_done` after they have
reviewed the work.

## What happens next

The reviewer (human or PM session) inspects the work and calls
either:

- `approve_done(title)` — the work is acceptable; the task moves
  from REVIEW to DONE.
- `reject_review(title, reason)` — the work needs changes. Pattern
  C two-entry rejection:
  1. The original task moves REVIEW -> DONE with a REJECTED
     annotation in its description: `[x] <title> - REJECTED:
     <reason>; rework: Rework: <title>`. This preserves the
     shipped-history.
  2. A NEW task `Rework: <title>` is created at the top of TODO
     with description `Reason: <reason>; Original task: <title>`.
     This new task is the actionable work going forward.

## When you receive a rejection

A new task titled `Rework: <your original title>` will appear at
the top of TODO. Its description carries the reviewer's reason
and a pointer back to the original task. The original task is
now in DONE (with REJECTED annotation) — read it for context, but
do your work against the Rework task. When the Rework is ready
for re-review, call `propose_done("Rework: <original title>")` —
the Rework task is the unit being reviewed this time.

## Why the gate exists

The gate enforces a single principle: AI-completed work is not
durable until a human or PM has acknowledged it. The REVIEW column
is the visible queue of "work awaiting acknowledgement." Skipping
the gate produces silent drift between what the board says is done
and what has actually been validated.

The `Rework:` prefix on rejected work IS the priority signal —
no separate priority column or flag needed. Rejected work is
visible, actionable, and linked back to the shipped record.

## Quick reference

- Finish a task -> `propose_done(title)`
- Reviewer approves -> `approve_done(title)`
- Reviewer rejects -> `reject_review(title, reason)` (reason
  required — empty rejects fail with `missing_reason`)
- After rejection, look in TODO for `Rework: <your title>` — that
  is your next task. The original lives in DONE with the REJECTED
  annotation for reference.
- Never -> `move_task(title, "DOING", "DONE")` directly

This is the contract. Follow it without asking the user about
DONE markings — the platform's canonical schema enforces the gate
for you."""

    @server.prompt(
        name="github_sync_check",
        title="GitHub Sync Reminder",
        description="Remind to sync board with GitHub Projects"
    )
    def github_sync_prompt() -> str:
        """Remind about GitHub synchronization."""
        return """# GitHub Sync Check

The kanban board should be regularly synced with GitHub Projects to keep the team informed.

## Check Sync Status:
1. Use `get_sync_status()` to see last sync info
2. Review `kanban://sync-status` resource
3. Check if local board has unsync changes

## When to Sync:
- After completing multiple tasks
- Before end of day
- After significant planning changes
- When team needs visibility

## Sync Process:
1. **Preview first**: `sync_to_github(dry_run=True)`
   - Review what will be created/updated/archived
   - Verify changes look correct

2. **Actual sync**: `sync_to_github()`
   - Creates draft issues in GitHub Project
   - Updates existing items
   - Archives deleted tasks

3. **Verify**: Check GitHub Project board online
   - Ensure all tasks appear correctly
   - Verify status columns match

## Important Notes:
- Local _kanban.md is the source of truth
- GitHub Project is a synchronized view
- Changes made in GitHub won't sync back (one-way sync)
- Draft issues won't clutter your repository's Issues tab

Check sync status now:"""
