# Implementation status — 2026-11-03

Stanlee is an experimental development build. The complete approved plan remains
the scope contract; full Pencil2D coverage, alpha acceptance and stable release
qualification remain unfinished.

The native registry contains **88 operations**. Implemented workflows include
pressure strokes, native atomic history/rollback, layer editing, explicit timeline
keys/exposure/reverse, animated cameras, vector geometry/styles/fill, palettes,
independent audio/image import, playback/view controls, bitmap region inspection,
transform/copy/cut and scanned-paper processing, polylines, vector point editing,
sequence/animated/cross-project imports, 25 view controls, 10 panels/toolbars,
35 typed preference fields, native shortcuts, captures and application information.
See [editing contracts](EDITING.md).
The upstream inventory contains 2,159 entries and 124 main-window actions. It has
81 mapped rows, of which 60 have explicit semantic review; 65 rows are marked
implemented, 16 partial and 2,078 pending. Registry coverage back-links now match
all forward mappings. Regeneration preserves reviews/rationale and invalidates
changed fingerprints. Semantic review remains incomplete; raw inventory counts
are not a product-completion percentage.

## Current local source

`build-manifest.json` pins native `f862a26167d207145972864b91d704758ce104c6`
on the review integration branch. Local verification passes **238 Python/native
integration, CLI, recovery and packaging tests**, with one Windows-only test skipped
on Mac, plus **83 native cases / 1,210 assertions** through qmake and CMake.
Both bridge-enabled and bridge-disabled CMake applications build on Mac.

The audit-gap implementation synchronizes first job-manager construction,
preserves existing POSIX output access modes, validates typed native payloads and
PNG image metadata, reconciles unobserved GUI content changes through independent
snapshots, and streams native archives through atomic `QSaveFile` publication.
Missing/restored assets also invalidate revisions, and capability/event probes
do not snapshot or mark dirty a document opened outside the workspace grant.
Native process death before archive commit preserves the original project.
Media validation enforces resolved format/dimensions/range/video timing and
expected audio-stream presence. Complete image/audio content equivalence remains
a fixture acceptance gate. Export/import jobs retain requests, progress and logs;
queued jobs can time out, authorized peer CLI instances can request owner-handled
cancellation, and imports reject document revisions changed during decoding.
The current source requires fresh platform/package/client qualification; historical
package runs below qualify their recorded revisions only.
The native CI fixture explicitly deploys its installed encoder/probe beside the
source app; production Mac/Windows encoder lookup remains restricted to the
application's deployed tools.

Native export handling propagates image/movie failures into CLI exit status,
rejects invalid numeric/range/format/camera requests, and rejects ambiguous explicit
camera names. CLI and GUI movie selections carry native layer IDs instead of
resolving an already selected camera by label again. Movie buffering uses actual
output pixels. Regression fixtures assert failure exits without output and source
preservation, plus selected-camera MP4/PNG composition against a visibly different
camera. Automated GUI interaction with repeated camera labels remains an open check.
A staged encoder symlink is replaced as a directory entry, preserving its external
target; a packaging regression fixture checks this behavior.

The subsequent relocated-package check exposed a native audio shutdown crash.
`SoundPlayer` previously destroyed its borrowed input buffer before QObject deleted
its decoder child. The decoder is now explicitly stopped/destroyed while the buffer
is alive, with teardown metadata forwarding disconnected. A focused native lifetime
test failed with SIGBUS before the fix, then passed all eight assertions; the same
saved audio document completed 30 consecutive clean CLI exports after the fix.
[Normalized evidence](evidence/2026-11-03-audio-shutdown.json) records the source and
verification boundaries. A locally relocated archive at controller `256d8c9` passed installed-wheel SDK
acceptance with all five movie formats after this fix. Its exact archive SHA-256 is
`8904c19ad13aabda50c1737a5a337c29ac31f47cdef9132f494aced0c4125699`.
It precedes the subsequent publication recovery change; final current-byte/platform
acceptance is a separate gate.
The application-version probe allows a bounded 30 seconds for first-load work;
a cold extracted package previously exceeded its ten-second probe deadline.
The lifetime regression uses physical child destruction because older Qt versions
disconnect signal observers during shutdown; its buffer-alive assertion is retained.

The native bridge uses opt-in activation, private authenticated local IPC,
strict schemas, GUI-thread dispatch, document/revision checks, workspace grants,
revocation and observation events. Document checkpoints/snapshots own independent
assets and preserve live history. Recovery loads before replacing the active
document and never writes the recovery source implicitly. Atomic edits reject
external effects and roll back failed steps without losing previous redo entries.
Full observation, file-format and human-edit qualification remains open.

Exports use saved documents or isolated snapshots, native rendering, bounded
workers and validation before publication. Durable journals and kernel leases
recover interrupted publications and preserve externally changed files and backup
conflicts. Real-process crash fixtures cover replacement-before-journal-update,
live-owner refusal and interrupted jobs. The 42-case multi-directory process-death matrix covers durable preparation,
replacement, commit/cleanup, interrupted recovery and repeated committed-conflict
recovery. Committed decisions remain irreversible; each output directory is synced
before intent. Full OS/power-loss/native/client crash qualification remains open. See [recovery](RECOVERY.md).

## Completed cross-platform package checkpoint

[Package run 41668969493](https://github.com/splitintech/stanlee/actions/runs/41668969493)
passed Windows x64, Linux x64, Mac ARM and Mac Intel packaging/installed-wheel SDK
acceptance, universal merging, final universal acceptance on both Mac CPUs, and
artifact provenance. The workflow checked out synthetic PR merge `43cc7c5aadaf85b6a168341949dd83ec580b9f72`;
its Git tree equals review head `9521442bc37aa5773ea0e10c1955d1a694f01386`.
Native pin: `5b25d9495c01580dc6ef8ce8a0e56636a60563b7`.
[Normalized proof](evidence/2026-11-03-cross-platform-packages.json) retains both
source identities, final archive hashes, six acceptance results and artifact IDs.
These historical packages precede the export/audio/recovery corrections and are
not current qualified builds. They contain the subsequently identified audio
shutdown and repeated committed-conflict recovery faults.

That checkpoint also passed all six [native Qt 5/6 platform configurations](https://github.com/splitintech/stanlee/actions/runs/41668969687)
and the complete [Python 3.11/3.12 platform matrix](https://github.com/splitintech/stanlee/actions/runs/41668970222).
One queued Python job was rerun after cancellation before any test steps.

The installed SDK fixture covers atomic pressure edits/history, bitmap region
history, vector geometry, independent sound duration after source deletion and
save/reopen, four distinct PNG frames, MP4/AVI/WebM audio and GIF/APNG frame counts.
GIF timing has centisecond quantization; AVI can retain audio padding. This is SDK
acceptance, separate from full real-client, GUI and content/audio equivalence.
The Mac encoder builds five pinned, hash-verified source archives with static
codecs and retained source/notices. Every universal runtime Mach-O contains both
architectures; CLI libraries remain isolated from Qt media libraries.

## Remaining plan gates

- Complete semantic inventory, remaining tools/editor controls, selections and
  clipboard/vector transfers, timeline actions, preferences and dialogs.
- Complete native format/codec/content/audio/timing fixtures, old-format and
  recovery acceptance, interleaved human editing and the entire alpha workflow.
- Full crash-point/OS and performance qualification; clean-machine installation,
  upgrades, rollback and uninstall.
- Complete Codex, Cursor and Claude Desktop acceptance on each target platform.
  [Codex evidence](evidence/2026-11-03-codex-editor.json) is an earlier 41-operation
  subset, not current full-client qualification. Cursor is installed but untested;
  Claude Desktop is absent from this machine.
- Dependency notice/corresponding-source audit, locked Windows/Linux encoders,
  reproducibility qualification, actual trusted Mac/Windows signing, notarization,
  final signed-byte acceptance and PyPI ownership/publication.
- Default-branch integration and activation of nightly publication. Review-branch
  artifacts exist; no nightly release, alpha/stable tag or PyPI publication is claimed.

Signing, immutable nightly publishing and stable-gate tools are implemented and
fail when required credentials/evidence are missing. No valid Mac signing identity
was available locally. Stable qualification currently refuses incomplete coverage,
client/platform, signing and reference evidence. See [packaging](PACKAGING.md) and
[release policy](RELEASE_POLICY.md). Independent upstream fixes remain separate
from any future automation-bridge proposal; see [native fixes](NATIVE_FIXES.md).
