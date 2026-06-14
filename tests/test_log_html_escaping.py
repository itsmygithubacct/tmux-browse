"""XSS guard for the log viewer (/api/session/log?html=1).

_log_html / _log_error_html wrap untrusted terminal scrollback and the
(also untrusted) session name into an HTML page. If the escaping
regressed, terminal output containing markup would execute in the
operator's browser. Pin the escaping behaviour.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import server  # noqa: E402


class HtmlEscapeTests(unittest.TestCase):

    def test_escapes_the_dangerous_set(self):
        self.assertEqual(server._html_escape('<>&"'),
                         "&lt;&gt;&amp;&quot;")

    def test_ampersand_escaped_first_no_double_encoding(self):
        # If '<' were escaped before '&', "&lt;" would become "&amp;lt;".
        self.assertEqual(server._html_escape("<"), "&lt;")
        self.assertEqual(server._html_escape("a & b"), "a &amp; b")

    def test_plain_text_untouched(self):
        self.assertEqual(server._html_escape("hello world 123"),
                         "hello world 123")


class LogHtmlEscapingTests(unittest.TestCase):

    def test_content_markup_is_escaped(self):
        payload = "</pre><script>alert(document.cookie)</script>"
        html = server._log_html("work", payload)
        # The injected script must appear only in escaped form.
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert(document.cookie)&lt;/script&gt;", html)

    def test_session_name_in_title_is_escaped(self):
        html = server._log_html("<img src=x onerror=alert(1)>", "body")
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)

    def test_our_autoscroll_script_is_still_present(self):
        # Sanity: the page's own (trusted) script must survive escaping of
        # the content — we escape the content, not the template.
        html = server._log_html("work", "line1\nline2")
        self.assertIn("window.scrollTo", html)


class LogErrorHtmlEscapingTests(unittest.TestCase):

    def test_error_name_and_message_escaped(self):
        html = server._log_error_html("<b>name</b>", "<i>oops</i>")
        self.assertNotIn("<b>name</b>", html)
        self.assertNotIn("<i>oops</i>", html)
        self.assertIn("&lt;b&gt;name&lt;/b&gt;", html)
        self.assertIn("&lt;i&gt;oops&lt;/i&gt;", html)


if __name__ == "__main__":
    unittest.main()
