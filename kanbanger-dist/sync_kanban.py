"""
kanban-project-sync

Sync a markdown kanban board to GitHub Projects.
"""
import re
import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, skip


# GitHub GraphQL endpoint
GITHUB_API = "https://api.github.com/graphql"


class LocalBoard:
    """Handles parsing of markdown kanban files."""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.tasks: Dict[str, List[Dict]] = {}
    
    def parse(self) -> Dict[str, List[Dict]]:
        """Parse a markdown kanban file and return tasks by column."""
        with open(self.file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tasks = {}
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
                elif 'DONE' in normalized or 'COMPLETE' in normalized:
                    current_section = 'Done'
                else:
                    current_section = section_name
                
                if current_section not in tasks:
                    tasks[current_section] = []
                continue
            
            # Check for task item
            if current_section:
                task_match = task_pattern.match(line.strip())
                if task_match:
                    is_done = task_match.group(1).lower() == 'x'
                    title = task_match.group(2).strip()
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
            "repo_node_id": None,
            "project_id": None,
            "tasks": {}
        }
    
    def load(self) -> Dict:
        """Load state from .kanban.json if it exists."""
        if self.state_file.exists():
            with open(self.state_file, 'r', encoding='utf-8') as f:
                self.state = json.load(f)
        return self.state
    
    def save(self):
        """Save state to .kanban.json."""
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2)
    
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
            print("Error: requests not installed. Run: pip install requests")
            sys.exit(1)
    
    def _query(self, query: str, variables: Dict) -> Dict:
        """Execute a GraphQL query."""
        response = self.requests.post(
            GITHUB_API,
            headers=self.headers,
            json={"query": query, "variables": variables}
        )
        
        if response.status_code != 200:
            print(f"Error: GitHub API returned status {response.status_code}")
            print(response.text)
            sys.exit(1)
        
        data = response.json()
        if "errors" in data:
            print(f"Error: GraphQL errors:")
            for error in data["errors"]:
                print(f"  - {error.get('message', str(error))}")
            sys.exit(1)
        
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
            print(f"Error: No projects found linked to {owner}/{repo_name}")
            sys.exit(1)
        
        # Find the right project
        project = None
        if project_number:
            project = next((p for p in projects if p["number"] == project_number), None)
            if not project:
                print(f"Error: Project #{project_number} not found")
                sys.exit(1)
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
            print("Error: No 'Status' field found in project")
            sys.exit(1)
        
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
                print(f"  [CREATE] {title} -> {desired_status}")
                item_id = self.client.create_draft_issue(project_id, title)
                self.state.update_task(title, item_id, desired_status)
                
                # Set initial status
                if desired_status in self.status_options:
                    self.client.update_item_status(
                        project_id, item_id, status_field_id, 
                        self.status_options[desired_status]
                    )
            elif stored_status != desired_status:
                # Status changed
                print(f"  [UPDATE] {title}: {stored_status} -> {desired_status}")
                if desired_status in self.status_options:
                    self.client.update_item_status(
                        project_id, item_id, status_field_id,
                        self.status_options[desired_status]
                    )
                self.state.update_task(title, item_id, desired_status)
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
        
        print(f"\nSaving state...")
        self.state.save()
        print(f"Sync complete!")


def main():
    parser = argparse.ArgumentParser(description='Sync markdown kanban to GitHub Projects')
    parser.add_argument('kanban_file', help='Path to the markdown kanban file')
    parser.add_argument('--repo', help='GitHub repo (owner/name)', default=os.environ.get('GITHUB_REPO'))
    parser.add_argument('--project', type=int, help='GitHub Project number (optional if only one project linked)', 
                        default=os.environ.get('GITHUB_PROJECT_NUMBER'))
    parser.add_argument('--dry-run', action='store_true', help='Parse only, no sync')
    
    args = parser.parse_args()
    
    # Convert project number from env var
    if args.project and isinstance(args.project, str):
        args.project = int(args.project) if args.project.isdigit() else None
    
    if not os.path.exists(args.kanban_file):
        print(f"Error: File not found: {args.kanban_file}")
        sys.exit(1)
    
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
    
    if not args.repo:
        print("Error: --repo or GITHUB_REPO environment variable required")
        sys.exit(1)
    
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("Error: GITHUB_TOKEN environment variable not set")
        sys.exit(1)
    
    state = StateManager(args.kanban_file)
    client = GitHubClient(token)
    syncer = Syncer(board, state, client)
    
    syncer.sync(args.repo, args.project)


if __name__ == "__main__":
    main()
