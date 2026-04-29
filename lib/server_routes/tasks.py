"""HTTP route handlers for the task store + worktree-based launch:
``/api/tasks`` (GET / POST), ``/api/tasks/update``,
``/api/tasks/launch``.
"""

from __future__ import annotations

import shlex
import sys
from typing import TYPE_CHECKING
from urllib.parse import ParseResult

from .. import config, sessions, tasks as tasks_mod, ttyd
from ..errors import TBError

if TYPE_CHECKING:
    from ..server import Handler


def h_tasks_get(handler: "Handler", _parsed: ParseResult) -> None:
    try:
        handler._send_json({
            "ok": True,
            "tasks": tasks_mod.list_tasks(include_archived=False),
        })
    except TBError as e:
        handler._send_tb_error(e)


def h_tasks_create(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    if not handler._check_unlock():
        return
    try:
        task = tasks_mod.create(
            title=(body.get("title") or "").strip(),
            repo_path=(body.get("repo_path") or "").strip(),
            agent=(body.get("agent") or "").strip() or None,
            worktree_path=(body.get("worktree_path") or "").strip(),
            branch=(body.get("branch") or "").strip(),
        )
        handler._send_json({"ok": True, "task": task})
    except TBError as e:
        handler._send_tb_error(e)


def h_tasks_update(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    if not handler._check_unlock():
        return
    task_id = (body.get("id") or "").strip()
    if not task_id:
        handler._send_json({"ok": False, "error": "missing 'id'"}, status=400)
        return
    fields = {k: v for k, v in body.items() if k != "id"}
    try:
        task = tasks_mod.update(task_id, **fields)
        handler._send_json({"ok": True, "task": task})
    except TBError as e:
        handler._send_tb_error(e)


def h_tasks_launch(handler: "Handler", _parsed: ParseResult, body: dict) -> None:
    task_id = (body.get("id") or "").strip()
    if not task_id:
        handler._send_json({"ok": False, "error": "missing 'id'"}, status=400)
        return
    task = tasks_mod.get_task(task_id)
    if not task:
        handler._send_json({"ok": False, "error": "task not found"}, status=404)
        return
    agent_name = (task.get("agent") or "").strip()
    if not agent_name:
        handler._send_json({"ok": False, "error": "no agent assigned to task"}, status=400)
        return
    # Task launch shells out to ``tb agent repl ...`` — that verb is
    # contributed by the agent extension. Refuse here when it isn't
    # registered, otherwise the spawned tmux session crashes silently
    # with "tb: unknown verb agent" and the operator has nothing to
    # debug.
    ext_verbs = handler.server.extension_registry.cli_verbs
    if "agent" not in ext_verbs:
        handler._send_json({
            "ok": False,
            "error": ("the agent extension isn't enabled — install or "
                      "enable it from Config > Extensions before "
                      "launching agent tasks"),
        }, status=409)
        return
    cwd = task.get("worktree_path") or task.get("repo_path") or str(config.PROJECT_DIR)
    session_name = f"task-{task_id}"
    if not sessions.exists(session_name):
        cmd = " ".join([
            shlex.quote(sys.executable), "-u",
            shlex.quote(str(config.PROJECT_DIR / "tb.py")),
            "agent", "repl", shlex.quote(agent_name),
        ])
        ok, err = sessions.new_session(session_name, cwd=cwd, cmd=cmd)
        if not ok:
            handler._send_json({"ok": False, "error": err}, status=400)
            return
    tasks_mod.update(task_id, session=session_name)
    tls_paths = getattr(handler.server, "tls_paths", None)
    bind_addr = getattr(handler.server, "ttyd_bind_addr", None)
    ttyd_result = ttyd.start(session_name, tls_paths=tls_paths, bind_addr=bind_addr)
    handler._send_json({
        "ok": True,
        "task_id": task_id,
        "session": session_name,
        "port": ttyd_result.get("port"),
    })
