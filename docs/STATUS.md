# Implementation status — 2026-11-02

This is a tested development foundation, not a completed alpha or stable release.
The approved complete plan remains the scope contract. Unfinished items are not
waived or converted into unsupported upstream limitations.

| Plan area | Current evidence | Remaining gate |
|---|---|---|
| Step 0 | Approved plan and project context persisted before code work | Complete |
| Step 1 | Public Stanlee and Pencil2D fork; upstream baseline pinned; unchanged Mac build and 768 assertions/58 native tests pass; Python dependencies locked; identity/settings separated | Remote platform/Qt matrix; reproducible packaged applications |
| Step 2 | 124 main-window actions; 2,159 discovered UI/API entries; drift checker | Semantic review, full mappings, dialog/tool controls, per-capability acceptance |
| Step 3 | Optional runtime activation; private authenticated POSIX IPC; bounded framing; GUI-thread dispatch; native signal revisions; polling events; visible disconnect | Windows ACL/named-pipe runtime qualification; stale crash-discovery cleanup; full observation coverage |
| Step 4 | New/open/save, handles, native snapshots, optional snapshot-only FPS override; source path/dirty/undo/assets tests | Old-format save, safe close, full checkpoints/recovery and malformed/missing-asset matrix |
| Step 5 | Native pressure/modifier stroke pipeline, dynamic tool properties and history undo/redo; layer creation/select; keyframes; FPS; tool/color/view selection | Full vector semantics, all layer/timeline edits and undo, bounded atomic batches/rollback |
| Step 6 | Automated Mac subset of reference workflow and native PNG export | Entire alpha workflow, human-edit acceptance and native video/audio fixtures |
| Step 7 | No upstream outreach performed | Complete alpha first, then proposal/design engagement |
| Step 8 | Remaining surface explicitly inventoried | Advanced timeline, vectors, cameras, audio, palettes, preferences and other editor capabilities |
| Step 9 | Saved/snapshot native CLI jobs, repeated exports and native aliases, ranges, dimensions, camera arguments; decode/dimension/frame-count/PNG-alpha validation | Full format/codec/audio/content/timing and GUI import/export coverage; native warning localization |
| Step 10 | Persistent job IDs/status; cancellation/deadlines; isolated profiles; owned process groups; staged outputs; one worker per service | Crash supervision, cross-process concurrency, restart/PID-reuse proof, Windows recovery and whole-sequence publication rollback |
| Step 11 | Official SDK stdio; tools/resources/images/prompts; generated config merge preservation; real SDK stdio tests | Signed-in Codex, Cursor and Claude Desktop acceptance; subscriptions/progress negotiation and complete resources |
| Step 12 | GPL notices, build manifest, Python wheel/sdist build and CI definitions | Clean-machine binary packaging, source/provenance bundle, stable signing/notarization, PyPI ownership/publication, upgrades/rollback/uninstall |

Native source integration is on `splitintech/pencil` branch
`stanlee/automation-bridge`, pinned by this repository's build manifest. Normal
fork `master` remains upstream code. New C++ tests pass with **787 assertions in
59 cases** locally. Python/native integration and CLI tests pass locally; the
latest CI results must be read separately from this local evidence.

The native shared registry currently advertises 21 implemented development
operations; it deliberately excludes pending operations. Contracts document that
layer creation and FPS edits lack undo. The coverage register is mechanically
complete only for its stated scan patterns, semantically incomplete, and is not
a declaration of full Pencil2D coverage. Windows discovery ACL checks and deadline-bounded named-pipe transport are
implemented; their runtime qualification is pending CI. Invalid ACLs fail closed. Source builds on
other platforms do not establish native bridge runtime acceptance.

MCP tools share the command service with CLI. Native frame previews use the
application's Object/camera composition. Export validation currently establishes
decodability, explicit dimensions/ranges and PNG alpha support, not comprehensive
content/audio equivalence. Native CLI can return success after an export failure;
Stanlee checks outputs independently. Unsupported transparency fails before work.

Private discovery tokens and company documents are excluded from source and
artifacts. No alpha/stable tag, PyPI publication, signed binary or upstream
acceptance is claimed.
