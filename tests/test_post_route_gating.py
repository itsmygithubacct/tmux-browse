"""Security invariant: every mutating POST endpoint is gated behind the
config-lock (_check_unlock).

The config-lock is the dashboard's "freeze this view" control — when set,
state-changing endpoints require an unlock token. That protection is only
as good as its coverage: a new POST handler that forgets the gate would
silently bypass the lock. This test fails if any POST route handler omits
_check_unlock, except for the deliberately-exempt unlock endpoint itself.
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.server import Handler  # noqa: E402

# Paths that legitimately do NOT gate on _check_unlock. Adding to this set
# is a deliberate, reviewable act — that's the point.
#   /api/config-lock/verify: the unlock mechanism. It must be reachable
#   while the lock is active, otherwise there's no way to obtain a token.
_UNGATED_BY_DESIGN = {"/api/config-lock/verify"}


class PostRouteGatingTests(unittest.TestCase):

    def test_every_mutating_post_handler_checks_unlock(self):
        offenders = []
        for path, fn in Handler._POST_ROUTES.items():
            if path in _UNGATED_BY_DESIGN:
                continue
            if "_check_unlock" not in inspect.getsource(fn):
                offenders.append(f"{path} -> {fn.__module__}.{fn.__name__}")
        self.assertEqual(
            offenders, [],
            "these POST handlers must gate on handler._check_unlock() "
            "(or be added to _UNGATED_BY_DESIGN with justification):\n"
            + "\n".join(offenders))

    def test_exempt_paths_still_exist(self):
        # Keep the exempt set from rotting: every entry must be a real route.
        for path in _UNGATED_BY_DESIGN:
            self.assertIn(path, Handler._POST_ROUTES,
                          f"{path} is exempt but no longer a POST route")

    def test_exempt_handler_is_actually_ungated(self):
        # If the verify endpoint ever starts gating itself, the lock becomes
        # un-openable — assert it stays ungated so that regression is caught.
        fn = Handler._POST_ROUTES["/api/config-lock/verify"]
        self.assertNotIn("_check_unlock", inspect.getsource(fn))


if __name__ == "__main__":
    unittest.main()
