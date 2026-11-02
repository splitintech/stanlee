#!/usr/bin/env python3
"""Verify the bundled native patch and, optionally, its pinned Git integration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def verify(root, native=None):
    build = json.loads((root / "build-manifest.json").read_text())
    manifest = json.loads((root / "patches/pencil2d/manifest.json").read_text())
    patch = root / "patches/pencil2d/fixes.patch"
    if manifest["patch"] != "patches/pencil2d/fixes.patch":
        raise ValueError("Unexpected native patch path")
    if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Native patch checksum mismatch")
    if manifest["upstream_revision"] != build["upstream_revision"]:
        raise ValueError("Native patch baseline differs from the build baseline")
    if build["native_fixes"] != {
        "manifest": "patches/pencil2d/manifest.json", "revision": manifest["fixes_revision"]
    }:
        raise ValueError("Build manifest does not identify the bundled fixes")
    if {issue["number"] for issue in manifest["issues"]} != {1332, 1942, 1964}:
        raise ValueError("Incomplete native issue manifest")
    if native is None:
        return

    def git(*arguments, env=None):
        return subprocess.check_output(
            ["git", "-C", str(native), *arguments], text=True, env=env, timeout=30
        ).strip()

    if git("rev-parse", "HEAD") != build["fork_revision"]:
        raise ValueError("Native checkout differs from the immutable build pin")
    git("merge-base", "--is-ancestor", manifest["fixes_revision"], "HEAD")
    git("merge-base", "--is-ancestor", build["bridge_base_revision"], "HEAD")

    # Replay against the upstream tree using a temporary index. The checkout's
    # actual index and working files are untouched.
    with tempfile.TemporaryDirectory(prefix="stanlee-patch-") as folder:
        environment = dict(os.environ, GIT_INDEX_FILE=str(Path(folder) / "index"))
        git("read-tree", manifest["upstream_revision"], env=environment)
        git("apply", "--cached", "--whitespace=error", str(patch), env=environment)
        if git("write-tree", env=environment) != manifest["fixed_tree"]:
            raise ValueError("Replayed patch differs from the tested fixes tree")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, help="Full-history pinned native checkout")
    args = parser.parse_args()
    try:
        verify(Path(__file__).resolve().parents[1], args.native)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Native fix verification failed: {error}\n")
    print("Native fixes: checksum, manifest and requested Git integration verified")


if __name__ == "__main__":
    main()
