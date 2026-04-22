"""LLM-backed ``tb agent`` execution loop."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import agent_logs, agent_providers
from .errors import TmuxFailed, UsageError


SYSTEM_PROMPT = """You are a tmux operations agent embedded in tb.py.

You do not have shell access directly. You have exactly one tool:
`tb_command`.

Use it to run non-interactive tb.py commands and inspect their results.
Prefer JSON output by asking for commands that can sensibly include `--json`.

Important rules:
- Never ask for confirmation. Keep working until the task is complete or blocked.
- Never recurse into `tb agent`.
- Prefer `snapshot`, `ls`, `show`, `capture`, and `exec` to understand tmux state.
- For commands inside panes, use `tb exec TARGET --timeout ... -- <command>`.
- Keep command count efficient. Read state first, then act, then verify.
- When the task is complete, return a concise final message describing what you did and any remaining issue.

You must respond with JSON only, one object per turn, in one of these shapes:
{"type":"tool","tool":"tb_command","args":["snapshot","--json"],"stdin":""}
{"type":"final","message":"done"}
"""


def _preview(text: str, head: int = 160, tail: int = 80) -> str:
    raw = text.strip()
    if len(raw) <= head + tail + 5:
        return raw
    return raw[:head] + " ... " + raw[-tail:]


def _extract_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise UsageError(f"agent returned non-JSON output (preview): {_preview(text)!r}")
    try:
        data = json.loads(raw[start:end + 1])
    except ValueError as e:
        raise UsageError(f"agent returned invalid JSON: {e}; preview={_preview(raw[start:end + 1])!r}")
    if not isinstance(data, dict):
        raise UsageError("agent response must be a JSON object")
    return data


# Provider dispatch lives in agent_providers — one adapter per wire API.


@dataclass
class ToolResult:
    ok: bool
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    json_data: Any = None


def _run_tb_command(repo_root: Path, args: list[str], stdin_text: str | None) -> ToolResult:
    if not args:
        raise UsageError("tb_command args must not be empty")
    verb = args[0]
    if verb in {"agent", "attach", "watch"}:
        raise UsageError(f"`tb {verb}` is not allowed from tb agent")
    cmd = [sys.executable, str(repo_root / "tb.py"), verb, "--json", *args[1:]]
    proc = subprocess.run(
        cmd,
        input=stdin_text if stdin_text is not None else None,
        text=True,
        capture_output=True,
        cwd=str(repo_root),
    )
    parsed = None
    stdout = proc.stdout or ""
    if stdout.strip():
        try:
            parsed = json.loads(stdout)
        except ValueError:
            parsed = None
    return ToolResult(
        ok=proc.returncode == 0,
        command=cmd,
        exit_code=proc.returncode,
        stdout=stdout,
        stderr=proc.stderr or "",
        json_data=parsed,
    )


def run_agent(agent: dict[str, Any], prompt: str, *,
              repo_root: Path,
              max_steps: int = 100,
              request_timeout: float = 90.0,
              origin: str = "cli") -> dict[str, Any]:
    if not prompt.strip():
        raise UsageError("missing agent prompt")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt.strip()},
    ]
    transcript: list[dict[str, Any]] = []
    try:
        for step in range(1, max_steps + 1):
            raw = agent_providers.complete(agent, messages, timeout=request_timeout)
            try:
                action = _extract_json(raw)
            except UsageError as e:
                transcript.append({"step": step, "model": raw, "parse_error": e.message})
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous response did not follow the required protocol. "
                        "Respond again with JSON only, using exactly one object in one of the allowed shapes. "
                        "Do not include prose, markdown fences, or <think> tags."
                    ),
                })
                continue
            transcript.append({"step": step, "model": raw, "action": action})
            if action.get("type") == "final":
                out = {
                    "agent": agent["name"],
                    "model": agent["model"],
                    "steps": step,
                    "message": str(action.get("message") or "").strip(),
                    "transcript": transcript,
                }
                agent_logs.append_entry(agent["name"], {
                    "origin": origin,
                    "status": "ok",
                    "prompt": prompt.strip(),
                    "message": out["message"],
                    "steps": step,
                    "model": agent.get("model"),
                    "transcript": transcript,
                })
                return out
            if action.get("type") != "tool" or action.get("tool") != "tb_command":
                raise UsageError("agent must return either a final action or a tb_command tool action")
            tool_args = action.get("args")
            if not isinstance(tool_args, list) or not all(isinstance(x, str) for x in tool_args):
                raise UsageError("tb_command args must be a list of strings")
            stdin_text = action.get("stdin")
            if stdin_text is not None and not isinstance(stdin_text, str):
                raise UsageError("tb_command stdin must be a string when present")
            result = _run_tb_command(repo_root, tool_args, stdin_text)
            tool_payload = {
                "ok": result.ok,
                "exit_code": result.exit_code,
                "stdout": result.stdout[-12000:],
                "stderr": result.stderr[-4000:],
                "json": result.json_data,
            }
            transcript[-1]["tool_result"] = tool_payload
            messages.append({"role": "assistant", "content": json.dumps(action)})
            messages.append({
                "role": "user",
                "content": "Tool result for tb_command:\n" + json.dumps(tool_payload, ensure_ascii=True),
            })
        raise TmuxFailed(f"agent exceeded max steps ({max_steps})")
    except Exception as e:
        agent_logs.append_entry(agent["name"], {
            "origin": origin,
            "status": "error",
            "prompt": prompt.strip(),
            "error": str(e),
            "model": agent.get("model"),
            "transcript": transcript,
        })
        raise
