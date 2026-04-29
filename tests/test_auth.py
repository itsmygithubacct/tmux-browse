"""Auth primitives: token resolution, extraction, constant-time compare."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import auth  # noqa: E402
from lib.errors import StateError  # noqa: E402


class _FakeHandler:
    """Minimal shim matching the attrs auth.extract_token reads."""
    def __init__(self, headers: dict, path: str = "/"):
        self.headers = headers
        self.path = path


class LoadTokenTests(unittest.TestCase):

    def setUp(self):
        self._orig = os.environ.pop("TMUX_BROWSE_TOKEN", None)

    def tearDown(self):
        if self._orig is not None:
            os.environ["TMUX_BROWSE_TOKEN"] = self._orig

    def test_cli_wins_over_env(self):
        os.environ["TMUX_BROWSE_TOKEN"] = "envtok"
        self.assertEqual(auth.load_token(cli_token="clitok"), "clitok")

    def test_file_wins_over_env(self):
        os.environ["TMUX_BROWSE_TOKEN"] = "envtok"
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("filetok\n")
            path = f.name
        try:
            self.assertEqual(auth.load_token(cli_token_file=path), "filetok")
        finally:
            os.unlink(path)

    def test_env_used_when_nothing_else(self):
        os.environ["TMUX_BROWSE_TOKEN"] = "envtok"
        self.assertEqual(auth.load_token(), "envtok")

    def test_whitespace_only_disables_auth(self):
        self.assertIsNone(auth.load_token(cli_token="   "))
        self.assertIsNone(auth.load_token(cli_token=""))

    def test_missing_file_raises_state_error(self):
        with self.assertRaises(StateError):
            auth.load_token(cli_token_file="/nonexistent/path/for/token")

    def test_file_first_nonempty_line_wins(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("\n   \n\ngoodtok\nlaterline\n")
            path = f.name
        try:
            self.assertEqual(auth.load_token(cli_token_file=path), "goodtok")
        finally:
            os.unlink(path)


class ExtractTokenTests(unittest.TestCase):

    def test_bearer_header(self):
        h = _FakeHandler({"Authorization": "Bearer abc123"})
        self.assertEqual(auth.extract_token(h), "abc123")

    def test_bearer_header_case_insensitive_scheme(self):
        h = _FakeHandler({"Authorization": "bearer abc123"})
        self.assertEqual(auth.extract_token(h), "abc123")

    def test_cookie_fallback(self):
        h = _FakeHandler({"Cookie": "tb_auth=cookietok; other=x"})
        self.assertEqual(auth.extract_token(h), "cookietok")

    def test_query_string_fallback(self):
        h = _FakeHandler({}, path="/?token=qtok")
        self.assertEqual(auth.extract_token(h), "qtok")

    def test_bearer_wins_over_cookie(self):
        h = _FakeHandler({
            "Authorization": "Bearer bt",
            "Cookie": "tb_auth=ct",
        })
        self.assertEqual(auth.extract_token(h), "bt")

    def test_no_token_returns_none(self):
        h = _FakeHandler({})
        self.assertIsNone(auth.extract_token(h))


class MatchesTests(unittest.TestCase):

    def test_exact_match(self):
        self.assertTrue(auth.matches("abc", "abc"))

    def test_mismatch(self):
        self.assertFalse(auth.matches("abc", "abd"))

    def test_empty_given_rejected(self):
        self.assertFalse(auth.matches("abc", ""))
        self.assertFalse(auth.matches("abc", None))


class PathIsOpenTests(unittest.TestCase):

    def test_health_is_open(self):
        self.assertTrue(auth.path_is_open("/health"))
        self.assertTrue(auth.path_is_open("/health?foo=1"))

    def test_other_paths_are_gated(self):
        self.assertFalse(auth.path_is_open("/"))
        self.assertFalse(auth.path_is_open("/api/sessions"))


class CookieTests(unittest.TestCase):

    def test_httponly_and_samesite_set(self):
        header = auth.make_cookie_header("tok123")
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Lax", header)
        self.assertIn("Path=/", header)
        self.assertTrue(header.startswith("tb_auth=tok123"))

    def test_max_age_respected(self):
        header = auth.make_cookie_header("tok", max_age=42)
        self.assertIn("Max-Age=42", header)


class SuggestTokenTests(unittest.TestCase):

    def test_returns_nonempty_string(self):
        t = auth.suggest_token()
        self.assertIsInstance(t, str)
        self.assertGreater(len(t), 20)

    def test_calls_are_unique(self):
        self.assertNotEqual(auth.suggest_token(), auth.suggest_token())


if __name__ == "__main__":
    unittest.main()
