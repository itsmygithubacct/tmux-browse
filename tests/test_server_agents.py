"""Dashboard agent API handlers."""

import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402
from lib.errors import StateError, UsageError  # noqa: E402


class _FakeHandler:
    def __init__(self):
        self.payload = None
        self.status = None

    def _send_json(self, obj, status=200):
        self.payload = obj
        self.status = status

    def _send_tb_error(self, err):
        return server.Handler._send_tb_error(self, err)


class AgentRouteTableTests(unittest.TestCase):

    def test_routes_are_registered(self):
        self.assertIn("/api/agents", server.Handler._GET_ROUTES)
        self.assertIn("/api/agents", server.Handler._POST_ROUTES)
        self.assertIn("/api/agents/remove", server.Handler._POST_ROUTES)


class AgentHandlerTests(unittest.TestCase):

    def test_agents_get_returns_public_rows_and_catalog(self):
        fake = _FakeHandler()
        with mock.patch("lib.server.agent_store.list_agents", return_value=[{
            "name": "gpt", "provider": "openai", "model": "gpt-5.4",
            "base_url": "https://api.openai.com/v1", "wire_api": "openai-chat",
            "has_api_key": True,
        }]), mock.patch("lib.server.agent_store.catalog_rows", return_value=[{
            "name": "gpt", "label": "OpenAI GPT", "provider": "openai",
            "model": "gpt-5.4", "base_url": "https://api.openai.com/v1",
            "wire_api": "openai-chat",
        }]), mock.patch("lib.server.agent_store.AGENTS_FILE", Path("/tmp/agents.json")), mock.patch(
            "lib.server.agent_store.SECRETS_FILE", Path("/tmp/agent-secrets.json"),
        ):
            server.Handler._h_agents_get(fake, urlparse("/api/agents"))
        self.assertEqual(fake.status, 200)
        self.assertTrue(fake.payload["ok"])
        self.assertEqual(fake.payload["agents"][0]["name"], "gpt")
        self.assertNotIn("api_key", fake.payload["agents"][0])
        self.assertEqual(fake.payload["defaults"][0]["label"], "OpenAI GPT")
        self.assertEqual(fake.payload["paths"]["agents"], "/tmp/agents.json")

    def test_agents_post_saves_agent(self):
        fake = _FakeHandler()
        with mock.patch("lib.server.agent_store.save_agent", return_value={
            "name": "gpt",
            "provider": "openai",
            "model": "gpt-5.4",
            "base_url": "https://api.openai.com/v1",
            "wire_api": "openai-chat",
            "has_api_key": True,
        }) as save_agent:
            server.Handler._h_agents_post(fake, urlparse("/api/agents"), {
                "agent": {
                    "name": "gpt",
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "base_url": "https://api.openai.com/v1",
                    "wire_api": "openai-chat",
                    "api_key": "sk-abc",
                },
            })
        self.assertEqual(fake.status, 200)
        self.assertEqual(fake.payload["agent"]["name"], "gpt")
        save_agent.assert_called_once_with(
            "gpt",
            api_key="sk-abc",
            model="gpt-5.4",
            base_url="https://api.openai.com/v1",
            provider="openai",
            wire_api="openai-chat",
        )

    def test_agents_post_maps_usage_error_to_400(self):
        fake = _FakeHandler()
        with mock.patch("lib.server.agent_store.save_agent", side_effect=UsageError("bad agent")):
            server.Handler._h_agents_post(fake, urlparse("/api/agents"), {
                "agent": {"name": "", "provider": "", "model": "", "base_url": "", "wire_api": ""},
            })
        self.assertEqual(fake.status, 400)
        self.assertFalse(fake.payload["ok"])
        self.assertEqual(fake.payload["error"], "bad agent")

    def test_agents_remove_returns_removed_state(self):
        fake = _FakeHandler()
        with mock.patch("lib.server.agent_store.remove_agent", return_value=True) as remove_agent:
            server.Handler._h_agents_remove(fake, urlparse("/api/agents/remove"), {"name": "gpt"})
        self.assertEqual(fake.status, 200)
        self.assertTrue(fake.payload["removed"])
        remove_agent.assert_called_once_with("gpt")

    def test_agents_get_maps_state_error_to_json_500(self):
        fake = _FakeHandler()
        with mock.patch("lib.server.agent_store.list_agents", side_effect=StateError("broken store")):
            server.Handler._h_agents_get(fake, urlparse("/api/agents"))
        self.assertEqual(fake.status, 500)
        self.assertFalse(fake.payload["ok"])
        self.assertEqual(fake.payload["error"], "broken store")


if __name__ == "__main__":
    unittest.main()
