"""Conversation-session naming helpers for configured agents."""

from __future__ import annotations


CONVERSATION_PREFIX = "agent-repl-"


def conversation_session_name(agent_name: str) -> str:
    return CONVERSATION_PREFIX + (agent_name or "").strip().lower()


def agent_name_from_session(session_name: str) -> str | None:
    name = (session_name or "").strip()
    if not name.startswith(CONVERSATION_PREFIX):
        return None
    agent_name = name[len(CONVERSATION_PREFIX):].strip().lower()
    return agent_name or None
