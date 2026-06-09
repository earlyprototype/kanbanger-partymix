"""Tests for ADR 0002 collision-proof board binding (issue #15 step 4).

Three layers, mirroring the design:

  1. Board-key primitives (kanban_io): mint / format / extract / insert /
     read, plus proof the marker is invisible to every board parser.
  2. Derived discovery (kanbanger.binding): the resolution precedence chain
     and the issue's 7-case behavior matrix — nested subfolder, monorepo,
     git worktree, symlinked path, no-.git tree, moved folder, copied
     board. Each case's DEFINED behavior is stated in its test docstring.
  3. Sync-state pairing (sync_kanban.StateManager.verify_board_key): the
     copied-board guard — sync state records the board key on first sync
     and refuses to drive a different board's state.

Everything runs against throwaway tmp_path dirs only.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from kanban_io import (
    discover_columns,
    extract_board_key,
    format_board_key_marker,
    insert_board_key,
    mint_board_key,
    parse_task_title_with_description,
    read_board_key,
)
from kanbanger.binding import find_board_dir, resolve_binding, resolve_workspace

FIVE_COL = (
    "# Proj Kanban\n"
    "\n"
    "## BACKLOG\n"
    "\n"
    "## TODO\n"
    "\n"
    "## DOING\n"
    "\n"
    "## REVIEW\n"
    "\n"
    "## DONE\n"
)

CANONICAL_COLUMNS = ["BACKLOG", "TODO", "DOING", "REVIEW", "DONE"]


def _write_keyed_board(directory: Path, key: str | None = None) -> str:
    """Write a keyed 5-column board into `directory`; return the key."""
    board_key = key or mint_board_key()
    (directory / "_kanban.md").write_text(
        insert_board_key(FIVE_COL, board_key), encoding="utf-8"
    )
    return board_key


@pytest.fixture
def no_workspace_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Discovery-mode fixture: ensure the env pin is absent."""
    monkeypatch.delenv("KANBANGER_WORKSPACE", raising=False)


# ---------------------------------------------------------------------------
# 1. Board-key primitives
# ---------------------------------------------------------------------------


def test_mint_board_key_is_uuid4_hex():
    key1 = mint_board_key()
    key2 = mint_board_key()
    for key in (key1, key2):
        assert len(key) == 32
        assert all(c in "0123456789abcdef" for c in key)
    assert key1 != key2  # uniqueness (probabilistic, but 2^122 odds)


def test_extract_board_key_reads_marker_under_title():
    key = mint_board_key()
    keyed = insert_board_key(FIVE_COL, key)
    assert extract_board_key(keyed) == key


def test_extract_board_key_none_when_absent():
    assert extract_board_key(FIVE_COL) is None
    assert extract_board_key("") is None


def test_extract_board_key_tolerates_dashed_uuid():
    text = "# T\n<!-- kanbanger:board-id: 123e4567-e89b-42d3-a456-426614174000 -->\n"
    assert extract_board_key(text) == "123e4567-e89b-42d3-a456-426614174000"


def test_extract_board_key_rejects_short_junk():
    # Below the 8-char floor: not a plausible key, must not latch on.
    assert extract_board_key("# T\n<!-- kanbanger:board-id: xy -->\n") is None


def test_insert_board_key_under_title_preserves_all_other_bytes():
    key = mint_board_key()
    keyed = insert_board_key(FIVE_COL, key)
    marker_line = format_board_key_marker(key) + "\n"
    # Exactly one line added; removing it reproduces the original.
    assert keyed.replace(marker_line, "", 1) == FIVE_COL
    # Placement: directly under the title line.
    lines = keyed.splitlines()
    assert lines[0] == "# Proj Kanban"
    assert lines[1] == format_board_key_marker(key)


def test_insert_board_key_at_top_when_no_title():
    key = mint_board_key()
    original = "## BACKLOG\n*   [ ] task\n"
    keyed = insert_board_key(original, key)
    assert keyed.splitlines()[0] == format_board_key_marker(key)
    assert keyed.replace(format_board_key_marker(key) + "\n", "", 1) == original


def test_insert_board_key_handles_unterminated_title_line():
    key = mint_board_key()
    original = "# Title only, no trailing newline"
    keyed = insert_board_key(original, key)
    assert keyed == original + "\n" + format_board_key_marker(key)
    assert extract_board_key(keyed) == key


def test_insert_board_key_uses_boards_crlf_style():
    key = mint_board_key()
    original = "# T\r\n\r\n## BACKLOG\r\n"
    keyed = insert_board_key(original, key)
    assert keyed.replace(format_board_key_marker(key) + "\r\n", "", 1) == original


def test_read_board_key_missing_file_returns_none(tmp_path: Path):
    assert read_board_key(tmp_path / "_kanban.md") is None


def test_read_board_key_unkeyed_board_returns_none(tmp_path: Path):
    (tmp_path / "_kanban.md").write_text(FIVE_COL, encoding="utf-8")
    assert read_board_key(tmp_path / "_kanban.md") is None


# --- marker invisibility: every parser must ignore it -----------------------


def test_marker_invisible_to_board_parsers(tmp_path: Path):
    """The marker is neither a column header nor a task line, for both the
    MCP-side parser (kanban_io) and the sync-side parser (LocalBoard)."""
    key = _write_keyed_board(tmp_path)
    marker = format_board_key_marker(key)

    # Column discovery: unchanged canonical set.
    assert discover_columns(str(tmp_path)) == CANONICAL_COLUMNS
    # Task-line parser: the marker is not a task.
    assert parse_task_title_with_description(marker) is None

    # Sync-side parser: no task anywhere mentions the marker.
    from sync_kanban import LocalBoard

    tasks = LocalBoard(str(tmp_path / "_kanban.md")).parse()
    for column_tasks in tasks.values():
        for task in column_tasks:
            assert "board-id" not in task["title"]


def test_marker_invisible_to_list_tasks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KANBANGER_WORKSPACE", str(tmp_path))
    key = mint_board_key()
    board = insert_board_key(FIVE_COL, key).replace(
        "## TODO\n", "## TODO\n*   [ ] Real task\n", 1
    )
    (tmp_path / "_kanban.md").write_text(board, encoding="utf-8")

    from tests.conftest import _StubMCPServer
    from kanbanger.tools import register_tools

    stub = _StubMCPServer()
    register_tools(stub)
    out = stub.tools["list_tasks"]()
    assert "board-id" not in out
    assert json.loads(out)["TODO"] == ["Real task"]


def test_board_key_survives_tool_mutations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """add_task / delete_task rewrite the board; the minted key must ride
    through untouched (it IS the board's identity)."""
    monkeypatch.setenv("KANBANGER_WORKSPACE", str(tmp_path))
    key = _write_keyed_board(tmp_path)

    from tests.conftest import _StubMCPServer
    from kanbanger.tools import register_tools

    stub = _StubMCPServer()
    register_tools(stub)
    stub.tools["add_task"]("Key survives", "TODO")
    assert read_board_key(tmp_path / "_kanban.md") == key
    stub.tools["delete_task"]("Key survives", "TODO")
    assert read_board_key(tmp_path / "_kanban.md") == key


# ---------------------------------------------------------------------------
# 2. Derived discovery — precedence chain
# ---------------------------------------------------------------------------


def test_env_var_wins_over_walkup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Back-compat: an explicit KANBANGER_WORKSPACE pin beats discovery,
    even when the start dir sits inside a different provisioned project."""
    pinned = tmp_path / "pinned"
    other = tmp_path / "other"
    for proj in (pinned, other):
        proj.mkdir()
        _write_keyed_board(proj)
    nested = other / "deep"
    nested.mkdir()

    monkeypatch.setenv("KANBANGER_WORKSPACE", str(pinned))
    binding = resolve_binding(nested)
    assert Path(binding.workspace) == pinned.resolve()
    assert Path(binding.board_path) == (pinned / "_kanban.md").resolve()


def test_env_var_empty_treated_as_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    _write_keyed_board(proj)
    nested = proj / "sub"
    nested.mkdir()

    monkeypatch.setenv("KANBANGER_WORKSPACE", "")
    assert Path(resolve_workspace(nested)) == proj.resolve()


def test_cwd_fallback_when_no_board_anywhere(tmp_path: Path, no_workspace_env):
    """Unprovisioned tree: the workspace is the start dir itself, and the
    binding reports no board and no key (None, not an error)."""
    lonely = tmp_path / "lonely" / "dir"
    lonely.mkdir(parents=True)
    binding = resolve_binding(lonely)
    assert Path(binding.workspace) == lonely.resolve()
    assert binding.board_path is None
    assert binding.board_key is None


def test_resolve_binding_unkeyed_board_returns_none_key(tmp_path: Path, no_workspace_env):
    """Old boards without a key keep working: board found, key None."""
    (tmp_path / "_kanban.md").write_text(FIVE_COL, encoding="utf-8")
    binding = resolve_binding(tmp_path)
    assert Path(binding.board_path) == (tmp_path / "_kanban.md").resolve()
    assert binding.board_key is None


def test_resolve_binding_keyed_board_returns_key(tmp_path: Path, no_workspace_env):
    key = _write_keyed_board(tmp_path)
    binding = resolve_binding(tmp_path)
    assert binding.board_key == key


def test_directory_named_kanban_md_does_not_count(tmp_path: Path, no_workspace_env):
    """Labels are lies: a DIRECTORY called _kanban.md is not a board. The
    walk must skip the decoy dir it meets first and keep climbing to the
    real board file above it."""
    root = tmp_path / "root"
    mid = root / "mid"
    (mid / "_kanban.md").mkdir(parents=True)  # decoy: a DIRECTORY
    start = mid / "inner"
    start.mkdir()
    key = _write_keyed_board(root)  # the real board, one level above

    found = find_board_dir(start)
    assert found == root.resolve()
    assert resolve_binding(start).board_key == key


# ---------------------------------------------------------------------------
# 2. Derived discovery — the 7-case matrix (issue #15 step 4 DONE bar)
# ---------------------------------------------------------------------------


def test_case1_nested_subfolder_finds_project_board(tmp_path: Path, no_workspace_env):
    """Case 1 — nested subfolder. Starting in <proj>/a/b resolves
    <proj>/_kanban.md: the walk checks the start dir then each ancestor."""
    proj = tmp_path / "proj"
    nested = proj / "a" / "b"
    nested.mkdir(parents=True)
    key = _write_keyed_board(proj)

    binding = resolve_binding(nested)
    assert Path(binding.workspace) == proj.resolve()
    assert Path(binding.board_path) == (proj / "_kanban.md").resolve()
    assert binding.board_key == key


def test_case2_monorepo_nearest_board_wins_deterministically(
    tmp_path: Path, no_workspace_env
):
    """Case 2 — monorepo with >= 2 boards. Starting inside the sub-project
    resolves the NEAREST (sub-project's) board, never the repo root's; a
    sibling without its own board falls through to the repo-root board.
    Resolution is deterministic: repeated calls give identical results."""
    repo = tmp_path / "monorepo"
    sub = repo / "packages" / "subproj"
    sub_nested = sub / "src"
    docs = repo / "docs"
    for d in (sub_nested, docs):
        d.mkdir(parents=True)
    root_key = _write_keyed_board(repo)
    sub_key = _write_keyed_board(sub)
    assert root_key != sub_key

    inside_sub = resolve_binding(sub_nested)
    assert Path(inside_sub.workspace) == sub.resolve()
    assert inside_sub.board_key == sub_key

    sibling = resolve_binding(docs)
    assert Path(sibling.workspace) == repo.resolve()
    assert sibling.board_key == root_key

    # Deterministic: identical on repeat.
    assert resolve_binding(sub_nested) == inside_sub
    assert resolve_binding(docs) == sibling


def test_case3_git_worktree_layout_resolves_own_board(tmp_path: Path, no_workspace_env):
    """Case 3 — git worktree (simulated layout). Discovery is PURE
    path-walking with no `.git` dependency: a worktree dir (whose `.git` is
    a pointer FILE, not a dir) containing its own checked-out board
    resolves that board, never the main working tree's."""
    main = tmp_path / "main"
    (main / ".git").mkdir(parents=True)  # main repo: .git DIRECTORY
    main_key = _write_keyed_board(main)

    wt = tmp_path / "wt"
    wt.mkdir()
    # Worktree layout: .git is a FILE pointing back into the main repo.
    (wt / ".git").write_text(
        f"gitdir: {main / '.git' / 'worktrees' / 'wt'}\n", encoding="utf-8"
    )
    wt_key = _write_keyed_board(wt)
    inner = wt / "deep"
    inner.mkdir()

    binding = resolve_binding(inner)
    assert Path(binding.workspace) == wt.resolve()
    assert binding.board_key == wt_key
    assert binding.board_key != main_key
    assert (wt / ".git").is_file()  # the layout really was worktree-shaped


def test_case3_real_git_worktree_resolves_own_board(tmp_path: Path, no_workspace_env):
    """Case 3 (real git) — a worktree made by `git worktree add` resolves
    its own checked-out board copy. Since the board is a tracked file, the
    worktree's copy carries the SAME minted key as the main tree's — the
    in-board key follows the file, not the folder."""
    git = shutil.which("git")
    if git is None:
        pytest.skip("git not on PATH in this environment")

    def run(*args: str, cwd: Path) -> None:
        subprocess.run(
            [git, *args], cwd=str(cwd), check=True, capture_output=True, timeout=60
        )

    main = tmp_path / "main"
    main.mkdir()
    key = _write_keyed_board(main)
    wt = tmp_path / "wt"
    try:
        run("init", "-q", cwd=main)
        run("add", "_kanban.md", cwd=main)
        run(
            "-c", "user.email=kanbanger-test@example.com",
            "-c", "user.name=kanbanger-test",
            "commit", "-qm", "board",
            cwd=main,
        )
        run("worktree", "add", str(wt), "-b", "kanbanger-wt-test", cwd=main)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"git worktree setup failed in this environment: {exc}")

    inner = wt / "deep"
    inner.mkdir()
    binding = resolve_binding(inner)
    assert Path(binding.workspace) == wt.resolve()
    assert Path(binding.board_path) == (wt / "_kanban.md").resolve()
    assert binding.board_key == key  # tracked file: identity travels with it


def test_case4_symlinked_path_resolves_physical_board(
    tmp_path: Path, no_workspace_env
):
    """Case 4 — symlinked path. DEFINED RULE: symlinks are resolved FIRST
    (`Path.resolve()`), so the PHYSICAL path governs discovery and the
    returned workspace. Rationale (see binding.find_board_dir): the
    codebase already canonicalizes every workspace path (S2), giving a
    board ONE identity however it is reached; and `os.getcwd()` is already
    physical on POSIX, so a logical-path rule would not be reliably
    observable anyway. On Windows, symlink creation may require elevation
    — skipped with a clear reason if the OS refuses (Linux CI exercises
    it)."""
    real_parent = tmp_path / "real"
    proj = real_parent / "proj"
    nested = proj / "sub"
    nested.mkdir(parents=True)
    key = _write_keyed_board(proj)

    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real_parent, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation not permitted on this OS/user: {exc}")

    start_through_link = alias / "proj" / "sub"
    binding = resolve_binding(start_through_link)
    # Physical path governs: the workspace is the REAL project dir.
    assert Path(binding.workspace) == proj.resolve()
    assert binding.board_key == key


def test_case5_plain_tree_no_git_discovery_works(tmp_path: Path, no_workspace_env):
    """Case 5 — no `.git` anywhere. Discovery has zero VCS dependency: a
    plain directory tree resolves exactly like a repo would."""
    proj = tmp_path / "plain" / "proj"
    nested = proj / "x" / "y" / "z"
    nested.mkdir(parents=True)
    key = _write_keyed_board(proj)

    assert not any(p.name == ".git" for p in tmp_path.rglob("*"))
    binding = resolve_binding(nested)
    assert Path(binding.workspace) == proj.resolve()
    assert binding.board_key == key


def test_case6_moved_folder_same_board_key(tmp_path: Path, no_workspace_env):
    """Case 6 — moved folder. Provision, move the whole project dir,
    resolve from inside the new location: the SAME board is found with the
    SAME key. Identity lives in the board file, not the path — the whole
    point of not using path-derived keys (ADR 0002 non-goal)."""
    from kanbanger.provision import provision_project

    old_parent = tmp_path / "old-home"
    proj = old_parent / "proj"
    proj.mkdir(parents=True)
    provision_project(proj)
    key = read_board_key(proj / "_kanban.md")
    assert key is not None
    (proj / "x" / "y").mkdir(parents=True)

    new_parent = tmp_path / "new-home"
    new_parent.mkdir()
    moved = new_parent / "proj-renamed"
    shutil.move(str(proj), str(moved))

    binding = resolve_binding(moved / "x" / "y")
    assert Path(binding.workspace) == moved.resolve()
    assert binding.board_key == key  # identity survived the move


def test_case7_copied_board_copies_share_key_and_resolve_locally(
    tmp_path: Path, no_workspace_env
):
    """Case 7 — copied board. DEFINED SEMANTICS: both copies carry the SAME
    key (a faithful copy IS the same board identity-wise). Local board ops
    are unaffected — discovery resolves whichever copy encloses the start
    dir, and each copy is operated on independently. The key collision
    matters for SYNC STATE, where it is detectable: see the
    verify_board_key tests below for the state-vs-board mismatch guard."""
    from kanbanger.provision import provision_project

    original = tmp_path / "original"
    original.mkdir()
    provision_project(original)
    (original / "sub").mkdir()
    key = read_board_key(original / "_kanban.md")
    assert key is not None

    copy = tmp_path / "copy"
    shutil.copytree(original, copy)

    # Both copies carry the same minted key.
    assert read_board_key(copy / "_kanban.md") == key

    # Local ops: each copy resolves to ITSELF from inside itself.
    from_original = resolve_binding(original / "sub")
    from_copy = resolve_binding(copy / "sub")
    assert Path(from_original.workspace) == original.resolve()
    assert Path(from_copy.workspace) == copy.resolve()
    assert from_original.board_key == from_copy.board_key == key


# ---------------------------------------------------------------------------
# 2. Server integration: get_workspace / tools use the resolution chain
# ---------------------------------------------------------------------------


def test_get_workspace_walks_up_from_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("KANBANGER_WORKSPACE", raising=False)
    proj = tmp_path / "proj"
    nested = proj / "a" / "b"
    nested.mkdir(parents=True)
    _write_keyed_board(proj)
    monkeypatch.chdir(nested)

    from kanbanger.tools import get_workspace

    assert Path(get_workspace()) == proj.resolve()


def test_resources_get_workspace_agrees_with_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Tools and resources must never resolve different boards."""
    monkeypatch.delenv("KANBANGER_WORKSPACE", raising=False)
    proj = tmp_path / "proj"
    nested = proj / "inner"
    nested.mkdir(parents=True)
    _write_keyed_board(proj)
    monkeypatch.chdir(nested)

    from kanbanger import resources, tools

    assert tools.get_workspace() == resources.get_workspace()
    assert Path(tools.get_workspace()) == proj.resolve()


def test_add_task_from_nested_cwd_writes_ancestor_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """End-to-end through the tool layer: with no env pin and cwd deep in a
    subfolder, add_task lands on the project's board (case 1 through the
    real tool path), and the minted key rides through the write."""
    monkeypatch.delenv("KANBANGER_WORKSPACE", raising=False)
    proj = tmp_path / "proj"
    nested = proj / "deep" / "deeper"
    nested.mkdir(parents=True)
    key = _write_keyed_board(proj)
    monkeypatch.chdir(nested)

    from tests.conftest import _StubMCPServer
    from kanbanger.tools import register_tools

    stub = _StubMCPServer()
    register_tools(stub)
    out = stub.tools["add_task"]("Discovered from subfolder", "TODO")
    assert "Successfully added" in out

    board_text = (proj / "_kanban.md").read_text(encoding="utf-8")
    assert "Discovered from subfolder" in board_text
    assert extract_board_key(board_text) == key
    # Nothing was created in the start dir.
    assert not (nested / "_kanban.md").exists()


# ---------------------------------------------------------------------------
# 3. Sync-state pairing: the copied-board guard
# ---------------------------------------------------------------------------


def _state_manager(tmp_path: Path):
    from sync_kanban import StateManager

    return StateManager(str(tmp_path / "_kanban.md"))


def test_verify_board_key_adopts_key_on_first_sync(tmp_path: Path):
    """First sync against a keyed board records the key in .kanban.json
    (persisted by save), so later runs can detect a swapped/copied pair."""
    _write_keyed_board(tmp_path)
    key = read_board_key(tmp_path / "_kanban.md")

    sm = _state_manager(tmp_path)
    sm.load()
    sm.verify_board_key(key)
    assert sm.state["board_key"] == key

    sm.save()
    state_on_disk = json.loads(
        (tmp_path / ".kanban.json").read_text(encoding="utf-8")
    )
    assert state_on_disk["board_key"] == key


def test_verify_board_key_match_is_noop(tmp_path: Path):
    key = _write_keyed_board(tmp_path)
    (tmp_path / ".kanban.json").write_text(
        json.dumps({"schema_version": 1, "board_key": key, "tasks": {}}),
        encoding="utf-8",
    )
    sm = _state_manager(tmp_path)
    sm.load()
    sm.verify_board_key(key)  # must not raise
    assert sm.state["board_key"] == key


def test_verify_board_key_mismatch_raises_copied_board_error(tmp_path: Path):
    """State recorded for board A paired with board B on disk -> a clear,
    structured refusal naming the copied-board suspicion and the fix."""
    from sync_kanban import ConfigurationError

    _write_keyed_board(tmp_path, key="b" * 32)
    (tmp_path / ".kanban.json").write_text(
        json.dumps({"schema_version": 1, "board_key": "a" * 32, "tasks": {}}),
        encoding="utf-8",
    )
    sm = _state_manager(tmp_path)
    sm.load()
    with pytest.raises(ConfigurationError, match=r"different board \(copied\?\)"):
        sm.verify_board_key("b" * 32)


def test_verify_board_key_skips_unkeyed_board(tmp_path: Path):
    """Legacy unkeyed boards keep syncing: a None board key is never
    checked, even against state that records a key."""
    (tmp_path / "_kanban.md").write_text(FIVE_COL, encoding="utf-8")
    (tmp_path / ".kanban.json").write_text(
        json.dumps({"schema_version": 1, "board_key": "a" * 32, "tasks": {}}),
        encoding="utf-8",
    )
    sm = _state_manager(tmp_path)
    sm.load()
    sm.verify_board_key(None)  # must not raise, must not overwrite
    assert sm.state["board_key"] == "a" * 32


def test_syncer_blocks_on_board_key_mismatch_before_any_network(tmp_path: Path):
    """Wiring proof: Syncer.sync runs the guard BEFORE touching GitHub.
    client=None would raise AttributeError on first use — the
    ConfigurationError from the guard must win."""
    from sync_kanban import ConfigurationError, LocalBoard, StateManager, Syncer

    _write_keyed_board(tmp_path, key="c" * 32)
    (tmp_path / ".kanban.json").write_text(
        json.dumps({"schema_version": 1, "board_key": "d" * 32, "tasks": {}}),
        encoding="utf-8",
    )
    board_path = str(tmp_path / "_kanban.md")
    syncer = Syncer(LocalBoard(board_path), StateManager(board_path), client=None)
    with pytest.raises(ConfigurationError, match="different board"):
        syncer.sync("owner/repo")


def test_classify_sync_stderr_maps_board_key_mismatch():
    """The MCP wrapper translates the guard's CLI error line into the
    stable `board_key_mismatch` error code."""
    from kanbanger.tools import ERROR_BOARD_KEY_MISMATCH, _classify_sync_stderr

    stderr = (
        "Error: sync state belongs to a different board (copied?): "
        ".kanban.json records board key aaa, but _kanban.md carries key bbb.\n"
    )
    assert _classify_sync_stderr(stderr) == ERROR_BOARD_KEY_MISMATCH
