# Stanlee audit-gap engineering implementation — 2026-11-03

Implement the engineering gaps identified by the comprehensive technical audit,
starting from controller f8061c3800f5d9d2ed7eff7dfcd498209bfb3ee2 and native
e7bc6f8387b0142fcb5d8b61cf12f03682d225c0 in their existing isolated /private/tmp
checkouts. Preserve unrelated SplitIn and private company-context work.

1. Close GUI revision/dirty observation holes, synchronize job-manager creation,
   retain successful-overwrite permissions, preserve semantic-review annotations,
   and enforce operation-specific output payload contracts. Add regression coverage.
2. Derive media expectations from native project metadata, validate container,
   dimensions, resolved frame range, timing and expected audio before publication;
   discover real native/encoder capabilities instead of assuming format availability.
3. Make native project saves publish atomically with original-file preservation;
   add interruption/failure checks separate from the Python publication journal.
4. Complete durable job progress/logs/request records and CLI cancellation, then
   extend applicable import/export and editor controls through typed native APIs.
5. Reconcile registry, documentation and semantic coverage without marking missing
   capabilities implemented. Add reproducible reference/acceptance and release
   qualification tooling, retaining explicit actual-client/signing/clean-machine gates.
6. Rebuild native binaries, run focused and full appropriate tests, verify registry
   mirrors and patch replay, and record exact changes/evidence/remaining gates in
   notes/live. Keep native manifest source identity accurate for edited sources.

Copy this sanitized project-only implementation plan into the controller docs.
User authorization covers implementation and local verification. Do not invent
human/client acceptance, signing identities, upstream approval or publication proof.
Do not merge/publish a stable release as a substitute for qualification.
