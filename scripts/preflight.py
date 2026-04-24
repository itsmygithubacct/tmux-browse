#!/usr/bin/env python3
"""Cross-repo version alignment check for tmux-browse + every
catalog-listed submodule.

Catches the common mistake of bumping one side of the contract and
forgetting the other. Run via ``make preflight`` locally or from CI.

Checks, per submodule, in the order a bump typically drifts:

1. **Submodule populated.** ``extensions/<name>/manifest.json`` exists.
   If not, prior steps can't compare anything — tell the operator to
   ``git submodule update --init``.
2. **Catalog ``pinned_ref`` matches the submodule's exact tag.** If
   ``.gitmodules`` points at a commit that isn't the tagged one the
   catalog claims, installs on a fresh machine will fetch a different
   commit than the one the repo tests against.
3. **Submodule manifest's ``min_tmux_browse`` ≤ core's version.** The
   running core must satisfy the extension's declared minimum.
4. **Submodule manifest version matches its git tag** (tag format
   ``v<version>-<name>``).

Exits 0 on all-clear, 1 on any mismatch. Stderr carries each failure
as a one-line ``FAIL: <submodule>/<check>: <message>`` so CI logs
are grep-friendly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def _fail(check: str, msg: str) -> None:
    sys.stderr.write(f"FAIL: {check}: {msg}\n")


def _ok(check: str, detail: str = "") -> None:
    print(f"ok: {check}" + (f" ({detail})" if detail else ""))


def _version_tuple(s: str) -> tuple[int, ...]:
    return tuple(int(p) for p in s.split(".") if p.isdigit())


def _git(*args: str, cwd: Path) -> tuple[int, str, str]:
    r = subprocess.run(
        ["git", *args], cwd=cwd,
        capture_output=True, text=True, timeout=15.0,
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _core_version() -> str:
    sys.path.insert(0, str(REPO))
    from lib import __version__
    return __version__


def check_one(name: str, spec: dict) -> bool:
    """Run the four checks for a single catalog entry. Returns True
    only when every check on this entry passed.
    """
    submodule_path = REPO / spec["submodule_path"]
    manifest_path = submodule_path / "manifest.json"
    pinned_ref = spec.get("pinned_ref")
    all_ok = True

    # 1. populated
    if manifest_path.is_file():
        _ok(f"{name}/populated", str(submodule_path))
    else:
        _fail(f"{name}/populated",
              f"{submodule_path}/manifest.json missing — "
              "run `git submodule update --init`")
        return False  # later checks need the manifest

    # 2. pinned_ref matches submodule
    rc, tag, err = _git("describe", "--tags", "--exact-match", "HEAD",
                        cwd=submodule_path)
    if rc != 0:
        _fail(f"{name}/pinned_ref",
              f"submodule HEAD isn't on a tag: {err or tag}")
        all_ok = False
        tag = None
    elif pinned_ref and tag != pinned_ref:
        _fail(f"{name}/pinned_ref",
              f"catalog says {pinned_ref!r}, submodule is at {tag!r}")
        all_ok = False
    else:
        _ok(f"{name}/pinned_ref", tag)

    # 3. core satisfies min_tmux_browse
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as e:
        _fail(f"{name}/manifest readable", str(e))
        return False
    min_core = manifest.get("min_tmux_browse", "0.0.0")
    core_version = _core_version()
    if _version_tuple(core_version) < _version_tuple(min_core):
        _fail(f"{name}/min_tmux_browse",
              f"core is {core_version}; {name} requires >= {min_core}")
        all_ok = False
    else:
        _ok(f"{name}/min_tmux_browse",
            f"core={core_version} >= required={min_core}")

    # 4. manifest version matches tag
    if tag:
        suffix = f"-{name}"
        if tag.startswith("v") and tag.endswith(suffix):
            tag_version = tag[1:-len(suffix)]
            mf_version = manifest.get("version")
            if tag_version != mf_version:
                _fail(f"{name}/version-tag",
                      f"tag says {tag_version!r}, manifest says {mf_version!r}")
                all_ok = False
            else:
                _ok(f"{name}/version-tag",
                    f"{mf_version} == {tag_version}")
        else:
            _fail(f"{name}/tag format",
                  f"{tag!r} doesn't match v<version>{suffix}")
            all_ok = False

    return all_ok


def main() -> int:
    sys.path.insert(0, str(REPO))
    try:
        from lib.extensions.catalog import KNOWN
    except ImportError as e:
        _fail("catalog import", str(e))
        return 1

    if not KNOWN:
        print("preflight: catalog is empty; nothing to check")
        return 0

    all_ok = True
    for name in sorted(KNOWN):
        try:
            if not check_one(name, KNOWN[name]):
                all_ok = False
        except Exception as e:
            _fail(name, f"unexpected error: {e}")
            all_ok = False

    if not all_ok:
        sys.stderr.write("\npreflight: one or more checks failed\n")
        return 1
    print("\npreflight: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
