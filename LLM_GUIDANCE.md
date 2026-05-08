# LLM Guidance for Kanban Management

This document provides guidance for Large Language Models (LLMs) to help users create and manage markdown kanban files for kanban-project-sync.

## Purpose

Enable LLMs to:
- Create well-formatted kanban boards from user requests
- Add/remove/move tasks intelligently
- Maintain proper markdown structure
- Suggest task organization and prioritization

## Markdown Kanban Format

### Basic Structure

```markdown
# [Optional: Board Title]

## BACKLOG
*   [ ] Task that hasn't been started
*   [ ] Another backlog item

## TODO
*   [ ] Task ready to be picked up
*   [ ] High priority task

## DOING
*   [ ] Task currently being worked on

## DONE
*   [x] Completed task (checked box)
*   [x] Another finished item
```

### Strict Requirements

1. **Column Headers:** Must be level 2 headers (`## `)
2. **Task Format:** Must use `*   [ ]` or `*   [x]` (asterisk + 3 spaces + checkbox)
3. **Status Indicators:**
   - Unchecked: `[ ]` for active tasks
   - Checked: `[x]` for completed tasks (only in DONE column)
4. **Column Names:** Case-insensitive but must match:
   - `BACKLOG` → Maps to "Backlog" status
   - `TODO` or `TO DO` → Maps to "Todo" status
   - `DOING` or `IN PROGRESS` → Maps to "InProgress" status
   - `DONE` or `COMPLETE` → Maps to "Done" status

### Optional Elements

- Numbered headers: `## 1. BACKLOG` (numbers ignored)
- Board title: `# Project Kanban Board` at top
- Empty columns: Allowed
- Blank lines: Ignored

## LLM Instructions

### When User Says: "Create a kanban board for [project]"

1. **Understand the context:** Ask clarifying questions about:
   - What tasks need to be tracked?
   - What's the priority?
   - What's the current status of work?

2. **Generate board:** Create with realistic task distribution:
   ```markdown
   # [Project Name] Kanban

   ## BACKLOG
   *   [ ] Future tasks
   *   [ ] Nice-to-have features

   ## TODO
   *   [ ] High priority items
   *   [ ] Ready to start

   ## DOING
   *   [ ] Currently active (1-3 items max for focus)

   ## DONE
   *   [x] Recently completed
   ```

3. **Best practices:**
   - Limit DOING to 1-3 items (avoid multitasking)
   - Prioritize TODO by putting important tasks first
   - Keep tasks specific and actionable
   - Use clear, concise language

### When User Says: "Add task to [column]"

```markdown
## [COLUMN NAME]
*   [ ] Existing task
*   [ ] New task added here  ← Add at bottom of section
```

### When User Says: "Move [task] to [column]"

1. Find the task by title (exact or fuzzy match)
2. Remove from current column
3. Add to target column
4. Update checkbox status:
   - Moving TO Done → Change `[ ]` to `[x]`
   - Moving FROM Done → Change `[x]` to `[ ]`

### When User Says: "Mark [task] as done"

1. Find task in any column
2. Move to DONE section
3. Change checkbox to `[x]`

### When User Says: "Delete [task]"

Simply remove the line from the markdown file.

## Task Writing Guidelines

### Good Task Titles

✅ **Specific and actionable:**
- "Implement user authentication API"
- "Fix bug in payment processing"
- "Write documentation for deployment"
- "Review PR #123"

✅ **Clear scope:**
- "Design database schema for users table"
- "Add error handling to file upload"

### Poor Task Titles

❌ **Too vague:**
- "Work on authentication"
- "Fix stuff"
- "Documentation"

❌ **Too broad:**
- "Build entire frontend"
- "Implement all features"

❌ **Not actionable:**
- "Think about design"
- "Maybe refactor later"

## Example Interactions

### Example 1: Create Board

**User:** "Create a kanban board for my web scraper project"

**LLM Response:**
```markdown
# Web Scraper Kanban

## BACKLOG
*   [ ] Add support for JavaScript-rendered pages
*   [ ] Implement rate limiting
*   [ ] Add proxy rotation
*   [ ] Create CLI interface

## TODO
*   [ ] Set up project structure
*   [ ] Implement basic HTTP requests
*   [ ] Add HTML parsing with BeautifulSoup

## DOING
*   [ ] Design data extraction pipeline

## DONE
*   [x] Research scraping libraries
*   [x] Define project requirements
```

### Example 2: Add Task

**User:** "Add 'implement retry logic' to TODO"

**LLM:** Reads current file, adds to TODO section:
```markdown
## TODO
*   [ ] Set up project structure
*   [ ] Implement basic HTTP requests
*   [ ] Add HTML parsing with BeautifulSoup
*   [ ] Implement retry logic
```

### Example 3: Move Task

**User:** "Move 'Design data extraction pipeline' to Done"

**LLM:** 
1. Find in DOING: `*   [ ] Design data extraction pipeline`
2. Remove from DOING
3. Add to DONE with checked box:
```markdown
## DOING

## DONE
*   [x] Research scraping libraries
*   [x] Define project requirements
*   [x] Design data extraction pipeline
```

### Example 4: Reorganize

**User:** "The TODO list is too long, move some items to backlog"

**LLM:** Analyze priorities, move lower-priority items:
```markdown
## BACKLOG
*   [ ] Add support for JavaScript-rendered pages
*   [ ] Implement rate limiting
*   [ ] Add proxy rotation
*   [ ] Create CLI interface
*   [ ] Add HTML parsing with BeautifulSoup  ← Moved

## TODO
*   [ ] Set up project structure
*   [ ] Implement basic HTTP requests
```

## Integration with Sync Tool

After editing the kanban file, remind users to sync:

```bash
# Preview changes
kanban-sync _kanban.md --dry-run

# Apply changes to GitHub
kanban-sync _kanban.md
```

## Common Patterns

### Sprint Planning
```markdown
## BACKLOG
*   [ ] All discovered work

## TODO
*   [ ] Sprint goals (prioritized)
*   [ ] High value items

## DOING
*   [ ] Current sprint work (WIP limit: 3)

## DONE
*   [x] Completed this sprint
```

### Bug Tracking
```markdown
## BACKLOG
*   [ ] Minor bugs
*   [ ] Known issues

## TODO
*   [ ] P1: Critical bugs
*   [ ] P2: High priority bugs

## DOING
*   [ ] Currently investigating

## DONE
*   [x] Fixed and verified
```

### Feature Development
```markdown
## BACKLOG
*   [ ] Feature ideas
*   [ ] User requests

## TODO
*   [ ] Approved features
*   [ ] Next milestone items

## DOING
*   [ ] In development

## DONE
*   [x] Shipped features
```

## Validation Checklist

Before finalizing edits, verify:

- [ ] All columns use `## ` headers
- [ ] All tasks use `*   [ ]` or `*   [x]` format
- [ ] Column names are BACKLOG, TODO, DOING, or DONE
- [ ] Only DONE tasks have `[x]` checkboxes
- [ ] Task titles are clear and actionable
- [ ] No duplicate task titles (causes sync issues)

## Advanced: Batch Operations

When user requests multiple changes:

**User:** "I finished these three tasks: task A, task B, task C"

**LLM:** Atomically move all three:
1. Find each task
2. Move to DONE
3. Mark as complete
4. Present updated file

## Error Prevention

### Avoid These Mistakes

❌ **Wrong checkbox format:**
```markdown
* [ ] Task   ← Missing spaces
*  [ ] Task  ← Wrong number of spaces
* [x ] Task  ← Space in wrong place
```

✅ **Correct format:**
```markdown
*   [ ] Task
*   [x] Task
```

❌ **Wrong header level:**
```markdown
# TODO        ← Level 1 (too high)
### TODO      ← Level 3 (too low)
```

✅ **Correct:**
```markdown
## TODO
```

## Tips for LLMs

1. **Preserve existing content:** When editing, don't remove tasks unless explicitly asked
2. **Maintain order:** Keep chronological order in DONE (newest at bottom)
3. **Ask for clarification:** If task name is ambiguous, confirm with user
4. **Suggest improvements:** Offer to break down large tasks or reorganize
5. **Remind about sync:** After edits, remind user to run `kanban-sync`

## Sample Prompts for Users

Share these with users to get the most from LLM assistance:

- "Create a kanban board for my [project type] project"
- "Add these tasks to my backlog: [list]"
- "I finished [task], mark it as done"
- "Move [task] from TODO to DOING"
- "Reorganize my TODO list by priority"
- "Break down [large task] into smaller tasks"
- "Show me what tasks are currently in progress"
- "Suggest what I should work on next"

## Tool Integration

LLMs can help users by:
1. **Creating/editing** the markdown file
2. **Explaining** what will happen when synced
3. **Previewing** the dry-run output
4. **Troubleshooting** sync errors

**Example workflow:**
```
User: "Add task X to TODO"
LLM:  [Edits _kanban.md]
      "Added! Run 'kanban-sync _kanban.md' to sync to GitHub."
User: "Can you preview what will happen?"
LLM:  [Runs dry-run]
      "This will create 1 new task in the Todo column on GitHub."
```

## Conclusion

With proper guidance, LLMs can be powerful kanban management assistants, making it natural to maintain project boards through conversation while keeping everything in sync with GitHub Projects.
