# Implementation status — 2026-11-03

This is a tested development foundation, not a completed alpha or stable release.
The approved complete plan remains the scope contract. Unfinished items are not
waived or converted into unsupported upstream limitations.

| Plan area | Current evidence | Remaining gate |
|---|---|---|
| Step 0 | Approved plan and project context persisted before code work | Complete |
| Step 1 | Public repositories; unchanged pinned upstream passes local Mac tests and the three-platform Qt 5/6 CI matrix; locked Python dependencies; per-process native settings isolation | Reproducible distributed application packages |
| Step 2 | 124 main-window actions; 2,159 discovered UI/API entries; drift checker | Semantic review, full mappings, dialog/tool controls, per-capability acceptance |
| Step 3 | Optional activation; private authenticated Unix sockets/Windows named pipes; bounded framing; GUI-thread dispatch; native revisions/events; visible and API revocation; stale-process discovery cleanup | Full observation coverage |
| Step 4 | New/open/save, immutable checkpoints/snapshots, explicit recovery, snapshot-only FPS override; source preservation and corrupt recovery tests | Old-format save and the full recovery/file-format matrix |
| Step 5 | Native strokes; both history modes preserve interleaved human/agent edits; bounded atomic batches/rollback; layer properties/order/duplication; timeline exposure/reverse; camera keys/path/easing; opacity; isolated project FPS | Full vector/bitmap editing, multi-key repositioning and the remaining native surface |
| Step 6 | Automated Mac subset of reference workflow and native PNG export | Entire alpha workflow, human-edit acceptance and native video/audio fixtures |
| Step 7 | Independent issue fixes submitted upstream with attribution and tests; links in NATIVE_FIXES.md | Complete alpha before the separate automation-bridge proposal/design engagement |
| Step 8 | Remaining surface explicitly inventoried | Remaining timeline, bitmap/tools, preferences/dialogs and full format/codec surface |
| Step 9 | Saved/snapshot native CLI jobs, repeated exports and native aliases, ranges, dimensions, camera arguments; decode/dimension/frame-count/PNG-alpha validation | Full format/codec/audio/content/timing and GUI import/export coverage; native warning localization |
| Step 10 | Scoped persistent jobs; cancellation/deadlines; isolated profiles; owned process groups; interrupted-owner detection; kernel owner leases; configurable shared worker slots; durable fsynced publication journals and rollback with retained conflict backups | Full crash-point/OS matrix and Windows runtime recovery qualification |
| Step 11 | Official SDK stdio; tools/resources/images/prompts and effect annotations; config merge preservation; installed-wheel native stdio test; real signed-in Codex subset workflow | Complete Codex workflow, Cursor and Claude Desktop acceptance; subscriptions/progress negotiation and complete resources |
| Step 12 | GPL notices, source pins, wheel/sdist and relocatable Mac package; cross-platform deployment/nightly/signing/gate implementations | Clean-machine binary packaging, source/provenance bundle, stable signing/notarization, PyPI ownership/publication, upgrades/rollback/uninstall |

Native source integration is on `splitintech/pencil` branch
`stanlee/qualified-integration`, pinned by this repository's build manifest. Normal
fork `master` remains upstream code. The integrated native suite passes **1,175 assertions in
79 cases** locally through both qmake and CMake. **72 Python/native integration, CLI and release-boundary tests** pass locally (one Windows-only test skipped on Mac); the
latest CI results must be read separately from this local evidence.

The native shared registry currently advertises 67 implemented development
operations, including vector geometry/styles/fill, palettes, sound assets, playback,
image import, safe close and viewport pan/flips.
Layer creation, strokes, FPS and supported content edits now use native document
transactions. See [editing contracts and history behavior](EDITING.md).
Fifty-one UI controls/actions have reviewed API/test mappings; the remaining
inventory is semantically incomplete and is not a declaration of full Pencil2D
coverage. Windows discovery ACL checks and deadline-bounded named-pipe transport are
implemented and passed the complete native matrix, including profiles,
checkpoints/recovery, revocation and independent snapshot assets.
Invalid ACLs fail closed. Source builds alone do not establish runtime acceptance.

Snapshots load bitmap backing files into the copy, reject missing/corrupt data,
and own independent sound bytes while retaining native timing.

`document.checkpoint` preserves the active revision, path, dirty state and undo
history; it emits an observation event. `document.recover` requires explicit
discard for dirty content, loads before replacing anything, creates a new document
handle and a fresh undo history, and marks recovered content dirty. Its optional
`source_path` chooses the eventual save path; recovery does not write that source.

Output publication stages all validated files, locks destination directories,
and rolls back earlier files if a later publication fails. External edits are
preserved; original backups are retained and reported when rollback would overwrite
them. Readers can see intermediate files. Real-process crash tests recover a death between replacement and journal update,
refuse live recovery, preserve external edits and recover interrupted job outputs.
Persistent lease files are intentional. Full crash-point/platform qualification
remains unfinished. See [recovery behavior](RECOVERY.md).

MCP tools share the command service with CLI. Native frame previews use the
application's Object/camera composition. Export validation currently establishes
decodability, explicit dimensions/ranges and PNG alpha support, not comprehensive
content/audio equivalence. Native CLI can return success after an export failure;
Stanlee checks outputs independently. Unsupported transparency fails before work.

Private discovery tokens and company documents are excluded from source and
artifacts. No alpha/stable tag, PyPI publication, signed binary or upstream
acceptance is claimed.

Source `ecf70ac` passed the complete [Python/packaging matrix](https://github.com/splitintech/stanlee/actions/runs/41458637568)
and [native Qt/platform matrix](https://github.com/splitintech/stanlee/actions/runs/41458637297).
The subsequent snapshot asset-integrity pin `da97b1f` also passed all six
[Python/packaging](https://github.com/splitintech/stanlee/actions/runs/41460361462)
and all six [native configurations](https://github.com/splitintech/stanlee/actions/runs/41460361576).
Those results qualify the previous foundation. The new editor transaction/native
pin passed a fresh platform matrix as recorded below; local results above cover
the same runtime/native source.
An installed-wheel test independently completed SDK stdio → native pressure stroke
and preview → isolated FPS snapshot → decoded 320×240 transparent PNG export.

Codex CLI **0.164.0-alpha.11.1**, authenticated through the existing ChatGPT login,
completed 15 MCP calls: discovery, operation-resource lookup, pressure stroke,
image preview, save/new/reopen, validated native export and deliberate stale
revision rejection with preserved state. [The normalized evidence](evidence/2026-11-02-codex-cli.json)
records the exact source/native revisions, wheel checksum and output metadata.
This used invocation-only configuration and tool permissions in a disposable
workspace. It did not alter persistent client settings. Cursor 3.27.6 is installed
but untested; Claude Desktop is absent. This subset does not complete Step 6.

The native pin now includes issues #1332, #1942 and #1964. Reproducible patch
replay, upstream request links and qualification limits are recorded in
[NATIVE_FIXES.md](NATIVE_FIXES.md) and [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).

The 2026-11-03 editor continuation adds strict recursive native schema validation
and validates batch eligibility before preparing history. A failed context step
rolls back content without removing previous redo entries. A newer unrecorded
human edit causes `history_conflict`, preserving both content and history index.
Tests exercise both native history modes, save points, layer IDs, active colors
and stored FPS defaults. Native camera copies preserve custom paths (including
an explicit control point at the origin). Snapshot metadata no longer crops live
bitmaps; preview and save normalize independent/native bitmap bounds consistently.
Blank saved keys have explicit transparent backing data. A rotated/scaled camera
preview now matches exactly after native save/reopen. Legacy documents with missing
bitmap assets remain a qualification limit; missing assets fail snapshot preparation.

Codex CLI 0.164.0-alpha.11.1 repeated the current editor workflow with **21
successful MCP calls** and one expected stale-revision error. A five-step atomic
batch changed FPS, drew a pressure stroke, duplicated a key and animated the
camera. Undo and redo restored timing/keys without changing document identity.
The client previewed frame 4, saved/new/reopened the project and exported a native
320×240 RGBA PNG. Independent decoding verified nonempty content and transparency;
before/after inspection proved stale-revision rejection preserved state.
[Normalized evidence](evidence/2026-11-03-codex-editor.json) pins the source, native
revision and installed wheel. This is still a subset of the full alpha workflow.
The installed-wheel SDK stdio test separately passed the same batch/history/
preview path and snapshot-only FPS export.

Editor source `3e69f4b` passed all six [Python/packaging jobs](https://github.com/splitintech/stanlee/actions/runs/41634341848).
All six [native Qt/platform configurations](https://github.com/splitintech/stanlee/actions/runs/41634341896)
also passed, including real MCP integration on each Qt 6 platform. Subsequent
documentation/evidence changes do not alter this qualified runtime/native code.

The current native integration also builds successfully with CMake
`STANLEE_AUTOMATION=OFF` on macOS arm64. This compile check preserves the optional
bridge boundary; it is separate from normal-application runtime qualification.


The content/audio checkpoint used native `0506f14b0c96`. Local qmake and
CMake tests each pass 79 native cases / 1,175 assertions. The optional bridge-OFF
CMake application also builds. Official Qt 6.12 supplies the headless FFmpeg backend
used by sound fixtures; the local Homebrew native Mac media backend did not resolve
headless duration, so no fake duration or weakened audio assertion was introduced.

A locally relocated Mac ARM package passed the installed SDK fixture: pressure
batch/undo/redo, vector geometry, independent decoded sound, camera preview,
save/new/reopen, four distinct PNG frames and a four-frame H.264 movie with one
audio stream, 24 FPS and duration 0.166667 seconds. Encoder/validator libraries are
isolated from Qt media libraries to avoid equal-SONAME ABI conflicts. This local
result is separate from the pending CI package/platform and real-client matrix.
The final committed package bytes and CI results must be recorded independently.
See [packaging and signing](PACKAGING.md). Nightly scheduling remains inactive
until the workflow is merged into the default branch; no such merge is claimed.


The first expanded CI pass found a real Qt 6.5 timing difference: some decoders
emit duration synchronously during player initialization. SoundManager now connects
before initialization, complementing the player-level subscription fix. The tests
retain the exact 1,000 ms / 12-frame assertion. The controller recovery/package
suite passed every Mac/Linux/Windows Python 3.11/3.12 job at `fcb6863`:
[CI evidence](https://github.com/splitintech/stanlee/actions/runs/41655448423).
Native and application package qualification must be rerun at the corrected pin.


The bitmap extension adds bounded independent pixel inspection, explicit native
region/affine edits and reflection, document-internal region copy/cut, and native
paper processing. Exact-pixel/opacity/save/reopen/undo and failure rollback fixtures
pass locally. The native paper threshold and RGB controls now have reviewed API
mappings; clipboard and selection UI workflows remain explicitly partial. Latest
source pin and platform qualification are recorded separately from this local proof.

The new bitmap source pin is `02c10d7d0953b4f1fbb12e9fcd46fa5fdb3a2622`.
