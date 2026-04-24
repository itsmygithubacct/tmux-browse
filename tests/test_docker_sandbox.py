"""Docker sandbox: name sanitization, mount validation, lifecycle, and the
isolation boundary that keeps Docker mode from reaching host tmux."""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import docker_sandbox  # noqa: E402
from lib.errors import StateError, UsageError  # noqa: E402


def _ok(stdout: str = "", stderr: str = "", returncode: int = 0):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr=stderr)


class SanitizeContainerNameTests(unittest.TestCase):

    def test_replaces_unsafe_chars(self):
        name = docker_sandbox.sanitize_container_name("my agent!", "run/1")
        self.assertNotIn(" ", name)
        self.assertNotIn("/", name)
        self.assertNotIn("!", name)

    def test_truncates_to_docker_limit(self):
        name = docker_sandbox.sanitize_container_name("a" * 200, "b" * 200)
        self.assertLessEqual(len(name), 63)

    def test_unsafe_inputs_still_produce_usable_name(self):
        # Even with all-unsafe agent/run inputs, the fixed 'tb-sandbox-'
        # prefix keeps the result valid for Docker.
        name = docker_sandbox.sanitize_container_name("!!!", "@@@")
        self.assertTrue(name.startswith("tb-sandbox"))
        self.assertTrue(all(c.isalnum() or c in "-._" for c in name))

    def test_includes_prefix(self):
        name = docker_sandbox.sanitize_container_name("opus", "r1")
        self.assertTrue(name.startswith("tb-sandbox-"))


class ValidateMountTests(unittest.TestCase):

    def test_blocks_docker_socket(self):
        with self.assertRaises(UsageError):
            docker_sandbox.validate_mount(Path("/var/run/docker.sock"))

    def test_blocks_etc(self):
        with self.assertRaises(UsageError):
            docker_sandbox.validate_mount(Path("/etc"))

    def test_blocks_under_etc(self):
        with self.assertRaises(UsageError):
            docker_sandbox.validate_mount(Path("/etc/passwd"))

    def test_blocks_proc(self):
        with self.assertRaises(UsageError):
            docker_sandbox.validate_mount(Path("/proc"))

    def test_blocks_sys(self):
        with self.assertRaises(UsageError):
            docker_sandbox.validate_mount(Path("/sys"))

    def test_blocks_ssh_under_home(self):
        ssh_path = Path.home() / ".ssh"
        with self.assertRaises(UsageError):
            docker_sandbox.validate_mount(ssh_path)

    def test_allows_normal_workspace(self):
        # tmp dir is fine
        docker_sandbox.validate_mount(Path("/tmp"))


class TargetEnforcementTests(unittest.TestCase):
    """The most important tests in this file: the isolation boundary."""

    def _make_sandbox(self):
        sb = docker_sandbox.Sandbox(
            agent_name="opus",
            run_id="r1",
            workspace=Path("/tmp"),
            repo_root=Path("/tmp"),
        )
        sb._created = True  # bypass lifecycle for boundary tests
        return sb

    def test_first_positional_extracts_target(self):
        self.assertEqual(docker_sandbox._first_positional(["exec", "sandbox:", "--", "ls"]),
                         "sandbox:")
        self.assertEqual(docker_sandbox._first_positional(["read", "sandbox:0"]),
                         "sandbox:0")

    def test_first_positional_skips_flags(self):
        self.assertEqual(
            docker_sandbox._first_positional(["read", "--lines", "50", "sandbox:"]),
            "50",
        )
        # Above is a known limitation — flag *values* are positional too. The
        # boundary check below is intentionally strict regardless.

    def test_first_positional_returns_none_for_no_target(self):
        self.assertIsNone(docker_sandbox._first_positional(["snapshot", "--json"]))
        self.assertIsNone(docker_sandbox._first_positional(["snapshot"]))

    def test_target_compatibility(self):
        self.assertTrue(docker_sandbox._target_is_sandbox_compatible("sandbox"))
        self.assertTrue(docker_sandbox._target_is_sandbox_compatible("sandbox:"))
        self.assertTrue(docker_sandbox._target_is_sandbox_compatible("sandbox:0"))
        self.assertTrue(docker_sandbox._target_is_sandbox_compatible("sandbox:0.1"))
        self.assertTrue(docker_sandbox._target_is_sandbox_compatible("sandbox.0"))
        self.assertFalse(docker_sandbox._target_is_sandbox_compatible("host:"))
        self.assertFalse(docker_sandbox._target_is_sandbox_compatible("dashboard:0"))

    def test_exec_tb_rejects_non_sandbox_target_without_invoking_docker(self):
        sb = self._make_sandbox()
        with mock.patch("subprocess.run") as run:
            result = sb.exec_tb(["exec", "host-session:", "--", "ls"], None)
        self.assertFalse(result.ok)
        self.assertIn("not allowed", result.stderr)
        run.assert_not_called()

    def test_exec_tb_allows_sandbox_target(self):
        sb = self._make_sandbox()
        with mock.patch("subprocess.run", return_value=_ok(stdout='{"ok":true}')) as run:
            result = sb.exec_tb(["read", "sandbox:"], None)
        self.assertTrue(result.ok)
        run.assert_called_once()

    def test_exec_tb_allows_no_target_verbs(self):
        sb = self._make_sandbox()
        with mock.patch("subprocess.run", return_value=_ok(stdout='{}')) as run:
            sb.exec_tb(["snapshot", "--json"], None)
        run.assert_called_once()

    def test_exec_tb_blocks_recursive_agent(self):
        sb = self._make_sandbox()
        with self.assertRaises(UsageError):
            sb.exec_tb(["agent", "opus"], None)


class CreateLifecycleTests(unittest.TestCase):

    def _new(self):
        return docker_sandbox.Sandbox(
            agent_name="opus",
            run_id="r1",
            workspace=Path("/tmp"),
            repo_root=Path("/tmp"),
        )

    def test_create_succeeds_when_all_steps_pass(self):
        sb = self._new()
        # docker run, docker inspect (running=true), tmux new, tmux has-session
        side = [_ok(stdout="cid\n"), _ok(stdout="true\n"), _ok(), _ok()]
        with mock.patch.object(docker_sandbox, "SUPPORTED", True), \
             mock.patch("subprocess.run", side_effect=side):
            sb.create()
        self.assertTrue(sb._created)

    def test_create_fails_if_docker_run_fails(self):
        sb = self._new()
        with mock.patch.object(docker_sandbox, "SUPPORTED", True), \
             mock.patch("subprocess.run") as run:
            run.side_effect = [
                _ok(returncode=1, stderr="image not found"),
                _ok(),  # rm -f
            ]
            with self.assertRaises(StateError):
                sb.create()
        self.assertFalse(sb._created)

    def test_create_fails_if_container_not_running(self):
        sb = self._new()
        side = [
            _ok(stdout="cid\n"),       # docker run
            _ok(stdout="false\n"),     # docker inspect
            _ok(),                     # rm -f cleanup
        ]
        with mock.patch.object(docker_sandbox, "SUPPORTED", True), \
             mock.patch("subprocess.run", side_effect=side):
            with self.assertRaises(StateError):
                sb.create()
        self.assertFalse(sb._created)

    def test_create_fails_if_tmux_new_session_fails(self):
        sb = self._new()
        side = [
            _ok(stdout="cid\n"),
            _ok(stdout="true\n"),
            _ok(returncode=1, stderr="tmux missing"),
            _ok(),  # rm -f cleanup
        ]
        with mock.patch.object(docker_sandbox, "SUPPORTED", True), \
             mock.patch("subprocess.run", side_effect=side):
            with self.assertRaises(StateError):
                sb.create()
        self.assertFalse(sb._created)

    def test_create_fails_if_tmux_has_session_fails(self):
        sb = self._new()
        side = [
            _ok(stdout="cid\n"),
            _ok(stdout="true\n"),
            _ok(),
            _ok(returncode=1, stderr="no such session"),
            _ok(),  # rm -f cleanup
        ]
        with mock.patch.object(docker_sandbox, "SUPPORTED", True), \
             mock.patch("subprocess.run", side_effect=side):
            with self.assertRaises(StateError):
                sb.create()
        self.assertFalse(sb._created)

    def test_create_raises_when_docker_unavailable(self):
        sb = self._new()
        with mock.patch.object(docker_sandbox, "SUPPORTED", False):
            with self.assertRaises(StateError):
                sb.create()


class CloseIdempotenceTests(unittest.TestCase):

    def test_close_on_never_created_is_noop(self):
        sb = docker_sandbox.Sandbox(
            agent_name="opus", run_id="r1",
            workspace=Path("/tmp"), repo_root=Path("/tmp"),
        )
        with mock.patch("subprocess.run") as run:
            sb.close()
            sb.close()  # second call must also be a no-op
        run.assert_not_called()

    def test_close_after_create_runs_rm_once(self):
        sb = docker_sandbox.Sandbox(
            agent_name="opus", run_id="r1",
            workspace=Path("/tmp"), repo_root=Path("/tmp"),
        )
        sb._created = True
        with mock.patch("subprocess.run", return_value=_ok()) as run:
            sb.close()
            sb.close()  # second call must not invoke docker again
        run.assert_called_once()
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[:3], ["docker", "rm", "-f"])

    def test_close_swallows_subprocess_errors(self):
        sb = docker_sandbox.Sandbox(
            agent_name="opus", run_id="r1",
            workspace=Path("/tmp"), repo_root=Path("/tmp"),
        )
        sb._created = True
        with mock.patch("subprocess.run",
                        side_effect=subprocess.SubprocessError("boom")):
            sb.close()  # must not raise


class ExecParsingTests(unittest.TestCase):

    def test_exec_parses_json_output(self):
        sb = docker_sandbox.Sandbox(
            agent_name="opus", run_id="r1",
            workspace=Path("/tmp"), repo_root=Path("/tmp"),
        )
        sb._created = True
        with mock.patch("subprocess.run",
                        return_value=_ok(stdout='{"hello":"world"}')):
            result = sb.exec_tb(["snapshot", "--json"], None)
        self.assertTrue(result.ok)
        self.assertEqual(result.json_data, {"hello": "world"})

    def test_exec_handles_non_json_output(self):
        sb = docker_sandbox.Sandbox(
            agent_name="opus", run_id="r1",
            workspace=Path("/tmp"), repo_root=Path("/tmp"),
        )
        sb._created = True
        with mock.patch("subprocess.run",
                        return_value=_ok(stdout="not json")):
            result = sb.exec_tb(["snapshot"], None)
        self.assertTrue(result.ok)
        self.assertIsNone(result.json_data)

    def test_exec_records_timeout(self):
        sb = docker_sandbox.Sandbox(
            agent_name="opus", run_id="r1",
            workspace=Path("/tmp"), repo_root=Path("/tmp"),
        )
        sb._created = True
        with mock.patch("subprocess.run",
                        side_effect=subprocess.TimeoutExpired(cmd=["docker"], timeout=5)):
            result = sb.exec_tb(["snapshot"], None, timeout=5)
        self.assertFalse(result.ok)
        self.assertEqual(result.exit_code, 124)
        self.assertIn("timed out", result.stderr)


if __name__ == "__main__":
    unittest.main()
