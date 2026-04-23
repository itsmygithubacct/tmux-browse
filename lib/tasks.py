"""Optional task abstraction for isolated agent work.

A task links a title, a git repo, an optional worktree, an assigned
agent, and a tmux session.  Tasks are persisted in
``~/.tmux-browse/tasks.json`` and are entirely optional — agents work
fine without them.

Task statuses: ``open``, ``done``, ``archived``.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from . import config, worktrees
from .errors import StateError, UsageError


TASKS_FILE = config.STATE_DIR / "tasks.json"

VALID_STATUSES = {"open", "done", "archived"}


def _load() -> list[dict[str, Any]]:
    if not TASKS_FILE.exists():
        return []
    try:
        data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []


def _save(tasks: list[dict[str, Any]]) -> None:
    config.ensure_dirs()
    tmp = TASKS_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
        tmp.replace(TASKS_FILE)
    except OSError as e:
        raise StateError(f"cannot write {TASKS_FILE}: {e.strerror or e}")


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def create(*, title: str, repo_path: str, agent: str | None = None,
           branch: str | None = None, use_worktree: bool = True) -> dict[str, Any]:
    """Create a new task. Optionally provisions a git worktree."""
    title = (title or "").strip()
    if not title:
        raise UsageError("task title required")
    repo = Path(repo_path).expanduser().resolve()
    if not repo.is_dir():
        raise UsageError(f"repo path does not exist: {repo}")

    task_id = _new_id()
    slug = f"{task_id}-{worktrees._slugify(title)}"

    wt_path = ""
    wt_branch = ""
    if use_worktree:
        wt = worktrees.create(repo, slug, branch=branch)
        wt_path = wt["path"]
        wt_branch = wt["branch"]

    task: dict[str, Any] = {
        "id": task_id,
        "title": title,
        "status": "open",
        "repo_path": str(repo),
        "worktree_path": wt_path,
        "branch": wt_branch,
        "agent": (agent or "").strip().lower() or None,
        "session": "",
        "created_ts": int(time.time()),
        "updated_ts": int(time.time()),
    }
    tasks = _load()
    tasks.append(task)
    _save(tasks)
    return task


def list_tasks(*, status: str | None = None,
               include_archived: bool = False) -> list[dict[str, Any]]:
    """Return tasks, optionally filtered by status."""
    tasks = _load()
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    elif not include_archived:
        tasks = [t for t in tasks if t.get("status") != "archived"]
    return tasks


def get_task(task_id: str) -> dict[str, Any] | None:
    for t in _load():
        if t.get("id") == task_id:
            return t
    return None


def update(task_id: str, **fields: Any) -> dict[str, Any]:
    """Update fields on a task. Returns the updated task."""
    tasks = _load()
    for i, t in enumerate(tasks):
        if t.get("id") == task_id:
            for key, val in fields.items():
                if key == "status" and val not in VALID_STATUSES:
                    raise UsageError(f"invalid status: {val}")
                if key in {"id", "created_ts"}:
                    continue
                t[key] = val
            t["updated_ts"] = int(time.time())
            tasks[i] = t
            _save(tasks)
            return t
    raise UsageError(f"task {task_id} not found")


def archive(task_id: str, *, cleanup_worktree: bool = False) -> dict[str, Any]:
    """Mark a task as archived. Optionally remove its worktree."""
    task = update(task_id, status="archived")
    if cleanup_worktree and task.get("worktree_path") and task.get("repo_path"):
        slug = Path(task["worktree_path"]).name
        try:
            worktrees.remove(task["repo_path"], slug, force=True)
        except Exception:
            pass
    return task
