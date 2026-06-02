"""Lightweight task abstraction used by the agent extension.

A task links a title, a git repo path, an optional worktree path,
an assigned agent name, and a tmux session.  Tasks are persisted
in ``~/.tmux-browse/tasks.json``.

Worktree lifecycle lives in the agent extension (``agent.worktrees``)
— core tasks just record paths. A caller who wants a worktree
provisions it, then calls :func:`update` to attach the path to the
task.

Task statuses: ``open``, ``done``, ``archived``.
"""

from __future__ import annotations

import fcntl
import json
import shutil
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import config
from .errors import StateError, UsageError


TASKS_FILE = config.STATE_DIR / "tasks.json"

VALID_STATUSES = {"open", "done", "archived"}


def _recover_corrupt(path: Path, err: Exception | str) -> list[dict[str, Any]]:
    """Move a corrupt task store aside and continue with an empty list."""
    backup = path.with_suffix(path.suffix + f".corrupt.{int(time.time())}")
    try:
        shutil.copy2(path, backup)
    except OSError:
        backup = None
    sys.stderr.write(
        f"tmux-browse: task store at {path} was corrupt ({err}); reinitialised"
        + (f", backup kept at {backup}" if backup else "")
        + "\n",
    )
    return []


def _write_tasks_file(f, tasks: list[dict[str, Any]]) -> None:
    f.seek(0)
    f.truncate()
    json.dump(tasks, f, indent=2)
    f.write("\n")
    f.flush()


@contextmanager
def _locked_tasks():
    """Yield ``(tasks, save_fn)`` with the task file locked for mutation."""
    config.ensure_dirs()
    try:
        TASKS_FILE.touch(exist_ok=True)
    except OSError as e:
        raise StateError(f"cannot create {TASKS_FILE}: {e.strerror or e}")
    try:
        f = TASKS_FILE.open("r+", encoding="utf-8")
    except OSError as e:
        raise StateError(f"cannot open {TASKS_FILE}: {e.strerror or e}")
    with f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX)
        except OSError as e:
            raise StateError(f"cannot lock {TASKS_FILE}: {e.strerror or e}")
        try:
            repaired = False
            try:
                f.seek(0)
                raw = f.read()
                if raw.strip():
                    try:
                        data = json.loads(raw)
                    except (ValueError, TypeError) as e:
                        data = _recover_corrupt(TASKS_FILE, e)
                        repaired = True
                else:
                    data = []
            except OSError as e:
                data = _recover_corrupt(TASKS_FILE, e)
                repaired = True
            if not isinstance(data, list):
                data = _recover_corrupt(TASKS_FILE, "expected a JSON list")
                repaired = True
            tasks = data
            if repaired:
                try:
                    _write_tasks_file(f, tasks)
                except OSError as e:
                    raise StateError(
                        f"cannot write {TASKS_FILE}: {e.strerror or e}",
                    )

            def save() -> None:
                try:
                    _write_tasks_file(f, tasks)
                except OSError as e:
                    raise StateError(
                        f"cannot write {TASKS_FILE}: {e.strerror or e}",
                    )

            yield tasks, save
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _load() -> list[dict[str, Any]]:
    with _locked_tasks() as (tasks, _save):
        return [dict(t) for t in tasks]


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def create(*, title: str, repo_path: str, agent: str | None = None,
           worktree_path: str = "", branch: str = "") -> dict[str, Any]:
    """Create a new task.

    ``worktree_path`` and ``branch`` are free-form strings — core
    doesn't provision or validate them. Callers that want a git
    worktree create it themselves (e.g. via ``agent.worktrees`` in
    the agent extension) and pass the resulting path here.
    """
    title = (title or "").strip()
    if not title:
        raise UsageError("task title required")
    repo = Path(repo_path).expanduser().resolve()
    if not repo.is_dir():
        raise UsageError(f"repo path does not exist: {repo}")

    task_id = _new_id()
    task: dict[str, Any] = {
        "id": task_id,
        "title": title,
        "status": "open",
        "repo_path": str(repo),
        "worktree_path": str(worktree_path or ""),
        "branch": str(branch or ""),
        "agent": (agent or "").strip().lower() or None,
        "session": "",
        "created_ts": int(time.time()),
        "updated_ts": int(time.time()),
    }
    with _locked_tasks() as (tasks, save):
        tasks.append(task)
        save()
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
    with _locked_tasks() as (tasks, _save):
        for t in tasks:
            if t.get("id") == task_id:
                return dict(t)
    return None


def update(task_id: str, **fields: Any) -> dict[str, Any]:
    """Update fields on a task. Returns the updated task."""
    with _locked_tasks() as (tasks, save):
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
                save()
                return dict(t)
    raise UsageError(f"task {task_id} not found")


def archive(task_id: str) -> dict[str, Any]:
    """Mark a task as archived.

    Worktree cleanup (if any) is the caller's responsibility —
    whoever created the worktree owns its lifecycle.
    """
    task = update(task_id, status="archived")
    return task
