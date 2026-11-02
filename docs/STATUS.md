# Implementation status — 2026-11-02

This is a tested development foundation, not a completed alpha or stable release.
The approved complete plan remains the scope contract. Unfinished items are not
waived or converted into unsupported upstream limitations.

| Plan area | Current evidence | Remaining gate |
|---|---|---|
| Step 0 | Approved plan and project context persisted before code work | Complete |
| Step 1 | Public repositories; unchanged pinned upstream passes local Mac tests and the three-platform Qt 5/6 CI matrix; locked Python dependencies; per-process native settings isolation | Reproducible distributed application packages |
| Step 2 | 124 main-window actions; 2,159 discovered UI/API entries; drift checker | Semantic review, full mappings, dialog/tool controls, per-capability acceptance |
| Step 3 | Optional activation; private authenticated Unix sockets/Windows named pipes; bounded framing; GUI-thread dispatch; native revisions/events; visible and API revocation; stale-process discovery cleanup | Final-revision platform qualification; full observation coverage |
| Step 4 | New/open/save, immutable checkpoints/snapshots, explicit recovery, snapshot-only FPS override; source preservation and corrupt recovery tests | Old-format save, safe close and full recovery and file-format matrix |
| Step 5 | Native pressure/modifier stroke pipeline, dynamic tool properties and history undo/redo; layer creation/select; keyframes; FPS; tool/color/view selection | Full vector semantics, all layer/timeline edits and undo, bounded atomic batches/rollback |
| Step 6 | Automated Mac subset of reference workflow and native PNG export | Entire alpha workflow, human-edit acceptance and native video/audio fixtures |
| Step 7 | Independent issue fixes submitted upstream with attribution and tests; links in NATIVE_FIXES.md | Complete alpha before the separate automation-bridge proposal/design engagement |
| Step 8 | Remaining surface explicitly inventoried | Advanced timeline, vectors, cameras, audio, palettes, preferences and other editor capabilities |
| Step 9 | Saved/snapshot native CLI jobs, repeated exports and native aliases, ranges, dimensions, camera arguments; decode/dimension/frame-count/PNG-alpha validation | Full format/codec/audio/content/timing and GUI import/export coverage; native warning localization |
| Step 10 | Scoped persistent jobs; cancellation/deadlines; isolated profiles; owned process groups; interrupted-owner detection; one worker per service; locked output staging and sequence failure rollback with retained conflict backups | Crash supervision, configurable/global worker concurrency, PID-reuse proof, crash-time publication recovery and Windows recovery qualification |
| Step 11 | Official SDK stdio; tools/resources/images/prompts and effect annotations; config merge preservation; installed-wheel native stdio test; real signed-in Codex subset workflow | Complete Codex workflow, Cursor and Claude Desktop acceptance; subscriptions/progress negotiation and complete resources |
| Step 12 | GPL notices, build manifest, Python wheel/sdist build and CI definitions | Clean-machine binary packaging, source/provenance bundle, stable signing/notarization, PyPI ownership/publication, upgrades/rollback/uninstall |

Native source integration is on `splitintech/pencil` branch
`stanlee/qualified-integration`, pinned by this repository's build manifest. Normal
fork `master` remains upstream code. The integrated native suite passes **990 assertions in
69 cases** locally through both qmake and CMake. **40 Python/native integration and CLI tests** pass locally (one Windows-only test skipped on Mac); the
latest CI results must be read separately from this local evidence.

The native shared registry currently advertises 26 implemented development
operations; it deliberately excludes pending operations. Contracts document that
layer creation and FPS edits lack undo. The coverage register is mechanically
complete only for its stated scan patterns, semantically incomplete, and is not
a declaration of full Pencil2D coverage. Windows discovery ACL checks and deadline-bounded named-pipe transport are
implemented and passed the earlier native matrix. The prior complete matrix covers profiles, checkpoints/recovery and revocation.
The final asset-integrity change requires its own matrix result.
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
them. Readers can see intermediate files. Process death can leave staging/backup
files and `.stanlee-publication.lock`; automatic crash recovery is unfinished.

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
The subsequent snapshot asset-integrity pin `da97b1f` is tracked separately in
[Python/packaging](https://github.com/splitintech/stanlee/actions/runs/41460361462)
and [native qualification](https://github.com/splitintech/stanlee/actions/runs/41460361576).
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
