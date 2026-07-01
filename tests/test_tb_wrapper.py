import subprocess
import sys
from pathlib import Path


def test_root_tb_wrapper_exposes_cli_help():
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, str(root / "tb.py"), "a", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "usage: tb a" in result.stdout
    assert "--cwd CWD" in result.stdout
    assert "--cmd CMD" in result.stdout
