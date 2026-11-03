# Stanlee completion build — 2026-11-03

Continue the original complete Pencil2D MCP plan from controller `d3cc207` and
native `84351d2a`. The user explicitly requested building the remaining coverage,
recovery/acceptance and application release capabilities. Existing work is delivered through review branches.

1. Refresh source refs and preserve unrelated changes. Keep private company context
   out of public source and release artifacts.
2. Extend native document lifecycle, vector geometry/selection/styles, bitmap
   operations, audio/assets, playback, palettes, viewport, settings/dialog logic
   and import/export. Extend shared contracts, native preconditions, observations,
   undo and invalid-context tests with every capability family.
3. Review discovered coverage semantically. Distinguish user-facing capabilities,
   supporting APIs and internal controls. Record explicit mappings and evidence;
   do not declare generated inventory or an operation count complete coverage.
4. Finish persistent job supervision and crash-time output publication recovery:
   durable journals, process ownership, safe rollback preserving external edits,
   restart reporting, cancellation/deadlines and configurable worker concurrency.
5. Build reproducible experimental application/source packages for macOS universal,
   Windows x64 and Linux x64. Include native runtime/encoder dependencies,
   manifests, licenses, checksums, provenance and installed-package smoke tests.
   Add nightly publishing automation with explicit experimental labeling.
6. Expand fixtures and the reference workflow across native editor, CLI, installed
   MCP package, crash/restart and each platform. Qualify real supported clients
   using official configuration while preserving existing user settings.
7. Implement signing/release gates and fail closed when signing credentials or
   required acceptance evidence are absent. Unsigned experimental artifacts are
   separate from signed stable releases. Never manufacture signing or client proof.
8. Run meaningful local, package and CI checks. Persist exact source revisions,
   artifacts, evidence and remaining external dependencies in status and private
   company-context notes. Deliver source through review branches and draft PRs.

No sub-agent delegation is requested. The original full plan and every unmet gate
remain active until supported by actual implementation and acceptance evidence.
