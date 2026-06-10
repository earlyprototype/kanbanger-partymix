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
  - kanbanger.__file__ surfaced in the importable check (catches
    cases where partymix code is being tested but a different package
    is winning the import resolution race)
  - .kanban.json schema_version check (R8)
  - dist-vs-package version-consistency check (catches the partymix
    setup.py 0.0.1 / __version__ 2.1.0 mismatch surfaced during MVP
    Step 1)
  - ADR 0002 binding triple in the header (issue #15 step 5):
    `workspace resolved = X -> board = Y -> key = Z`, rendered from one
    kanbanger.binding.resolve_binding() call
  - local-only mode (issue #18): when GitHub sync is plainly not
    configured (no GITHUB_TOKEN / GITHUB_REPO from the shell env, the
    workspace .env, or a .mcp.json literal default), the credential /
    repo not-set checks SKIP instead of FAIL and a "local-only mode"
    line makes the state explicit. Half-configured sync still FAILs.
  - GitHub config-source transparency (issue #18): doctor states where
    each GitHub value came from (shell env / workspace .env / not set)
    and notes when the ambient env disagrees with what the project's
    .mcp.json would provide to a launched server.
  - callable core (issue #23): run_doctor() runs every check and returns
    a structured DoctorReport (per-check {section, name, status, detail,
    remediation} plus the binding triple, config sources, and local-only
    state). This CLI and the MCP `doctor` tool consume the SAME core —
    the CLI echoes the lines progressively (byte-identical to the
    pre-refactor output), the tool renders them verdict-first via
    render_report(). This module must never import the mcp SDK.
    run_doctor() also never mutates os.environ: the workspace .env is
    overlaid into a per-run effective env mapping (build_effective_env),
    so a doctor run inside the long-lived MCP server can't leak one
    workspace's config into later tool calls or sync subprocesses.

Usage:
    kanban-doctor                    # run from a workspace with _kanban.md
    kanban-doctor --workspace PATH   # run against a specific workspace
    kanban-doctor --strict           # treat WARN as FAIL for exit code
    kanban-doctor --no-network       # skip network-requiring checks
    kanban-doctor --local-only       # assert local-only: missing GitHub config SKIPs

Exit codes:
    0 -- all checks passed (WARN may be present unless --strict)
    1 -- one or more FAIL (or WARN with --strict)
    2 -- script error (e.g. missing dependency)
"""

import argparse
import contextvars
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

GITHUB_API = "https://api.github.com/graphql"
CLASSIC_PAT_RE = re.compile(r"^ghp_[A-Za-z0-9]{36}$")
EXPECTED_STATE_SCHEMA_VERSION = 1
KNOWN_KANBANGER_DISTS = ("kanban-project-sync", "kanbanger-partymix")
# The two env vars that decide whether GitHub sync is configured at all
# (GITHUB_PROJECT_NUMBER is an optional refinement, not a config signal).
GITHUB_SYNC_VARS = ("GITHUB_TOKEN", "GITHUB_REPO")
# `${VAR}` / `${VAR:-default}` placeholder syntax used in .mcp.json env
# blocks (written by kanbanger.provision, resolved by the MCP client).
MCP_PLACEHOLDER_RE = re.compile(
    r"^\$\{(?P<var>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>.*))?\}$"
)


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


# ----- Structured results (issue #23: ONE core for CLI + MCP tool) --------

_STATUS_FOR_TAG = {PASS_TAG: "PASS", WARN_TAG: "WARN", FAIL_TAG: "FAIL",
                   SKIP_TAG: "SKIP"}
_MODULE_TAGS = {"PASS": PASS_TAG, "WARN": WARN_TAG, "FAIL": FAIL_TAG,
                "SKIP": SKIP_TAG}
_PLAIN_TAGS = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]",
               "SKIP": "[SKIP]"}


@dataclass(frozen=True)
class CheckResult:
    """One check outcome — the structured form of an `_emit` line.

    `section` is the doctor section the check ran under (None only for
    direct ad-hoc calls outside run_doctor). `remediation` is None for
    results that carry no `-> fix` line.
    """

    section: Optional[str]
    name: str
    status: str  # "PASS" | "WARN" | "FAIL" | "SKIP"
    detail: str
    remediation: Optional[str] = None


@dataclass(frozen=True)
class DoctorReport:
    """Everything one run_doctor() invocation produced.

    body_lines is the EXACT text the CLI prints (plain tags, no ANSI),
    line for line — render_report() and the echoing CLI both derive from
    the same _RunContext, so the two surfaces cannot drift. counts uses
    the legacy lowercase keys ("pass"/"warn"/"fail"/"skip").
    """

    workspace: str
    binding_line: str
    binding: Optional[dict]  # {workspace, board_path, board_key} or None
    local_only: bool
    local_only_forced: bool
    config_source_lines: Tuple[str, ...]
    results: Tuple[CheckResult, ...]
    counts: dict
    body_lines: Tuple[str, ...]

    @property
    def verdict(self) -> str:
        """Overall verdict: local-only (issue #18) is a HEALTHY state."""
        if self.counts["fail"] > 0:
            return "problems found"
        if self.local_only:
            return "healthy (local-only)"
        return "healthy"


def _result_lines(status, name, detail, remediation, tags):
    """Render one check result to its CLI line(s).

    THE single format definition, shared by the legacy direct-call path,
    the echoing CLI run, and the MCP render — exact-output parity by
    construction.
    """
    lines = [f"  {tags[status]} {name}: {detail}"]
    if remediation:
        lines.append(f"         -> {remediation}")
    return lines


class _RunContext:
    """Mutable collector for one run_doctor() invocation.

    Collects structured CheckResults AND the exact CLI body text (plain
    tags). When `echo` is True the colored variant of each line prints as
    it is produced — the CLI's progressive output, byte-identical to the
    pre-refactor behavior. When False nothing is printed (the MCP stdio
    transport owns stdout).
    """

    def __init__(self, echo: bool = False) -> None:
        self.echo = echo
        self.section: Optional[str] = None
        self.results: list = []
        self.counts = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
        self.body_lines: list = []

    def line(self, plain: str, colored: Optional[str] = None) -> None:
        self.body_lines.append(plain)
        if self.echo:
            print(colored if colored is not None else plain)

    def set_section(self, name: str) -> None:
        self.section = name
        self.line("", "")
        self.line(name, f"{BOLD}{name}{RESET}")
        self.line("-" * len(name))

    def add(self, status: str, name: str, detail: str,
            remediation: Optional[str]) -> None:
        self.results.append(CheckResult(
            section=self.section, name=name, status=status,
            detail=detail, remediation=remediation,
        ))
        self.counts[status.lower()] += 1
        plain = _result_lines(status, name, detail, remediation, _PLAIN_TAGS)
        colored = _result_lines(status, name, detail, remediation, _MODULE_TAGS)
        for plain_line, colored_line in zip(plain, colored):
            self.line(plain_line, colored_line)


# Active run context. A ContextVar (not a bare module global) so two
# concurrent doctor runs inside one long-lived MCP server process can
# never interleave their results.
_ACTIVE_RUN: "contextvars.ContextVar[Optional[_RunContext]]" = (
    contextvars.ContextVar("kanban_doctor_active_run", default=None)
)

# Legacy module-level counters: only the DIRECT-call path of _emit uses
# them (unit tests invoke individual checks and read these in place; see
# tests/test_kanban_doctor.py::_capture_check). run_doctor() collects into
# its own _RunContext, so embedded runs never pollute these.
_results = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}


def _emit(tag, label, message, fix=None):
    """Sink for every check outcome.

    Inside a run_doctor() run (the CLI entry point and the MCP `doctor`
    tool) the active _RunContext collects a structured CheckResult — and,
    for the CLI, echoes the exact pre-refactor line. Called DIRECTLY (no
    active run: unit tests, REPL) it keeps the original behavior: print
    the line and bump the module-level counters.
    """
    status = _STATUS_FOR_TAG.get(tag, "SKIP")
    ctx = _ACTIVE_RUN.get()
    if ctx is not None:
        ctx.add(status, label, message, fix)
        return
    for line in _result_lines(status, label, message, fix, {status: tag}):
        print(line)
    _results[status.lower()] += 1


# ----- ADR 0002 binding triple (issue #15 step 5) -------------------------

def binding_summary(start_dir) -> Tuple[str, Optional[dict]]:
    """The ADR 0002 observability triple, structured.

    Returns (line, binding): `line` is the text rendered after the
    `binding:   ` prefix — `workspace resolved = X -> board = Y -> key = Z`
    — from ONE kanbanger.binding.resolve_binding() call (the exact chain
    the MCP server uses: env pin > walk-up discovery > start dir), so the
    doctor shows the binding a server launched against this workspace
    would use. `binding` is {"workspace", "board_path", "board_key"}, or
    None when kanbanger.binding isn't importable (the doctor must keep
    working in the broken installs it diagnoses;
    check_kanbanger_importable reports the import problem properly).

    Deliberately identity context, not an _emit check: none of the
    triple's states is a failure -- an unkeyed (legacy) board and an
    unprovisioned dir are both valid, so this never touches the counters
    or the exit-code policy.
    """
    try:
        from kanbanger.binding import resolve_binding
    except ImportError as e:
        return f"unavailable (kanbanger.binding not importable: {e})", None
    binding = resolve_binding(start_dir)
    board = binding.board_path or "none"
    if binding.board_key:
        key = binding.board_key
    elif binding.board_path:
        key = "none (legacy unkeyed board)"
    else:
        key = "none"
    line = (f"workspace resolved = {binding.workspace} "
            f"-> board = {board} -> key = {key}")
    return line, {
        "workspace": binding.workspace,
        "board_path": binding.board_path,
        "board_key": binding.board_key,
    }


def print_binding(start_dir):
    """Print the binding triple under the `workspace:` header (direct-call
    convenience; run_doctor renders the same line via binding_summary)."""
    line, _ = binding_summary(start_dir)
    print(f"binding:   {line}")


# ----- Individual checks -------------------------------------------------

def check_python_version():
    label = "Python version"
    v = sys.version_info
    if v < (3, 10):
        _emit(FAIL_TAG, label, f"{v.major}.{v.minor} (need >= 3.10)",
              "Install Python 3.10 or later")
    else:
        _emit(PASS_TAG, label, f"{v.major}.{v.minor}.{v.micro}")


def check_env_file(workspace):
    """Report the workspace .env's existence. Reporting ONLY: this never
    mutates os.environ (run_doctor executes inside the long-lived MCP
    server process; the .env values reach the checks via the per-run
    effective env from build_effective_env instead)."""
    label = ".env file"
    env_path = workspace / ".env"
    if env_path.exists():
        _emit(PASS_TAG, label, f"found at {env_path}")
        if load_dotenv is None:
            _emit(WARN_TAG, ".env auto-load",
                  "python-dotenv not installed; .env values not auto-loaded",
                  "pip install python-dotenv")
    else:
        _emit(WARN_TAG, label,
              f"no .env in {workspace}",
              "If env vars come from your shell instead, this is fine. Otherwise: create .env with GITHUB_TOKEN and GITHUB_REPO")


# ----- GitHub config sources + local-only detection (issue #18) -----------

def read_env_file_values(workspace):
    """Return the non-empty values the workspace .env supplies.

    Used for source attribution, local-only detection, and the per-run
    effective env (build_effective_env). Prefers python-dotenv's parser;
    falls back to a minimal KEY=VALUE parse so detection still works
    when dotenv isn't installed (in which case the values are NOT
    overlaid into the effective env -- the checks won't see them, but
    their existence still disables local-only mode).
    """
    env_path = workspace / ".env"
    if not env_path.exists():
        return {}
    if load_dotenv is not None:
        from dotenv import dotenv_values
        return {k: v for k, v in dotenv_values(env_path).items() if v}
    values = {}
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            key, _, val = line.partition("=")
            val = val.strip().strip("'\"")
            if val:
                values[key.strip()] = val
    except OSError:
        pass  # unreadable .env: attribution degrades, check_env_file reports it
    return values


def build_effective_env(env_file_vals):
    """The per-run env mapping the doctor checks consume: the process
    env overlaid with the workspace .env values (.env wins -- the same
    precedence the CLI has always had via load_dotenv(override=True)),
    WITHOUT writing os.environ. run_doctor executes inside the
    long-lived MCP server process (issue #23), where mutating os.environ
    would leak one workspace's .env into every later tool call and
    sync_to_github subprocess.

    When python-dotenv is missing the .env is NOT overlaid, matching the
    legacy non-merge behavior (check_env_file WARNs '.env auto-load' and
    the checks see the shell env only).
    """
    if load_dotenv is None:
        return dict(os.environ)
    return {**os.environ, **env_file_vals}


def read_mcp_project_env(workspace):
    """Parse <workspace>/.mcp.json's kanbanger env block.

    Returns (mcp_json_exists, literals). `literals` maps env var -> the
    value the PROJECT ITSELF would supply at server launch:
      - plain literal value         -> itself
      - ${VAR:-default} placeholder -> the literal default ('' if empty)
      - ${VAR} placeholder          -> '' (pure ambient pass-through)
    The MCP client resolves ${VAR:-default} against ITS environment first,
    so literals are what the project guarantees from its own config alone.
    `literals` is None when .mcp.json exists but cannot be parsed.
    """
    mcp_path = workspace / ".mcp.json"
    if not mcp_path.exists():
        return False, {}
    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True, None
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return True, {}
    env_block = {}
    for name, server in servers.items():
        if "kanbanger" in name.lower() and isinstance(server, dict):
            env_block = server.get("env") or {}
            break
    literals = {}
    for var, raw in env_block.items():
        if not isinstance(raw, str):
            continue
        match = MCP_PLACEHOLDER_RE.match(raw)
        literals[var] = (match.group("default") or "") if match else raw
    return True, literals


def is_local_only(env_file_vals, mcp_literals, environ=None):
    """True when GitHub sync is plainly not configured anywhere.

    Rule: neither GITHUB_TOKEN nor GITHUB_REPO is supplied by the
    effective env (`environ`: shell overlaid with the workspace .env via
    build_effective_env; defaults to os.environ for direct callers), by
    an unmerged .env (dotenv missing), or by a non-empty .mcp.json
    literal/default. ANY single signal disables local-only: a
    half-configured sync must keep FAILing.
    """
    if environ is None:
        environ = os.environ
    for var in GITHUB_SYNC_VARS:
        if environ.get(var):
            return False
        if env_file_vals.get(var):
            return False
        if mcp_literals and mcp_literals.get(var):
            return False
    return True


def _mcp_divergence_notes(mcp_literals, environ=None):
    """Notes for each GitHub var where the effective env (`environ`,
    default os.environ) and the project's .mcp.json would disagree at
    server launch. Values are never printed here (the source lines above
    show the repo; tokens never appear)."""
    if environ is None:
        environ = os.environ
    notes = []
    for var in GITHUB_SYNC_VARS:
        ambient = environ.get(var)
        project = (mcp_literals or {}).get(var, "")
        if ambient and not project:
            notes.append(
                f"note: ambient env supplies {var} but this project's "
                ".mcp.json does not -- a launched server may see different config")
        elif ambient and project and ambient != project:
            notes.append(
                f"note: ambient {var} differs from this project's .mcp.json "
                "default -- a launched server may see different config")
        elif project and not ambient:
            notes.append(
                f"note: this project's .mcp.json supplies {var} but the "
                "ambient env does not -- doctor validates the ambient view only")
    return notes


def config_source_lines(env_file_vals, mcp_exists, mcp_literals, forced, local_only,
                        environ=None):
    """Issue #18 item 2: state WHERE each GitHub value came from and flag
    ambient-vs-.mcp.json disagreement.

    Returns the exact lines the CLI prints (informational context, never
    counted, never exit-affecting). The checks consume the same effective
    env (`environ`: shell overlaid with the workspace .env; defaults to
    os.environ for direct callers).
    """
    if environ is None:
        environ = os.environ
    lines = []
    for var in GITHUB_SYNC_VARS:
        effective = environ.get(var)
        if not effective:
            origin = "not set"
        elif load_dotenv is not None and env_file_vals.get(var):
            origin = "workspace .env"  # the .env overlay wins over the shell
        else:
            origin = "shell env"
        if effective and var != "GITHUB_TOKEN":
            origin += f" ('{effective}')"
        lines.append(f"  {var}: {origin}")
    if mcp_exists and mcp_literals is None:
        lines.append("  note: .mcp.json present but unparseable -- cannot compare project config")
    elif mcp_exists:
        for note in _mcp_divergence_notes(mcp_literals, environ):
            lines.append(f"  {note}")
    if local_only and forced:
        lines.append("  local-only mode (--local-only) -- missing GitHub sync config will SKIP, not FAIL")
    elif local_only:
        lines.append("  local-only mode -- GitHub sync not configured; GitHub checks skip instead of fail")
    return lines


def print_config_sources(env_file_vals, mcp_exists, mcp_literals, forced, local_only):
    """Print the config-source attribution (direct-call convenience;
    run_doctor renders the same lines via config_source_lines)."""
    for line in config_source_lines(env_file_vals, mcp_exists, mcp_literals,
                                    forced, local_only):
        print(line)


def check_token_present(local_only=False, environ=None):
    label = "GITHUB_TOKEN"
    if environ is None:
        environ = os.environ
    token = environ.get("GITHUB_TOKEN")
    if not token:
        if local_only:
            # Local-only boards are a fully supported, healthy state: the
            # check is not applicable, so SKIP (WARN would turn a healthy
            # board into exit 1 under --strict).
            _emit(SKIP_TAG, label,
                  "not set (local-only mode -- GitHub sync not configured)")
            return None
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
        # validate that the token actually works.
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


def check_repo_format(local_only=False, environ=None):
    label = "GITHUB_REPO"
    if environ is None:
        environ = os.environ
    repo = environ.get("GITHUB_REPO")
    if not repo:
        if local_only:
            # Same rationale as check_token_present: not applicable, not
            # a defect -- SKIP keeps --strict meaningful for real WARNs.
            _emit(SKIP_TAG, label,
                  "not set (local-only mode -- GitHub sync not configured)")
            return None
        _emit(FAIL_TAG, label, "not set",
              "Set GITHUB_REPO=owner/repo in .env")
        return None
    if "/" not in repo:
        _emit(FAIL_TAG, label, f"'{repo}' missing '/' separator",
              "Format must be 'owner/repo' (e.g. earlyprototype/kanbanger-partymix)")
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


def check_status_field(projects, environ=None):
    label = "Project Status field has required options"
    if not projects:
        _emit(SKIP_TAG, label, "skipped (no projects to check)")
        return
    if environ is None:
        environ = os.environ
    project_num = environ.get("GITHUB_PROJECT_NUMBER", "").strip()
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
    # is auto-injected by kanbanger.server at startup, and
    # sync_kanban.LocalBoard.parse maps `## REVIEW` -> Status="Review".
    # The GH Project's Status field must therefore expose all five
    # options or REVIEW items land with no Status.
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
              "Create _kanban.md with BACKLOG/TODO/DOING/REVIEW/DONE columns "
              "(the Kanbanger MCP offers to set this up on first use)")


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


def check_mcp_installed():
    label = "mcp SDK (FastMCP)"
    try:
        import mcp  # noqa: F401
        _emit(PASS_TAG, label, "installed (MCP server can run)")
        return True
    except ImportError:
        _emit(WARN_TAG, label, "not installed",
              "For MCP support: pip install -e \".[mcp]\"")
        return False


def check_kanbanger_importable():
    """Surface __file__ so install-source surprises are visible."""
    label = "kanbanger package"
    try:
        import kanbanger
        version = getattr(kanbanger, "__version__", "unknown")
        source_path = os.path.dirname(os.path.abspath(kanbanger.__file__))
        _emit(PASS_TAG, label,
              f"importable (version {version}) from {source_path}")
        return source_path, version
    except ImportError as e:
        _emit(WARN_TAG, label, f"not importable: {e}",
              "Install kanbanger globally: pipx install "
              "git+https://github.com/earlyprototype/kanbanger-partymix.git "
              "(then `kanbanger init` in the project root).")
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
              "Multiple kanbanger dists installed; check for shadowing conflicts. "
              "`pip uninstall` the dist you don't need and keep the single "
              "global kanbanger-partymix install (re-run `kanbanger init` "
              "per project if its .mcp.json needs re-pointing).")
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
        _emit(SKIP_TAG, label, "skipped (kanbanger not importable)")
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
              f"{dist_name} dist=={dist_version} but kanbanger.__version__=={import_version}",
              "Either update setup.py version, or update kanbanger/__init__.py "
              "__version__ string. They should match.")


# ----- Callable core (issue #23) ------------------------------------------

def run_doctor(workspace, *, no_network: bool = False,
               local_only_flag: bool = False,
               echo: bool = False) -> DoctorReport:
    """Run every doctor check against `workspace`; return a DoctorReport.

    The ONE implementation behind both surfaces:
      - the CLI (main) calls with echo=True: every line prints as it is
        produced — the exact pre-refactor output, colors and all;
      - the MCP `doctor` tool calls with echo=False: nothing is printed
        (stdout is the MCP stdio transport) and the tool renders the
        collected report via render_report().

    `no_network` mirrors --no-network; `local_only_flag` mirrors
    --local-only (auto-detection still applies when False). `workspace`
    should be an absolute, resolved path (callers resolve; the value is
    rendered verbatim in the header).

    Never mutates os.environ: the workspace .env is overlaid into a
    per-run effective env (build_effective_env) that every env-reading
    check consumes, so an embedded run can't leak one workspace's config
    into the MCP server process (later tool calls and sync_to_github
    subprocesses inherit that env).
    """
    workspace = Path(workspace)
    ctx = _RunContext(echo=echo)
    run_token = _ACTIVE_RUN.set(ctx)
    try:
        ctx.line("kanban-doctor (partymix) -- preflight checks",
                 f"{BOLD}kanban-doctor (partymix) -- preflight checks{RESET}")
        ctx.line(f"workspace: {workspace}")
        binding_line, binding_info = binding_summary(workspace)
        ctx.line(f"binding:   {binding_line}")

        ctx.set_section("Environment")
        check_python_version()
        check_env_file(workspace)  # existence report only; never mutates os.environ

        # Issue #18 detection + the per-run effective env: shell overlaid
        # by the workspace .env (the precedence load_dotenv(override=True)
        # used to install process-wide). Every env-reading check below
        # consumes THIS mapping; os.environ stays untouched (issue #23:
        # this runs inside the long-lived MCP server process). The network
        # checks need no mapping -- token/repo flow to them explicitly via
        # check_token_present / check_repo_format's return values.
        env_file_vals = read_env_file_values(workspace)
        environ = build_effective_env(env_file_vals)
        mcp_exists, mcp_literals = read_mcp_project_env(workspace)
        local_only = local_only_flag or is_local_only(env_file_vals, mcp_literals,
                                                      environ)

        ctx.set_section("GitHub config sources")
        cfg_lines = config_source_lines(env_file_vals, mcp_exists, mcp_literals,
                                        local_only_flag, local_only, environ)
        for line in cfg_lines:
            ctx.line(line)

        ctx.set_section("GitHub credentials")
        token = check_token_present(local_only, environ)
        check_token_format(token)
        check_token_works(token, no_network)

        ctx.set_section("Repo and Projects")
        repo = check_repo_format(local_only, environ)
        if token and repo and not no_network:
            repo_ok = check_repo_accessible(token, repo, no_network)
            if repo_ok:
                projects = check_projects_v2_access(token, repo, no_network)
                check_status_field(projects, environ)
            else:
                _emit(SKIP_TAG, "Token can access Projects V2", "skipped (repo not accessible)")
                _emit(SKIP_TAG, "Project Status field has required options", "skipped (repo not accessible)")
        else:
            _emit(SKIP_TAG, "Repo visible to token", "skipped (prerequisites)")
            _emit(SKIP_TAG, "Token can access Projects V2", "skipped (prerequisites)")
            _emit(SKIP_TAG, "Project Status field has required options", "skipped (prerequisites)")

        ctx.set_section("Workspace")
        check_kanban_file(workspace)
        check_state_file(workspace)

        ctx.set_section("MCP server")
        check_mcp_installed()
        _src, import_version = check_kanbanger_importable()

        ctx.set_section("Install integrity (partymix additions)")
        check_install_collision()
        check_version_consistency(import_version)

        ctx.line("", "")
        ctx.line("Summary", f"{BOLD}Summary{RESET}")
        ctx.line(f"  [PASS]: {ctx.counts['pass']}",
                 f"  {PASS_TAG}: {ctx.counts['pass']}")
        ctx.line(f"  [WARN]: {ctx.counts['warn']}",
                 f"  {WARN_TAG}: {ctx.counts['warn']}")
        ctx.line(f"  [FAIL]: {ctx.counts['fail']}",
                 f"  {FAIL_TAG}: {ctx.counts['fail']}")
        if ctx.counts["skip"]:
            ctx.line(f"  {SKIP_TAG}: {ctx.counts['skip']}")
    finally:
        _ACTIVE_RUN.reset(run_token)

    return DoctorReport(
        workspace=str(workspace),
        binding_line=binding_line,
        binding=binding_info,
        local_only=local_only,
        local_only_forced=local_only_flag,
        config_source_lines=tuple(cfg_lines),
        results=tuple(ctx.results),
        counts=dict(ctx.counts),
        body_lines=tuple(ctx.body_lines),
    )


def render_report(report: DoctorReport) -> str:
    """Render a DoctorReport as verdict-first plain text (no ANSI color).

    The consumer is the MCP `doctor` tool (issue #23): overall verdict on
    line 1 so an agent can relay health at a glance, then the EXACT body
    the CLI prints — header, binding triple, config sources, per-section
    check lines with remediations, summary counts — with plain
    [PASS]/[WARN]/[FAIL]/[SKIP] tags.
    """
    counts = report.counts
    if counts["fail"] > 0:
        tail = (f" -- {counts['fail']} check(s) failed; each [FAIL] line "
                f"below carries its remediation")
    elif report.local_only:
        tail = " -- GitHub sync not configured; the local board is fully operational"
    else:
        tail = ""
    if counts["fail"] == 0 and counts["warn"]:
        tail += f" ({counts['warn']} warning(s) noted)"
    lines = [f"verdict: {report.verdict}{tail}", ""]
    lines.extend(report.body_lines)
    return "\n".join(lines)


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
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Assert this board is local-only: missing GitHub sync config "
             "SKIPs instead of FAILs. (Auto-detected when no GITHUB_TOKEN/"
             "GITHUB_REPO is supplied by the shell env, the workspace .env, "
             "or a .mcp.json literal default.)",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    report = run_doctor(
        workspace,
        no_network=args.no_network,
        local_only_flag=args.local_only,
        echo=True,
    )

    if report.counts["fail"] > 0:
        sys.exit(1)
    if args.strict and report.counts["warn"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
