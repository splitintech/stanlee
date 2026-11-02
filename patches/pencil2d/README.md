# Pencil2D correctness and download-verification fixes

`fixes.patch` contains the complete native changes for upstream issues
[#1332](https://github.com/pencil2d/pencil/issues/1332),
[#1942](https://github.com/pencil2d/pencil/issues/1942), and
[#1964](https://github.com/pencil2d/pencil/issues/1964). It applies to the exact
upstream revision in `manifest.json` and reconstructs the tested fixes tree.

The normal Stanlee build already contains these changes through the immutable
native pin in `build-manifest.json`. Do not apply this patch a second time to
that build. It is provided for review, source distribution, and reproducing
the standalone upstream changes without the optional automation bridge.

```sh
python scripts/verify_native_fixes.py
python scripts/verify_native_fixes.py --native /path/to/pinned/pencil
```

The second command requires native Git history, checks both the bridge and fix
ancestry, and replays the patch in a temporary index to verify its resulting
tree. It does not change the native checkout's index or working files.

For an independent checkout at the recorded upstream revision:

```sh
git apply --check /path/to/stanlee/patches/pencil2d/fixes.patch
git apply /path/to/stanlee/patches/pencil2d/fixes.patch
```

The hidden-layer work retains Jouvens-Corantin's contribution from upstream
[PR #1989](https://github.com/pencil2d/pencil/pull/1989) in the native Git history.
The manifest records the original revision and contributor. Follow-up changes
add controller-level coverage and regression tests while keeping the Layer
data model available to undo, loading and explicit scripting.

The patch retains Pencil2D copyright/license notices. New code is GPL-2.0-only;
see this repository's `LICENSE` and `NOTICE`. Upstream requests and qualification
limits are tracked in [project context](../../docs/PROJECT_CONTEXT.md).
