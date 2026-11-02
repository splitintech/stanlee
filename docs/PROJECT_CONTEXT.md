# Stanlee project context

Updated: 2026-11-02

## Product and architecture

Stanlee provides Pencil2D control to external AI clients through the official
Python MCP SDK and a shared CLI. The complete scope includes editing, drawing,
animation, layers, timeline, cameras, dimensions, frame ranges, import/export,
observation, and application settings. The authoritative scope and acceptance
gates are in [BUILD_PLAN.md](BUILD_PLAN.md).

The Python server lives in `splitintech/stanlee`. A separately built optional
C++/Qt bridge lives in `splitintech/pencil`; it contains no MCP or AI runtime.
Normal upstream-style builds leave the bridge disabled. Enabled builds use a
separate Pencil2D–Stanlee identity and settings profile.

Use Python 3.11+, official MCP SDK 2.3.0, and Qt 6 for distributed development
builds. Native contributions preserve Qt 5/6 and qmake/CMake compatibility.
New code is GPL-2.0-only; preserve upstream copyright and dependency notices.

All native mutations run on the GUI thread with authenticated local IPC,
workspace grants, session/document identities, and expected revisions. The
bridge rejects stale or busy state. Human editing, native undo, snapshots,
export isolation, recovery, and client/platform qualification are separate
acceptance gates. See [STATUS.md](STATUS.md) for unfinished work.

## Source revisions and included fixes

`build-manifest.json` is the authoritative immutable native pin. It records the
upstream baseline, original bridge revision, integrated bridge/fixes revision,
and the native fix manifest. The baseline remains
`408563a37068daf7f1b4c6a9291daef039be8cb5`.

The pinned native application includes:

| Upstream issue | Behavior |
| --- | --- |
| [#1332](https://github.com/pencil2d/pencil/issues/1332) | Commit a freehand stroke before changing frames and resume from the last pointer position, preserving frame ownership and mouse/tablet input. |
| [#1942](https://github.com/pencil2d/pencil/issues/1942) | Reject hidden-layer editing before changing content, selections, clipboard, or history; keep visibility policy in shared editor/interaction controllers. |
| [#1964](https://github.com/pencil2d/pencil/issues/1964) | Publish SHA-256 sidecars for final native packages and configure trusted-ref CI provenance with repository/workflow/ref/commit verification instructions. |

Reviewable source is bundled in [patches/pencil2d](../patches/pencil2d/README.md).
The manifest records issue branches, commit IDs, upstream request links, the
patch checksum, and the expected reconstructed Git tree. CI checks the patch
and verifies that the pinned application includes both the bridge and fixes.

The hidden-layer work preserves Jouvens-Corantin's original contribution from
[PR #1989](https://github.com/pencil2d/pencil/pull/1989). Follow-up work adds missing
controller guards and regressions while following the review request to keep
the Layer data model available for undo, loading, and explicit scripting.

## Contribution process

For these correctness/download fixes, upstream review and merge requests are
authorized now. The larger optional automation-bridge proposal remains a
separate contribution with its own working-alpha/design gates.

The inspected upstream revision has no code `CONTRIBUTING.md` or PR template;
no public organization-wide `.github` repository was found. Follow the
[published contribution page](https://www.pencil2d.org/contribute/),
[developer documentation](https://dev.pencil2d.org/), existing C++/Qt conventions,
and specific maintainer feedback on related pull requests. Submit focused
changes with reproductions, regression tests, qualification limits, and original
attribution. The documentation-only contribution guide is not a separate code
submission requirement. Maintainers recommend Qt 5.15 / Qt 6.5.3 for upstream
development in [PR #1999](https://github.com/pencil2d/pencil/pull/1999#issuecomment-4251786886);
the inherited native CI matrix preserves those versions.

Request links and the current validation record are in
[NATIVE_FIXES.md](NATIVE_FIXES.md). A request is not maintainer acceptance;
upstream issue closure follows upstream review and merge.

## Release and evidence boundaries

The standalone fixes passed 66 native cases / 923 assertions locally and six
hosted native build/test/package configurations: Linux Qt 5/6, Windows Qt 5
x86/x64 and Qt 6 x64, and macOS Qt 6 universal. The legacy macOS Intel/Qt 5
workflow timed out in Homebrew dependency setup before application compilation.
These results do not qualify the entire Stanlee bridge on those platforms.
The newly integrated local macOS build separately passes 67 native cases /
942 assertions and 28 Stanlee Python/CLI/MCP/native tests (one Windows-only skip).

A real hosted package and its sidecar verified successfully; controlled byte
tampering was rejected. Checksums alone do not authenticate a publisher.
Trusted-ref build attestation publication still needs a merge/release run;
PR builds intentionally skip it. Official download-site publication and stable
platform signing remain release steps.

Stanlee remains a development foundation. Full editor coverage, complete alpha,
all client/platform acceptance, recovery qualification, signed applications,
and stable/PyPI publication must meet the existing plan's gates.
