#!/usr/bin/env python3
"""Cross-repo version alignment check for tmux-browse + its submodules.

Catches the common mistake of bumping one side of the contract and
forgetting the other. Run via ``make preflight`` locally or from CI.

Checks performed (order matches how a bump typically drifts):

1. **Submodule populated.** ``extensions/agent/manifest.json`` exists.
   If not, prior steps can't compare anything — tell the operator to
   ``git submodule update --init``.
2. **Catalog ``pinned_ref`` matches the submodule's exact tag.** If
   ``.gitmodules`` points at a commit that isn't tagged as the catalog
   claims, installs on a fresh machine will fetch a different commit
   than the running one — the classic "version skew" bug.
3. **Submodule manifest's ``min_tmux_browse`` ≤ core's version.** The
   running core must satisfy the extension's declared minimum. A
   stricter check than the loader does (the loader validates at load
   time; preflight catches it at dev time).
4. **Submodule manifest version matches its git tag.** If the tag
   says ``v0.7.1-agent`` but the manifest says ``0.7.0``, the two
   documents disagree about what the tag means — cosmetic but worth
   flagging.

Exits 0 on all-clear, 1 on any mismatch. stderr carries each
failure as a one-line ``FAIL: <check>: <message>`` so CI logs are
grep-friendly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SUBMODULE = REPO / "extensions" / "agent"
MANIFEST = SUBMODULE / "manifest.json"


def _fail(check: str, msg: str) -> None:
    sys.stderr.write(f"FAIL: {check}: {msg}\n")


def _ok(check: str, detail: str = "") -> None:
    print(f"ok: {check}" + (f" ({detail})" if detail else ""))


def _version_tuple(s: str) -> tuple[int, ...]:
    return tuple(int(p) for p in s.split(".") if p.isdigit())


def _git(*args: str, cwd: Path = REPO) -> tuple[int, str, str]:
    r = subprocess.run(
        ["git", *args], cwd=cwd,
        capture_output=True, text=True, timeout=15.0,
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def check_submodule_populated() -> bool:
    if MANIFEST.is_file():
        _ok("submodule populated", str(SUBMODULE))
        return True
    _fail("submodule populated",
          f"{SUBMODULE}/manifest.json missing — "
          "run `git submodule update --init`")
    return False


def check_pinned_ref_matches_catalog() -> bool:
    # Import lazily — the catalog is Python code, not static data.
    sys.path.insert(0, str(REPO))
    try:
        from lib.extensions.catalog import KNOWN
    except ImportError as e:
        _fail("catalog import", str(e))
        return False
    spec = KNOWN.get("agent")
    if spec is None:
        _fail("catalog has 'agent'", "KNOWN missing the agent entry")
        return False
    pinned_ref = spec.get("pinned_ref")
    if not pinned_ref:
        _fail("catalog pinned_ref", "agent catalog entry has no pinned_ref")
        return False
    # What tag is the currently-checked-out submodule commit?
    rc, out, err = _git("describe", "--tags", "--exact-match", "HEAD",
                        cwd=SUBMODULE)
    if rc != 0:
        _fail("pinned_ref matches submodule",
              f"submodule HEAD isn't on a tag: {err or out}")
        return False
    if out != pinned_ref:
        _fail("pinned_ref matches submodule",
              f"catalog says {pinned_ref!r}, submodule is at {out!r}")
        return False
    _ok("pinned_ref matches submodule", out)
    return True


def check_core_satisfies_min() -> bool:
    try:
        manifest = json.loads(MANIFEST.read_text())
    except (OSError, ValueError) as e:
        _fail("manifest readable", str(e))
        return False
    min_core = manifest.get("min_tmux_browse", "0.0.0")
    sys.path.insert(0, str(REPO))
    try:
        from lib import __version__ as core_version
    except ImportError as e:
        _fail("core version import", str(e))
        return False
    if _version_tuple(core_version) < _version_tuple(min_core):
        _fail("core satisfies min_tmux_browse",
              f"core is {core_version}; agent requires >= {min_core}")
        return False
    _ok("core satisfies min_tmux_browse",
        f"core={core_version} >= required={min_core}")
    return True


def check_manifest_version_matches_tag() -> bool:
    try:
        manifest = json.loads(MANIFEST.read_text())
    except (OSError, ValueError):
        # Previous check already reported.
        return False
    rc, tag, _ = _git("describe", "--tags", "--exact-match", "HEAD",
                      cwd=SUBMODULE)
    if rc != 0:
        # Already reported by check_pinned_ref_matches_catalog.
        return False
    # Tag convention: ``v<version>-agent`` — e.g. ``v0.7.1-agent``.
    if not (tag.startswith("v") and tag.endswith("-agent")):
        _fail("tag format",
              f"submodule tag {tag!r} doesn't match v<version>-agent")
        return False
    tag_version = tag[1:-len("-agent")]
    mf_version = manifest.get("version")
    if tag_version != mf_version:
        _fail("manifest version matches tag",
              f"tag says {tag_version!r}, manifest says {mf_version!r}")
        return False
    _ok("manifest version matches tag", f"{mf_version} == {tag_version}")
    return True


CHECKS = [
    check_submodule_populated,
    check_pinned_ref_matches_catalog,
    check_core_satisfies_min,
    check_manifest_version_matches_tag,
]


def main() -> int:
    all_ok = True
    for check in CHECKS:
        try:
            if not check():
                all_ok = False
        except Exception as e:
            _fail(check.__name__, f"unexpected error: {e}")
            all_ok = False
    if not all_ok:
        sys.stderr.write("\npreflight: one or more checks failed\n")
        return 1
    print("\npreflight: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
