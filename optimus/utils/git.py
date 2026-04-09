"""
Git utilities — root detection and canonical repo resolution.
Mirrors src/utils/git.ts (root-finding portion).

Full git.ts is large; remaining helpers (gitExe, getIsGit, diff helpers) will
be ported incrementally as dependents are added.
"""
from __future__ import annotations

import os
import shutil
import unicodedata
from functools import lru_cache
from pathlib import Path

# ---------------------------------------------------------------------------
# LRU-backed find_git_root (max 50 entries, same as TS memoizeWithLRU(50))
# ---------------------------------------------------------------------------

_GIT_ROOT_NOT_FOUND = object()

_find_root_cache: dict[str, str | object] = {}
_find_root_order: list[str] = []
_LRU_MAX = 50


def _lru_find_root_impl(start_path: str) -> str | object:
    if start_path in _find_root_cache:
        # Move to end (most-recently-used)
        _find_root_order.remove(start_path)
        _find_root_order.append(start_path)
        return _find_root_cache[start_path]

    result = _compute_find_root(start_path)

    # Evict LRU entry if needed
    if len(_find_root_order) >= _LRU_MAX:
        oldest = _find_root_order.pop(0)
        _find_root_cache.pop(oldest, None)

    _find_root_cache[start_path] = result
    _find_root_order.append(start_path)
    return result


def _compute_find_root(start_path: str) -> str | object:
    current = os.path.realpath(os.path.abspath(start_path))
    # Walk up to filesystem root
    while True:
        git_path = os.path.join(current, ".git")
        try:
            st = os.stat(git_path)
            # .git can be a dir (regular repo) or file (worktree/submodule)
            import stat as _stat
            if _stat.S_ISDIR(st.st_mode) or _stat.S_ISREG(st.st_mode):
                return unicodedata.normalize("NFC", current)
        except OSError:
            pass
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return _GIT_ROOT_NOT_FOUND


def find_git_root(start_path: str) -> str | None:
    """Walk up from *start_path* looking for a .git dir or file.

    Returns the directory that contains .git, or None if not found.
    Memoized with an LRU cache (max 50 entries).
    """
    result = _lru_find_root_impl(start_path)
    return None if result is _GIT_ROOT_NOT_FOUND else result  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Canonical root resolution (worktree → main repo)
# ---------------------------------------------------------------------------

_canonical_cache: dict[str, str] = {}
_canonical_order: list[str] = []


def _resolve_canonical_root(git_root: str) -> str:
    """Resolve a git_root through the worktree chain to the main repo root.

    For a regular repo this is a no-op. For a worktree, follows the
    `.git` file → `gitdir:` → `commondir` chain.
    """
    if git_root in _canonical_cache:
        _canonical_order.remove(git_root)
        _canonical_order.append(git_root)
        return _canonical_cache[git_root]

    result = _compute_canonical_root(git_root)

    if len(_canonical_order) >= _LRU_MAX:
        oldest = _canonical_order.pop(0)
        _canonical_cache.pop(oldest, None)

    _canonical_cache[git_root] = result
    _canonical_order.append(git_root)
    return result


def _compute_canonical_root(git_root: str) -> str:
    try:
        git_file = os.path.join(git_root, ".git")
        git_content = Path(git_file).read_text(encoding="utf-8").strip()
        if not git_content.startswith("gitdir:"):
            return git_root

        worktree_git_dir = os.path.realpath(
            os.path.join(git_root, git_content[len("gitdir:"):].strip())
        )

        # commondir points to the shared .git dir (relative to worktree gitdir).
        # Submodules have no commondir → fall through.
        common_dir_rel = Path(os.path.join(worktree_git_dir, "commondir")).read_text(
            encoding="utf-8"
        ).strip()
        common_dir = os.path.realpath(os.path.join(worktree_git_dir, common_dir_rel))

        # SECURITY: Validate that worktreeGitDir is a direct child of <commonDir>/worktrees/
        if os.path.realpath(os.path.dirname(worktree_git_dir)) != os.path.join(
            common_dir, "worktrees"
        ):
            return git_root

        # Validate backlink: <worktreeGitDir>/gitdir must point back to <gitRoot>/.git
        backlink = os.path.realpath(
            Path(os.path.join(worktree_git_dir, "gitdir")).read_text(encoding="utf-8").strip()
        )
        expected = os.path.join(os.path.realpath(git_root), ".git")
        if backlink != expected:
            return git_root

        # Bare-repo worktrees: common dir is not inside a working directory
        if os.path.basename(common_dir) != ".git":
            return unicodedata.normalize("NFC", common_dir)

        return unicodedata.normalize("NFC", os.path.dirname(common_dir))
    except OSError:
        return git_root


def find_canonical_git_root(start_path: str) -> str | None:
    """Like find_git_root but resolves worktrees to the main repo root.

    All worktrees of the same repo map to the same project identity.
    Use this for project-scoped state (auto-memory, project config, etc.).
    """
    root = find_git_root(start_path)
    if root is None:
        return None
    return _resolve_canonical_root(root)


# ---------------------------------------------------------------------------
# git executable
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def git_exe() -> str:
    return shutil.which("git") or "git"


async def get_is_git() -> bool:
    """Return True if the current working directory is inside a git repo."""
    from optimus.utils.cwd import get_cwd
    return find_git_root(get_cwd()) is not None
