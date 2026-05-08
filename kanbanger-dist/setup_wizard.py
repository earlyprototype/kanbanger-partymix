"""
kanban-project-sync Setup Wizard

Interactive guide to configure your GitHub Project sync.
"""
import os
import sys
from pathlib import Path


def print_header(text):
    """Print a fancy header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")


def print_step(step, total, text):
    """Print a step indicator."""
    print(f"\n[Step {step}/{total}] {text}")
    print("-" * 60)


def print_success(text):
    """Print success message."""
    print(f"  [OK] {text}")


def print_error(text):
    """Print error message."""
    print(f"  [ERROR] {text}")


def print_info(text):
    """Print info message."""
    print(f"  [INFO] {text}")


def get_input(prompt, default=None):
    """Get user input with optional default."""
    if default:
        response = input(f"{prompt} [{default}]: ").strip()
        return response if response else default
    return input(f"{prompt}: ").strip()


def yes_no(prompt, default=True):
    """Ask a yes/no question."""
    default_str = "Y/n" if default else "y/N"
    response = input(f"{prompt} ({default_str}): ").strip().lower()
    if not response:
        return default
    return response in ['y', 'yes']


def check_env_file():
    """Check if .env file exists."""
    env_path = Path(".env")
    if env_path.exists():
        print_info(".env file found")
        return True
    return False


def create_env_file(token, repo, project_number=None):
    """Create .env file."""
    env_path = Path(".env")
    content = f"GITHUB_TOKEN={token}\nGITHUB_REPO={repo}\n"
    if project_number:
        content += f"GITHUB_PROJECT_NUMBER={project_number}\n"
    
    with open(env_path, 'w') as f:
        f.write(content)
    
    print_success(f".env file created at {env_path.absolute()}")


def check_gitignore():
    """Ensure .gitignore includes sensitive files."""
    gitignore_path = Path(".gitignore")
    
    required_entries = [".env", ".kanban.json"]
    
    if not gitignore_path.exists():
        print_info(".gitignore not found, creating...")
        with open(gitignore_path, 'w') as f:
            f.write("# Kanban sync files\n")
            f.write(".env\n")
            f.write(".env.local\n")
            f.write(".kanban.json\n")
        print_success(".gitignore created")
        return
    
    with open(gitignore_path, 'r') as f:
        content = f.read()
    
    missing = [entry for entry in required_entries if entry not in content]
    
    if missing:
        print_info(f"Adding {', '.join(missing)} to .gitignore...")
        with open(gitignore_path, 'a') as f:
            f.write("\n# Kanban sync files\n")
            for entry in missing:
                f.write(f"{entry}\n")
        print_success(".gitignore updated")
    else:
        print_success(".gitignore looks good")


def validate_token(token):
    """Validate GitHub token by making a simple API call."""
    try:
        import requests
    except ImportError:
        print_error("requests library not installed")
        return False
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    query = """
    query {
        viewer {
            login
        }
    }
    """
    
    try:
        response = requests.post(
            "https://api.github.com/graphql",
            headers=headers,
            json={"query": query},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if "errors" in data:
                print_error("Token is invalid or lacks required scopes")
                print_info("Make sure your token has 'repo' and 'project' scopes")
                return False
            
            username = data["data"]["viewer"]["login"]
            print_success(f"Token valid! Logged in as: {username}")
            return True
        elif response.status_code == 401:
            print_error("Token is invalid or expired")
            return False
        else:
            print_error(f"GitHub API returned status {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Connection error: {str(e)}")
        return False


def check_repo_project(token, repo):
    """Check if repository has linked projects."""
    try:
        import requests
    except ImportError:
        return None
    
    owner, repo_name = repo.split('/')
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    query = """
    query($owner: String!, $repo: String!) {
        repository(owner: $owner, name: $repo) {
            projectsV2(first: 5) {
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
    
    try:
        response = requests.post(
            "https://api.github.com/graphql",
            headers=headers,
            json={"query": query, "variables": {"owner": owner, "repo": repo_name}},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if "errors" in data:
                print_error("Could not access repository")
                print_info("Make sure the repository exists and your token has access")
                return None
            
            projects = data["data"]["repository"]["projectsV2"]["nodes"]
            return projects
        else:
            return None
    except Exception as e:
        print_error(f"Connection error: {str(e)}")
        return None


def check_status_field(project):
    """Check if project has proper Status field."""
    required_options = {"Backlog", "Todo", "InProgress", "Done"}
    
    for field in project.get("fields", {}).get("nodes", []):
        if field and field.get("name") in ["Status", "status"]:
            options = {opt["name"] for opt in field.get("options", [])}
            missing = required_options - options
            
            if not missing:
                print_success("Status field configured correctly!")
                return True
            else:
                print_error(f"Status field missing options: {', '.join(missing)}")
                print_info("Your Status field has: " + ", ".join(options))
                return False
    
    print_error("No 'Status' field found in project")
    return False


def create_example_kanban():
    """Create an example kanban file."""
    kanban_path = Path("_kanban.md")
    
    if kanban_path.exists():
        if not yes_no("_kanban.md already exists. Overwrite?", default=False):
            return False
    
    content = """# My Kanban Board

## BACKLOG
*   [ ] Plan new features
*   [ ] Research best practices

## TODO
*   [ ] Start working on tasks

## DOING
*   [ ] Active task goes here

## DONE
*   [x] Setup kanban-sync tool
"""
    
    with open(kanban_path, 'w') as f:
        f.write(content)
    
    print_success(f"Example kanban created: {kanban_path.absolute()}")
    return True


def main():
    """Run the setup wizard."""
    print_header("kanban-project-sync Setup Wizard")
    
    print("Welcome! This wizard will help you configure kanban-project-sync.")
    print("You'll need:")
    print("  1. A GitHub account")
    print("  2. A repository")
    print("  3. A GitHub Project V2 linked to that repository")
    print("\nLet's get started!\n")
    
    if not yes_no("Continue with setup?", default=True):
        print("\nSetup cancelled.")
        return
    
    # Step 1: Check/create .gitignore
    print_step(1, 6, "Checking .gitignore")
    check_gitignore()
    
    # Step 2: GitHub Token
    print_step(2, 6, "GitHub Personal Access Token")
    
    existing_env = check_env_file()
    token = None
    
    if existing_env:
        if yes_no("Use existing token from .env?", default=True):
            from dotenv import load_dotenv
            load_dotenv()
            token = os.environ.get("GITHUB_TOKEN")
    
    if not token:
        print("\nYou need a GitHub Personal Access Token.")
        print("Get one here: https://github.com/settings/tokens")
        print("\nRequired scopes:")
        print("  - repo (Full control of private repositories)")
        print("  - project (Full control of projects)")
        print()
        
        token = get_input("Paste your GitHub token (starts with ghp_)")
        
        if not token or not token.startswith("ghp_"):
            print_error("Invalid token format")
            sys.exit(1)
    
    print("\nValidating token...")
    if not validate_token(token):
        print_error("Token validation failed. Please try again.")
        sys.exit(1)
    
    # Step 3: Repository
    print_step(3, 6, "GitHub Repository")
    
    repo = None
    if existing_env:
        from dotenv import load_dotenv
        load_dotenv()
        existing_repo = os.environ.get("GITHUB_REPO")
        if existing_repo:
            print_info(f"Found in .env: {existing_repo}")
            if yes_no("Use this repository?", default=True):
                repo = existing_repo
    
    if not repo:
        print("\nEnter your repository in format: owner/repo-name")
        print("Example: earlyprototype/kanbanger")
        repo = get_input("Repository")
        
        if '/' not in repo:
            print_error("Invalid format. Use: owner/repo-name")
            sys.exit(1)
    
    # Step 4: Check Projects
    print_step(4, 6, "Checking Linked Projects")
    
    print("Checking for linked projects...")
    projects = check_repo_project(token, repo)
    
    if projects is None:
        print_error("Could not check projects")
        sys.exit(1)
    
    if not projects:
        print_error("No projects found linked to this repository!")
        print("\nTo link a project:")
        print(f"  1. Go to: https://github.com/{repo}")
        print("  2. Click 'Projects' tab")
        print("  3. Click 'Link a project'")
        print("  4. Select or create a project")
        print("\nRun this wizard again after linking a project.")
        sys.exit(1)
    
    print_success(f"Found {len(projects)} linked project(s):")
    for project in projects:
        print(f"    #{project['number']}: {project['title']}")
    
    # Step 5: Check Status Field
    print_step(5, 6, "Checking Status Field Configuration")
    
    selected_project = projects[0]
    project_number = None
    
    if len(projects) > 1:
        print("\nMultiple projects found. Which one do you want to use?")
        for i, project in enumerate(projects, 1):
            print(f"  {i}. #{project['number']}: {project['title']}")
        
        choice = get_input(f"Select project (1-{len(projects)})", default="1")
        try:
            idx = int(choice) - 1
            selected_project = projects[idx]
            project_number = selected_project['number']
        except (ValueError, IndexError):
            print_error("Invalid selection")
            sys.exit(1)
    
    print(f"\nChecking project: {selected_project['title']}")
    
    if not check_status_field(selected_project):
        print("\nTo fix the Status field:")
        print(f"  1. Go to: https://github.com/users/{repo.split('/')[0]}/projects/{selected_project['number']}")
        print("  2. Click on Status field dropdown → 'Edit field'")
        print("  3. Ensure these options exist (exact names):")
        print("     - Backlog")
        print("     - Todo")
        print("     - InProgress")
        print("     - Done")
        print("\nRun this wizard again after fixing the Status field.")
        sys.exit(1)
    
    # Step 6: Save Configuration
    print_step(6, 6, "Saving Configuration")
    
    create_env_file(token, repo, project_number)
    
    print_success("Configuration complete!")
    
    # Bonus: Create example kanban
    print("\n" + "=" * 60)
    if yes_no("Create an example _kanban.md file?", default=True):
        if create_example_kanban():
            print("\nYou can now test the sync:")
            print("  kanban-sync _kanban.md --dry-run")
            print("\nOr do a real sync:")
            print("  kanban-sync _kanban.md")
    
    print("\n" + "=" * 60)
    print("  Setup Complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Create or edit your kanban markdown file")
    print("  2. Run: kanban-sync your-file.md --dry-run")
    print("  3. When ready: kanban-sync your-file.md")
    print("\nFor help: kanban-sync --help")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        sys.exit(1)
