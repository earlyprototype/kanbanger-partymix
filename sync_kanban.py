"""
kanban-project-sync

Sync a markdown kanban board to GitHub Projects.
"""
import re
import os
import sys
import json
import shutil
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from kanban_io import (
    atomic_write_json,
    kanban_lock,
    parse_task_title_with_description,
    read_board_key,
)

# Load environment variables from .env file if it exists.
# override=True: the project's `.env` is the authoritative target for
# this sync run. Without it, a shell-level export (e.g. a stale
# GITHUB_REPO=owner/other-project from another workspace's profile
# script) silently shadows the `.env` value and routes the sync to
# the wrong project — items get written into another repo's Project
# instead of the intended one, with no error surfaced.
# find_dotenv(usecwd=True): the default `find_dotenv()` walks upward
# from the *caller module's file location* (i.e. this file's
# directory), not from the user's CWD. When kanban-sync is invoked
# from a target project, that lookup can latch onto a rogue
# parent-of-source-directory `.env` (e.g. ~/Desktop/AI/.env) and the
# target project's `.env` is never considered. usecwd=True makes the
# search start at os.getcwd() so the CWD-closest `.env` wins.
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=True)
except ImportError:
    pass  # python-dotenv not installed, skip


# GitHub GraphQL endpoint
GITHUB_API = "https://api.github.com/graphql"

# R8: state file schema version. Persisted in .kanban.json so future
# kanbanger versions can detect and migrate older state shapes.
# v0 = pre-R8 (no field present); v1 = current. v0 and v1 are
# structurally identical, so v0 files self-upgrade on next save.
SCHEMA_VERSION = 1


# E1: typed exceptions raised by the sync_kanban library so callers
# (CLI entry-point, MCP subprocess wrapper, future direct importers)
# can distinguish failure categories instead of pattern-matching on
# stdout. Library code raises; CLI catches at __main__.
class KanbangerError(Exception):
    """Base class for all kanbanger library errors."""


class GitHubAPIError(KanbangerError):
    """A GitHub GraphQL/HTTP call failed: HTTP non-200, GraphQL
    error array, or a missing field that the GraphQL contract
    promised."""


class ProjectNotFoundError(KanbangerError):
    """No GitHub Project matched the requested repo/number."""


class ConfigurationError(KanbangerError):
    """Required configuration is missing or invalid: env var, file
    path, or runtime dependency."""


class LocalBoard:
    """Handles parsing of markdown kanban files."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.tasks: Dict[str, List[Dict]] = {}
    
    def parse(self) -> Dict[str, List[Dict]]:
        """Parse a markdown kanban file and return tasks by column.

        D4: same-title rows in the same section are deduped (first
        occurrence wins) with a stderr warning. Without dedup the
        sync path would create duplicate GitHub items for what looks
        like one logical task to the user.

        D8: dedup uses the stripped title (text before any ` - desc`
        separator) computed via the shared
        `kanban_io.parse_task_title_with_description` helper — same
        semantics as the MCP-tools side. Without the shared helper the
        two parsers drifted and `* [ ] X` + `* [ ] X - extra` pushed
        as two separate GH items even though MCP-tools dedup'd them.
        The pushed `title` field still carries the full post-checkbox
        text so the description survives to GitHub on the first
        occurrence; only the dedup key is the stripped form.
        """
        with open(self.file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        tasks = {}
        seen_per_section: Dict[str, set] = {}
        current_section = None

        # Detect section headers (## N. TITLE or ## TITLE)
        section_pattern = re.compile(r'^##\s+(?:\d+\.\s+)?(.+)', re.IGNORECASE)
        task_pattern = re.compile(r'^\*\s+\[([ xX])\]\s+(.+)')

        for line in content.split('\n'):
            # Check for section header
            section_match = section_pattern.match(line.strip())
            if section_match:
                section_name = section_match.group(1).strip()
                # Normalize common section names
                normalized = section_name.upper()
                if 'BACKLOG' in normalized:
                    current_section = 'Backlog'
                elif 'TO DO' in normalized or 'TODO' in normalized:
                    current_section = 'Todo'
                elif 'DOING' in normalized or 'IN PROGRESS' in normalized:
                    current_section = 'InProgress'
                elif 'REVIEW' in normalized:
                    current_section = 'Review'
                elif 'DONE' in normalized or 'COMPLETE' in normalized:
                    current_section = 'Done'
                else:
                    current_section = section_name

                tasks.setdefault(current_section, [])
                seen_per_section.setdefault(current_section, set())
                continue

            # Check for task item
            if current_section:
                task_match = task_pattern.match(line.strip())
                if task_match:
                    is_done = task_match.group(1).lower() == 'x'
                    title = task_match.group(2).strip()
                    parsed = parse_task_title_with_description(line)
                    dedup_key = parsed[0] if parsed is not None else title
                    if dedup_key in seen_per_section[current_section]:
                        print(
                            f"Warning: duplicate task title in section "
                            f"'{current_section}': '{dedup_key}'. Keeping "
                            f"first occurrence; dropping subsequent "
                            f"duplicate to prevent duplicate GitHub items "
                            f"on sync.",
                            file=sys.stderr,
                        )
                        continue
                    seen_per_section[current_section].add(dedup_key)
                    tasks[current_section].append({
                        'title': title,
                        'done': is_done
                    })

        self.tasks = tasks
        return tasks


class StateManager:
    """Manages the .kanban.json sidecar file for state tracking."""
    
    def __init__(self, kanban_file_path: str):
        self.kanban_file = Path(kanban_file_path)
        self.state_file = self.kanban_file.parent / ".kanban.json"
        self.state = {
            "schema_version": SCHEMA_VERSION,
            "repo_node_id": None,
            "project_id": None,
            # ADR 0002: the minted board key this state belongs to. None
            # until the first sync against a keyed board adopts it.
            "board_key": None,
            "tasks": {}
        }

    def load(self) -> Dict:
        """Load state from .kanban.json if it exists.

        R7: on a corrupt JSON parse, copy the bad file aside (preserving
        it for postmortem) and reset to an empty default state. Lets the
        tool keep running rather than crashing on a partial write or
        manual edit; the user loses sync history but no further damage
        accumulates. Recovery via markdown-rebuild is deferred (would
        warrant its own audit item).
        """
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
            except json.JSONDecodeError as exc:
                timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
                backup_path = self.state_file.with_name(
                    f"{self.state_file.name}.corrupt-{timestamp}"
                )
                try:
                    shutil.copy2(self.state_file, backup_path)
                except Exception as copy_exc:
                    backup_note = (
                        f"backup attempt failed: {copy_exc!r}; "
                        f"original left in place at {self.state_file}"
                    )
                else:
                    backup_note = f"backed up to {backup_path}"
                print(
                    f"Warning: .kanban.json is corrupt "
                    f"({exc.msg} at line {exc.lineno} col {exc.colno}); "
                    f"{backup_note}. Resetting to empty state — sync "
                    f"history is lost; subsequent sync runs will treat "
                    f"the board as never-synced.",
                    file=sys.stderr,
                )
                self.state = {
                    "schema_version": SCHEMA_VERSION,
                    "repo_node_id": None,
                    "project_id": None,
                    "board_key": None,
                    "tasks": {},
                }
                return self.state
            # R8: backwards-compat. Pre-R8 state files have no
            # schema_version; v0 and v1 are structurally identical, so
            # silently upgrade in-memory (next save persists the field).
            loaded_version = self.state.get("schema_version")
            if loaded_version is None:
                self.state["schema_version"] = SCHEMA_VERSION
            elif loaded_version > SCHEMA_VERSION:
                print(
                    f"Warning: .kanban.json schema_version={loaded_version} "
                    f"is newer than this kanbanger version "
                    f"(supports v{SCHEMA_VERSION}). Reading what is "
                    f"recognised; unknown fields are preserved on save.",
                    file=sys.stderr,
                )
        return self.state
    
    def save(self):
        """Save state to .kanban.json. D1: atomic write under cross-process lock.

        Atomic write (R1 pattern via kanban_io.atomic_write_json) protects
        against torn state files; the workspace-relative lock (R2 pattern via
        kanban_io.kanban_lock) serializes against tools.py mutations and any
        concurrent sync writer. Together they form D1's transactional pair —
        both kanban_io.atomic_write_text (markdown, in tools.py) and
        atomic_write_json (state, here) write under the same lock file.
        """
        workspace = str(self.kanban_file.parent)
        with kanban_lock(workspace):
            atomic_write_json(str(self.state_file), self.state)
    
    def verify_board_key(self, board_key: Optional[str]) -> None:
        """Guard the sync state against a copied / swapped board (ADR 0002).

        `.kanban.json` pairs LOCAL task titles with REMOTE GitHub item ids.
        If the board file and the state file stop belonging to each other —
        the classic cause being a copied project directory, where both
        copies carry the SAME minted board key but only one of them should
        keep driving the original GitHub project items — silent
        cross-driving would corrupt the remote project. The minted board
        key makes the pairing checkable:

          * `board_key` is None (legacy unkeyed board): no check — old
            boards keep syncing exactly as before.
          * state has no recorded key yet: ADOPT the board's key (first
            sync against a keyed board, or migration of pre-key state);
            persisted by the next save().
          * recorded key == board key: the pair belongs together; no-op.
          * recorded key != board key: REFUSE with ConfigurationError —
            "sync state belongs to a different board (copied?)". The user
            deletes the stale .kanban.json (fresh sync state for this
            copy) or restores the right board.

        NOTE: this detects state-vs-board mismatch. The full duplication
        case — two faithful copies (same key, same state) BOTH syncing to
        one GitHub project from different folders — needs a remote-side
        marker to disambiguate and is out of scope here (flagged in issue
        #15 step 4).
        """
        if board_key is None:
            return
        recorded = self.state.get("board_key")
        if recorded is None:
            self.state["board_key"] = board_key
            return
        if recorded != board_key:
            raise ConfigurationError(
                f"sync state belongs to a different board (copied?): "
                f"{self.state_file} records board key {recorded}, but "
                f"{self.kanban_file} carries board key {board_key}. "
                f"If this project directory was copied, delete "
                f"{self.state_file} to start fresh sync state for this "
                f"copy (the original copy keeps the existing state); "
                f"otherwise restore the matching board file."
            )

    def get_item_id(self, task_title: str) -> Optional[str]:
        """Get the GitHub item ID for a task title."""
        return self.state["tasks"].get(task_title, {}).get("item_id")
    
    def get_status(self, task_title: str) -> Optional[str]:
        """Get the stored status for a task title."""
        return self.state["tasks"].get(task_title, {}).get("status")
    
    def update_task(self, task_title: str, item_id: str, status: str):
        """Update or add a task in the state."""
        self.state["tasks"][task_title] = {
            "item_id": item_id,
            "status": status
        }
    
    def remove_task(self, task_title: str):
        """Remove a task from the state."""
        if task_title in self.state["tasks"]:
            del self.state["tasks"][task_title]
    
    def set_project_info(self, repo_node_id: str, project_id: str):
        """Set the repository and project IDs."""
        self.state["repo_node_id"] = repo_node_id
        self.state["project_id"] = project_id


class GitHubClient:
    """Handles GitHub GraphQL API interactions."""
    
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        try:
            import requests
            self.requests = requests
        except ImportError:
            raise ConfigurationError(
                "requests not installed. Run: pip install requests"
            )
    
    def _query(self, query: str, variables: Dict) -> Dict:
        """Execute a GraphQL query."""
        response = self.requests.post(
            GITHUB_API,
            headers=self.headers,
            json={"query": query, "variables": variables}
        )
        
        if response.status_code != 200:
            raise GitHubAPIError(
                f"GitHub API returned status {response.status_code}: "
                f"{response.text}"
            )

        data = response.json()
        if "errors" in data:
            details = "\n".join(
                f"  - {error.get('message', str(error))}"
                for error in data["errors"]
            )
            raise GitHubAPIError(f"GraphQL errors:\n{details}")
        
        return data
    
    def get_repo_project(self, owner: str, repo_name: str, project_number: Optional[int] = None) -> Tuple[str, str, str, Dict]:
        """
        Get project information via repository lookup.
        Returns: (repo_node_id, project_id, status_field_id, status_options)
        """
        query = """
        query($owner: String!, $repo: String!) {
            repository(owner: $owner, name: $repo) {
                id
                projectsV2(first: 10) {
                    nodes {
                        id
                        number
                        title
                        fields(first: 20) {
                            nodes {
                                ... on ProjectV2SingleSelectField {
                                    id
                                    name
                                    options {
                                        id
                                        name
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        
        variables = {"owner": owner, "repo": repo_name}
        
        data = self._query(query, variables)
        
        repo = data["data"]["repository"]
        repo_node_id = repo["id"]
        projects = repo["projectsV2"]["nodes"]
        
        if not projects:
            raise ProjectNotFoundError(
                f"No projects found linked to {owner}/{repo_name}"
            )

        # Find the right project
        project = None
        if project_number:
            project = next((p for p in projects if p["number"] == project_number), None)
            if not project:
                raise ProjectNotFoundError(
                    f"Project #{project_number} not found"
                )
        else:
            project = projects[0]
            print(f"Info: Using project #{project['number']}: {project['title']}")

        project_id = project["id"]

        # Find the Status field
        status_field = None
        for field in project["fields"]["nodes"]:
            if field and field.get("name") in ["Status", "status"]:
                status_field = field
                break

        if not status_field:
            raise GitHubAPIError("No 'Status' field found in project")
        
        status_field_id = status_field["id"]
        status_options = {opt["name"]: opt["id"] for opt in status_field["options"]}
        
        return repo_node_id, project_id, status_field_id, status_options
    
    def get_project_items(self, project_id: str) -> List[Dict]:
        """Get all items from a project."""
        query = """
        query($projectId: ID!, $cursor: String) {
            node(id: $projectId) {
                ... on ProjectV2 {
                    items(first: 100, after: $cursor) {
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                        nodes {
                            id
                            content {
                                ... on DraftIssue {
                                    title
                                    body
                                }
                            }
                            fieldValues(first: 10) {
                                nodes {
                                    ... on ProjectV2ItemFieldSingleSelectValue {
                                        name
                                        field {
                                            ... on ProjectV2SingleSelectField {
                                                name
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        
        items = []
        cursor = None
        
        while True:
            variables = {"projectId": project_id, "cursor": cursor}
            data = self._query(query, variables)
            
            project = data["data"]["node"]
            page_items = project["items"]["nodes"]
            
            for item in page_items:
                if item.get("content") and item["content"].get("title"):
                    # Extract status
                    status = None
                    for field_value in item.get("fieldValues", {}).get("nodes", []):
                        if field_value and field_value.get("field", {}).get("name") == "Status":
                            status = field_value.get("name")
                            break
                    
                    items.append({
                        "id": item["id"],
                        "title": item["content"]["title"],
                        "status": status
                    })
            
            page_info = project["items"]["pageInfo"]
            if not page_info["hasNextPage"]:
                break
            cursor = page_info["endCursor"]
        
        return items
    
    def create_draft_issue(self, project_id: str, title: str, body: str = "") -> str:
        """Create a draft issue in the project. Returns the item ID."""
        mutation = """
        mutation($projectId: ID!, $title: String!, $body: String) {
            addProjectV2DraftIssue(input: {projectId: $projectId, title: $title, body: $body}) {
                projectItem {
                    id
                }
            }
        }
        """
        
        variables = {
            "projectId": project_id,
            "title": title,
            "body": body
        }
        
        data = self._query(mutation, variables)
        return data["data"]["addProjectV2DraftIssue"]["projectItem"]["id"]
    
    def update_item_status(self, project_id: str, item_id: str, status_field_id: str, status_option_id: str):
        """Update the status field of a project item."""
        mutation = """
        mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
            updateProjectV2ItemFieldValue(input: {
                projectId: $projectId,
                itemId: $itemId,
                fieldId: $fieldId,
                value: {singleSelectOptionId: $optionId}
            }) {
                projectV2Item {
                    id
                }
            }
        }
        """
        
        variables = {
            "projectId": project_id,
            "itemId": item_id,
            "fieldId": status_field_id,
            "optionId": status_option_id
        }
        
        self._query(mutation, variables)
    
    def archive_item(self, project_id: str, item_id: str):
        """Archive a project item."""
        mutation = """
        mutation($projectId: ID!, $itemId: ID!) {
            archiveProjectV2Item(input: {projectId: $projectId, itemId: $itemId}) {
                item {
                    id
                }
            }
        }
        """
        
        variables = {
            "projectId": project_id,
            "itemId": item_id
        }
        
        self._query(mutation, variables)


class Syncer:
    """Orchestrates the synchronization between local kanban and GitHub project."""
    
    def __init__(self, board: LocalBoard, state: StateManager, client: GitHubClient):
        self.board = board
        self.state = state
        self.client = client
        self.status_field_id = None
        self.status_options = {}
    
    def sync(self, repo: str, project_number: Optional[int] = None):
        """Perform the full synchronization."""
        owner, repo_name = repo.split('/')
        
        print(f"Parsing {self.board.file_path}...")
        local_tasks = self.board.parse()
        
        print(f"Loading state from {self.state.state_file}...")
        self.state.load()

        # ADR 0002 copied-board guard: refuse BEFORE any network call if
        # this state file belongs to a different board than the one on
        # disk (raises ConfigurationError). Unkeyed legacy boards skip the
        # check; a keyed board's key is adopted into state on first sync.
        self.state.verify_board_key(read_board_key(self.board.file_path))

        print(f"Connecting to GitHub repository {repo}...")
        repo_node_id, project_id, status_field_id, status_options = self.client.get_repo_project(
            owner, repo_name, project_number
        )
        
        self.status_field_id = status_field_id
        self.status_options = status_options
        
        # Update state with project info
        self.state.set_project_info(repo_node_id, project_id)
        
        print(f"Fetching remote project items...")
        remote_items = self.client.get_project_items(project_id)
        remote_by_title = {item["title"]: item for item in remote_items}
        
        print(f"\nSynchronizing...")
        
        # Flatten local tasks to (title, status) pairs
        local_flat = {}
        for column, tasks in local_tasks.items():
            for task in tasks:
                local_flat[task["title"]] = column
        
        # Track which remote items we've seen
        seen_remote = set()
        
        # Process local tasks
        for title, desired_status in local_flat.items():
            item_id = self.state.get_item_id(title)
            stored_status = self.state.get_status(title)
            
            if not item_id:
                # New task - create it
                print(f"  [CREATE] {title} => {desired_status}")
                item_id = self.client.create_draft_issue(project_id, title)
                # D7+D12: persist item_id with status=None first. The
                # confirmed status is only persisted AFTER the status
                # update mutation succeeds. Prevents the stuck-no-status
                # idempotency bug where a transient failure between
                # create_draft_issue and update_item_status leaves state
                # desynced from GH (state thinks status set; GH has none;
                # next sync sees stored == desired and skips forever).
                self.state.update_task(title, item_id, None)
                self.state.save()

                # Set initial status
                if desired_status in self.status_options:
                    self.client.update_item_status(
                        project_id, item_id, status_field_id,
                        self.status_options[desired_status]
                    )
                    # Confirmed — persist status
                    self.state.update_task(title, item_id, desired_status)
                    self.state.save()
                else:
                    # No matching Status option on the Project. Item is
                    # created with no Status; state stays at None so the
                    # next sync will [UPDATE]-retry. Loud + persistent:
                    # the user must add the option or remove the kanban
                    # entry. (Closes the partymix REVIEW-sync gap class
                    # — audit D11.)
                    print(
                        f"  WARNING: '{desired_status}' has no matching "
                        f"Status option on the GitHub Project; item "
                        f"created with no Status. Sync will retry next "
                        f"run.",
                        file=sys.stderr,
                    )
            elif stored_status != desired_status:
                # Status changed (or first status set after a previous
                # failed attempt — see D12 pattern above)
                print(f"  [UPDATE] {title}: {stored_status} => {desired_status}")
                if desired_status in self.status_options:
                    self.client.update_item_status(
                        project_id, item_id, status_field_id,
                        self.status_options[desired_status]
                    )
                    # Confirmed — persist
                    self.state.update_task(title, item_id, desired_status)
                    self.state.save()
                else:
                    # No matching Status option. Skip the update; state
                    # stays at stored_status. Sync will keep flagging
                    # until the option is added or the kanban entry is
                    # removed.
                    print(
                        f"  WARNING: '{desired_status}' has no matching "
                        f"Status option on the GitHub Project; status "
                        f"not updated. Sync will retry next run.",
                        file=sys.stderr,
                    )
            else:
                # No change
                print(f"  [OK] {title}")

            seen_remote.add(title)

        # Archive tasks that were removed from markdown
        for title in list(self.state.state["tasks"].keys()):
            if title not in local_flat:
                item_id = self.state.get_item_id(title)
                print(f"  [ARCHIVE] {title}")
                self.client.archive_item(project_id, item_id)
                self.state.remove_task(title)
                # D7: persist after each archive so the local state matches
                # the GH-side archive even if the loop is interrupted.
                self.state.save()

        # End-of-loop save remains as a defensive flush; a no-op when
        # per-item saves already covered every mutation, but cheap and
        # keeps the existing "Sync complete" semantics intact.
        print(f"\nSaving state...")
        self.state.save()
        print(f"Sync complete!")


def main():
    # Fix console encoding for Windows; 'replace' (R11) so a stray byte cannot raise into the parent's pipe drain.
    if sys.platform == 'win32':
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')
    
    parser = argparse.ArgumentParser(description='Sync markdown kanban to GitHub Projects')
    parser.add_argument('kanban_file', help='Path to the markdown kanban file')
    parser.add_argument('--repo', help='GitHub repo (owner/name)', default=os.environ.get('GITHUB_REPO') or None)
    parser.add_argument('--project', type=int, help='GitHub Project number (optional if only one project linked)',
                        default=os.environ.get('GITHUB_PROJECT_NUMBER') or None)
    parser.add_argument('--dry-run', action='store_true', help='Parse only, no sync')
    
    args = parser.parse_args()
    
    # Convert project number from env var
    if args.project and isinstance(args.project, str):
        args.project = int(args.project) if args.project.isdigit() else None

    # Fail-fast on missing repo BEFORE any work, including --dry-run.
    if not args.repo:
        raise ConfigurationError(
            "--repo or GITHUB_REPO environment variable required"
        )

    if not os.path.exists(args.kanban_file):
        raise ConfigurationError(f"File not found: {args.kanban_file}")

    # Initialize components
    board = LocalBoard(args.kanban_file)

    if args.dry_run:
        print(f"Parsing {args.kanban_file}...")
        tasks = board.parse()
        print("\nParsed tasks:")
        for column, items in tasks.items():
            print(f"\n{column}:")
            for item in items:
                status = "[x]" if item.get('done') else "[ ]"
                print(f"  {status} {item['title']}")
        return

    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        raise ConfigurationError("GITHUB_TOKEN environment variable not set")
    
    state = StateManager(args.kanban_file)
    client = GitHubClient(token)
    syncer = Syncer(board, state, client)
    
    syncer.sync(args.repo, args.project)


if __name__ == "__main__":
    # E1: catch typed library errors and present them with the same
    # 'Error: <message>' shape callers used to print directly. Same
    # exit code (1), same human-facing text; messages now uniformly
    # land on stderr (was a mix of stdout + stderr previously).
    # Other exceptions propagate with their traceback — those are bugs.
    try:
        try:
            main()
        except KanbangerError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
    finally:
        # R11: flush before exit so the parent sees a clean EOF on its pipes.
        try:
            sys.stdout.flush()
        except Exception:
            pass
        try:
            sys.stderr.flush()
        except Exception:
            pass
