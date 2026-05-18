#!/usr/bin/env python3
"""
kanban-doctor (partymix port) -- preflight checks for kanbanger-partymix.

Verifies your environment is correctly configured to run kanbanger-partymix
as both a CLI tool and an MCP server. Each check produces PASS / WARN / FAIL
with a specific remediation pointer.

Adapted from v2.1.0's kanban_doctor.py (frozen at _kanbanger/). Partymix
additions:
  - install-collision detector (flags if multiple kanbanger dists are
    installed, e.g. v2.1.0 and partymix both reachable via pip)
  - kanbanger_mcp.__file__ surfaced in the importable check (catches
    cases where partymix code is being tested but a different package
    is winning the import resolution race)
  - .kanban.json schema_version check (R8)
  - dist-vs-package version-consistency check (catches the partymix
    setup.py 0.0.1 / __version__ 2.1.0 mismatch surfaced during MVP
    Step 1)

Usage:
    kanban-doctor                    # run from a workspace with _kanban.md
    kanban-doctor --workspace PATH   # run against a specific workspace
    kanban-doctor --strict           # treat WARN as FAIL for exit code
    kanban-doctor --no-network       # skip network-requiring checks

Exit codes:
    0 -- all checks passed (WARN may be present unless --strict)
    1 -- one or more FAIL (or WARN with --strict)
    2 -- script error (e.g. missing dependency)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

GITHUB_API = "https://api.github.com/graphql"
CLASSIC_PAT_RE = re.compile(r"^ghp_[A-Za-z0-9]{36}$")
EXPECTED_STATE_SCHEMA_VERSION = 1
KNOWN_KANBANGER_DISTS = ("kanban-project-sync", "kanbanger-partymix")


# ----- Output helpers ----------------------------------------------------

def _supports_color():
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


if _supports_color():
    GREEN, YELLOW, RED, BOLD, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[1m", "\033[0m"
else:
    GREEN = YELLOW = RED = BOLD = RESET = ""


PASS_TAG = f"{GREEN}[PASS]{RESET}"
WARN_TAG = f"{YELLOW}[WARN]{RESET}"
FAIL_TAG = f"{RED}[FAIL]{RESET}"
SKIP_TAG = "[SKIP]"


_results = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}


def _emit(tag, label, message, fix=None):
    print(f"  {tag} {label}: {message}")
    if fix:
        print(f"         -> {fix}")
    if tag == PASS_TAG:
        _results["pass"] += 1
    elif tag == WARN_TAG:
        _results["warn"] += 1
    elif tag == FAIL_TAG:
        _results["fail"] += 1
    else:
        _results["skip"] += 1


def _section(text):
    print()
    print(f"{BOLD}{text}{RESET}")
    print("-" * len(text))


# ----- Individual checks -------------------------------------------------

def check_python_version():
    label = "Python version"
    v = sys.version_info
    if v < (3, 8):
        _emit(FAIL_TAG, label, f"{v.major}.{v.minor} (need >= 3.8)",
              "Install Python 3.8 or later")
    else:
        _emit(PASS_TAG, label, f"{v.major}.{v.minor}.{v.micro}")


def check_env_file(workspace):
    label = ".env file"
    env_path = workspace / ".env"
    if env_path.exists():
        _emit(PASS_TAG, label, f"found at {env_path}")
        if load_dotenv is not None:
            load_dotenv(env_path, override=True)
        else:
            _emit(WARN_TAG, ".env auto-load",
                  "python-dotenv not installed; .env values not auto-loaded",
                  "pip install python-dotenv")
    else:
        _emit(WARN_TAG, label,
              f"no .env in {workspace}",
              "If env vars come from your shell instead, this is fine. Otherwise: create .env with GITHUB_TOKEN and GITHUB_REPO")


def check_token_present():
    label = "GITHUB_TOKEN"
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        _emit(FAIL_TAG, label, "not set",
              "Set GITHUB_TOKEN in .env or your shell environment")
        return None
    _emit(PASS_TAG, label, f"present ({token[:4]}...{token[-4:] if len(token) >= 8 else ''})")
    return token


def check_token_format(token):
    label = "GITHUB_TOKEN format (classic-PAT check)"
    if not token:
        _emit(SKIP_TAG, label, "skipped (token not set)")
        return
    if CLASSIC_PAT_RE.match(token):
        _emit(PASS_TAG, label, "looks like a classic PAT (ghp_ + 36 chars)")
    elif token.startswith("github_pat_"):
        _emit(FAIL_TAG, label,
              "token starts with 'github_pat_' -- this is a FINE-GRAINED PAT",
              "Generate a CLASSIC PAT instead. Fine-grained PATs cannot access "
              "Projects V2 GraphQL. https://github.com/settings/tokens "
              "(Tokens classic tab) -- required scopes: repo, project")
    elif token.startswith("ghp_"):
        _emit(WARN_TAG, label,
              f"starts with ghp_ but unexpected length ({len(token)})",
              "Verify the token wasn't truncated when copied")
    elif token.startswith("gho_"):
        # OAuth user tokens (e.g. from `gh auth token` / `gh auth login`)
        # functionally work for the Projects V2 GraphQL calls sync makes,
        # but they refresh whenever `gh auth login` runs again, so they
        # are not stable for long-lived automation. WARN, don't FAIL —
        # downstream checks (Repo visible / Projects V2 / Status field)
        # validate that the token actually works. See INTEGRATION_REPORT
        # entry B3.
        _emit(WARN_TAG, label,
              "starts with 'gho_' (OAuth user token from `gh auth login`)",
              "OAuth tokens work but get refreshed whenever `gh auth login` "
              "runs again. For stable long-lived automation prefer a "
              "dedicated classic PAT (ghp_) at "
              "https://github.com/settings/tokens")
    elif token.startswith("ghs_"):
        _emit(FAIL_TAG, label,
              "token type prefix 'ghs_' is a GitHub App server-to-server "
              "token, not a personal-use PAT",
              "Use a classic Personal Access Token (ghp_) created at "
              "https://github.com/settings/tokens")
    else:
        _emit(WARN_TAG, label, "doesn't match any known GitHub token format",
              "Verify this is a classic PAT (starts with 'ghp_')")


def check_token_works(token, no_network):
    label = "GITHUB_TOKEN authenticates"
    if not token:
        _emit(SKIP_TAG, label, "skipped (token not set)")
        return None
    if no_network:
        _emit(SKIP_TAG, label, "skipped (--no-network)")
        return None
    try:
        import requests
    except ImportError:
        _emit(FAIL_TAG, label, "requests library not installed",
              "Re-run: pip install -e .  (or pip install requests)")
        return None
    try:
        resp = requests.post(
            GITHUB_API,
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "query { viewer { login } }"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if "errors" in data:
                _emit(FAIL_TAG, label,
                      f"GraphQL errors: {data['errors'][0].get('message', '?')}",
                      "Re-generate the PAT")
                return None
            login = data["data"]["viewer"]["login"]
            _emit(PASS_TAG, label, f"authenticated as {login}")
            return login
        elif resp.status_code == 401:
            _emit(FAIL_TAG, label, "401 Unauthorized -- token invalid or expired",
                  "Re-generate at https://github.com/settings/tokens")
        else:
            _emit(FAIL_TAG, label, f"HTTP {resp.status_code}",
                  "Check network and token validity")
    except Exception as e:
        _emit(FAIL_TAG, label, f"connection error: {e}",
              "Check internet connection and try again")
    return None


def check_repo_format():
    label = "GITHUB_REPO"
    repo = os.environ.get("GITHUB_REPO")
    if not repo:
        _emit(FAIL_TAG, label, "not set",
              "Set GITHUB_REPO=owner/repo in .env")
        return None
    if "/" not in repo:
        _emit(FAIL_TAG, label, f"'{repo}' missing '/' separator",
              "Format must be 'owner/repo' (e.g. earlyprototype/kanbanger)")
        return None
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts):
        _emit(FAIL_TAG, label, f"'{repo}' malformed",
              "Format must be 'owner/repo' (one slash, both parts non-empty)")
        return None
    _emit(PASS_TAG, label, repo)
    return repo


def check_repo_accessible(token, repo, no_network):
    label = "Repo visible to token"
    if not token or not repo:
        _emit(SKIP_TAG, label, "skipped (prerequisites failed)")
        return False
    if no_network:
        _emit(SKIP_TAG, label, "skipped (--no-network)")
        return False
    try:
        import requests
    except ImportError:
        return False
    owner, repo_name = repo.split("/")
    try:
        resp = requests.post(
            GITHUB_API,
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": "query($o:String!,$r:String!){repository(owner:$o,name:$r){id name}}",
                "variables": {"o": owner, "r": repo_name},
            },
            timeout=10,
        )
        if resp.status_code != 200:
            _emit(FAIL_TAG, label, f"HTTP {resp.status_code}",
                  "Check repo name and token's 'repo' scope")
            return False
        data = resp.json()
        if "errors" in data or not data.get("data", {}).get("repository"):
            err = "errors in response" if "errors" in data else "repository not visible"
            _emit(FAIL_TAG, label, f"{repo}: {err}",
                  "Verify repo exists and token has 'repo' scope")
            return False
        _emit(PASS_TAG, label, repo)
        return True
    except Exception as e:
        _emit(FAIL_TAG, label, f"error: {e}", "Check connectivity")
        return False


def check_projects_v2_access(token, repo, no_network):
    label = "Token can access Projects V2"
    if not token or not repo:
        _emit(SKIP_TAG, label, "skipped (prerequisites failed)")
        return None
    if no_network:
        _emit(SKIP_TAG, label, "skipped (--no-network)")
        return None
    try:
        import requests
    except ImportError:
        return None
    owner, repo_name = repo.split("/")
    try:
        resp = requests.post(
            GITHUB_API,
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": (
                    "query($o:String!,$r:String!){"
                    "repository(owner:$o,name:$r){"
                    "projectsV2(first:5){nodes{id number title fields(first:20){"
                    "nodes{... on ProjectV2SingleSelectField{name options{name}}}"
                    "}}}}"
                    "}"
                ),
                "variables": {"o": owner, "r": repo_name},
            },
            timeout=10,
        )
        data = resp.json()
        if "errors" in data:
            err_msg = data["errors"][0].get("message", "")
            if "Resource not accessible" in err_msg or "fine-grained" in err_msg.lower():
                _emit(FAIL_TAG, label,
                      "Projects V2 NOT accessible -- likely a fine-grained PAT",
                      "Generate a CLASSIC PAT with 'repo' and 'project' scopes. "
                      "Fine-grained PATs cannot access Projects V2 GraphQL.")
                return None
            _emit(FAIL_TAG, label, f"GraphQL error: {err_msg}",
                  "Check token scopes -- needs 'project' scope on classic PAT")
            return None
        nodes = data["data"]["repository"]["projectsV2"]["nodes"]
        if not nodes:
            _emit(WARN_TAG, label,
                  "query succeeded but no projects linked to repo",
                  f"Link a project: https://github.com/{repo}/projects")
            return []
        _emit(PASS_TAG, label, f"{len(nodes)} project(s) linked")
        return nodes
    except Exception as e:
        _emit(FAIL_TAG, label, f"error: {e}", "Check connectivity")
        return None


def check_status_field(projects):
    label = "Project Status field has required options"
    if not projects:
        _emit(SKIP_TAG, label, "skipped (no projects to check)")
        return
    project_num = os.environ.get("GITHUB_PROJECT_NUMBER", "").strip()
    target = None
    if project_num and project_num.isdigit():
        target = next((p for p in projects if p["number"] == int(project_num)), None)
        if not target:
            _emit(FAIL_TAG, label,
                  f"GITHUB_PROJECT_NUMBER={project_num} not found",
                  f"Available numbers: {[p['number'] for p in projects]}")
            return
    else:
        target = projects[0]
    status_field = None
    for f in target["fields"]["nodes"]:
        if f and f.get("name", "").lower() == "status":
            status_field = f
            break
    if not status_field:
        _emit(FAIL_TAG, label,
              f"Project '{target['title']}' has no Status field",
              "Add a Status (single-select) field to your Project")
        return
    opts = {o["name"] for o in status_field["options"]}
    # Partymix is the 5-column release: BACKLOG/TODO/DOING/REVIEW/DONE
    # is auto-injected by kanbanger_mcp.server at startup, and
    # sync_kanban.LocalBoard.parse maps `## REVIEW` -> Status="Review".
    # The GH Project's Status field must therefore expose all five
    # options or REVIEW items land with no Status. See
    # INTEGRATION_REPORT entry B4.
    required = {"Backlog", "Todo", "InProgress", "Review", "Done"}
    missing = required - opts
    if missing:
        _emit(FAIL_TAG, label,
              f"Status field missing: {sorted(missing)}",
              f"Edit Status field; current options: {sorted(opts)}. "
              "Partymix is the 5-column release — REVIEW is required.")
    else:
        _emit(PASS_TAG, label,
              f"Project '{target['title']}': all five required options "
              f"present (Backlog/Todo/InProgress/Review/Done)")


def check_kanban_file(workspace):
    label = "_kanban.md in workspace"
    p = workspace / "_kanban.md"
    if p.exists():
        try:
            content = p.read_text(encoding="utf-8")
            cols = sum(1 for line in content.splitlines() if line.startswith("## "))
            _emit(PASS_TAG, label, f"{p} ({cols} column header(s) found)")
        except Exception as e:
            _emit(WARN_TAG, label, f"{p} present but unreadable: {e}",
                  "Check file encoding (should be UTF-8)")
    else:
        _emit(WARN_TAG, label, f"not at {p}",
              "Create _kanban.md with BACKLOG/TODO/DOING/REVIEW/DONE columns, "
              "or run 'kanban-sync-setup' to generate one")


def check_state_file(workspace):
    """R8: .kanban.json schema_version must be recognised by this version."""
    label = ".kanban.json schema"
    state_file = workspace / ".kanban.json"
    if not state_file.exists():
        _emit(PASS_TAG, label,
              "no state file yet (will be created on first sync_to_github)")
        return
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _emit(FAIL_TAG, label, ".kanban.json is not valid JSON",
              "Delete the file -- R7 backup-and-reset will run on next sync.")
        return
    except Exception as e:
        _emit(WARN_TAG, label, f"could not read: {e}", "")
        return
    schema = data.get("schema_version")
    if schema is None:
        _emit(WARN_TAG, label, "state file lacks schema_version",
              "Run sync_to_github to regenerate, or delete .kanban.json.")
    elif schema != EXPECTED_STATE_SCHEMA_VERSION:
        _emit(WARN_TAG, label,
              f"schema_version={schema} (expected {EXPECTED_STATE_SCHEMA_VERSION})",
              "Migration may be needed; consult CHANGELOG.")
    else:
        _emit(PASS_TAG, label, f"schema_version={schema}")


def check_telemetry_env_var():
    label = "MCP_USE_ANONYMIZED_TELEMETRY"
    val = os.environ.get("MCP_USE_ANONYMIZED_TELEMETRY")
    if val == "false":
        _emit(PASS_TAG, label, "set to 'false' (telemetry banner suppressed)")
    elif val:
        _emit(WARN_TAG, label, f"set to '{val}' (expected 'false')",
              "If using kanbanger as MCP server: set to 'false' to suppress "
              "mcp_use's import-time stdout banner that corrupts JSON-RPC framing")
    else:
        _emit(WARN_TAG, label, "not set",
              "REQUIRED for MCP server use. Set MCP_USE_ANONYMIZED_TELEMETRY=false "
              "in your MCP client's env block. Harmless for CLI-only use.")


def check_mcp_use_installed():
    label = "mcp_use library"
    try:
        import mcp_use  # noqa: F401
        _emit(PASS_TAG, label, "installed (MCP server can run)")
        return True
    except ImportError:
        _emit(WARN_TAG, label, "not installed",
              "For MCP support: pip install -e \".[mcp]\"")
        return False


def check_kanbanger_mcp_importable():
    """Surface __file__ so install-source surprises are visible."""
    label = "kanbanger_mcp package"
    os.environ.setdefault("MCP_USE_ANONYMIZED_TELEMETRY", "false")
    try:
        import kanbanger_mcp
        version = getattr(kanbanger_mcp, "__version__", "unknown")
        source_path = os.path.dirname(os.path.abspath(kanbanger_mcp.__file__))
        _emit(PASS_TAG, label,
              f"importable (version {version}) from {source_path}")
        return source_path, version
    except ImportError as e:
        _emit(WARN_TAG, label, f"not importable: {e}",
              "Run scripts/setup-venv.py to provision a per-project venv.")
        return None, None


def check_install_collision():
    """Flag when more than one kanbanger dist is installed in the active Python."""
    label = "Install collision detector"
    try:
        import importlib.metadata as md
    except ImportError:
        _emit(SKIP_TAG, label, "importlib.metadata unavailable (Python < 3.8)")
        return
    found = []
    for name in KNOWN_KANBANGER_DISTS:
        try:
            ver = md.version(name)
            found.append((name, ver))
        except md.PackageNotFoundError:
            pass
    if len(found) > 1:
        names_versions = ", ".join(f"{n}=={v}" for n, v in found)
        _emit(WARN_TAG, label,
              f"multiple kanbanger dists installed: {names_versions}",
              "Both packages expose the same importable name (`kanbanger_mcp`). "
              "Use scripts/setup-venv.py (per-project venv) to isolate, "
              "or `pip uninstall` the one not needed for this project.")
    elif len(found) == 1:
        n, v = found[0]
        _emit(PASS_TAG, label, f"only {n}=={v} installed (no collision)")
    else:
        _emit(WARN_TAG, label,
              "no kanbanger dist metadata found",
              "Likely an editable install with detached metadata, or "
              "PYTHONPATH-only access. Check `pip list`.")


def check_version_consistency(import_version):
    """Catch dist-vs-package version drift (e.g. setup.py 0.0.1 / __version__ 2.1.0)."""
    label = "Dist / package version consistency"
    if import_version is None:
        _emit(SKIP_TAG, label, "skipped (kanbanger_mcp not importable)")
        return
    try:
        import importlib.metadata as md
    except ImportError:
        _emit(SKIP_TAG, label, "skipped (importlib.metadata unavailable)")
        return
    dist_version = None
    dist_name = None
    for name in KNOWN_KANBANGER_DISTS:
        try:
            dist_version = md.version(name)
            dist_name = name
            break
        except md.PackageNotFoundError:
            continue
    if dist_version is None:
        _emit(SKIP_TAG, label, "skipped (no kanbanger dist installed)")
        return
    if dist_version == import_version:
        _emit(PASS_TAG, label, f"{dist_name} dist=={dist_version}, package=={import_version}")
    else:
        _emit(WARN_TAG, label,
              f"{dist_name} dist=={dist_version} but kanbanger_mcp.__version__=={import_version}",
              "Either update setup.py version, or update kanbanger_mcp/__init__.py "
              "__version__ string. They should match.")


# ----- Entry point -------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="kanban-doctor",
        description="Preflight checks for kanbanger-partymix deployment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run from a workspace containing _kanban.md, or pass --workspace.",
    )
    parser.add_argument(
        "--workspace",
        default=os.environ.get("KANBANGER_WORKSPACE", os.getcwd()),
        help="Path to the kanbanger workspace (default: $KANBANGER_WORKSPACE or cwd)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat WARN as FAIL for exit-code purposes",
    )
    parser.add_argument(
        "--no-network",
        action="store_true",
        help="Skip checks that require network (GitHub API calls)",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()

    print(f"{BOLD}kanban-doctor (partymix) -- preflight checks{RESET}")
    print(f"workspace: {workspace}")

    _section("Environment")
    check_python_version()
    check_env_file(workspace)

    _section("GitHub credentials")
    token = check_token_present()
    check_token_format(token)
    check_token_works(token, args.no_network)

    _section("Repo and Projects")
    repo = check_repo_format()
    if token and repo and not args.no_network:
        repo_ok = check_repo_accessible(token, repo, args.no_network)
        if repo_ok:
            projects = check_projects_v2_access(token, repo, args.no_network)
            check_status_field(projects)
        else:
            _emit(SKIP_TAG, "Token can access Projects V2", "skipped (repo not accessible)")
            _emit(SKIP_TAG, "Project Status field has required options", "skipped (repo not accessible)")
    else:
        _emit(SKIP_TAG, "Repo visible to token", "skipped (prerequisites)")
        _emit(SKIP_TAG, "Token can access Projects V2", "skipped (prerequisites)")
        _emit(SKIP_TAG, "Project Status field has required options", "skipped (prerequisites)")

    _section("Workspace")
    check_kanban_file(workspace)
    check_state_file(workspace)

    _section("MCP server")
    check_telemetry_env_var()
    check_mcp_use_installed()
    _src, import_version = check_kanbanger_mcp_importable()

    _section("Install integrity (partymix additions)")
    check_install_collision()
    check_version_consistency(import_version)

    print()
    print(f"{BOLD}Summary{RESET}")
    print(f"  {PASS_TAG}: {_results['pass']}")
    print(f"  {WARN_TAG}: {_results['warn']}")
    print(f"  {FAIL_TAG}: {_results['fail']}")
    if _results["skip"]:
        print(f"  {SKIP_TAG}: {_results['skip']}")

    if _results["fail"] > 0:
        sys.exit(1)
    if args.strict and _results["warn"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
