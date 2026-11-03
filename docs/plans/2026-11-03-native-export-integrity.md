# Stanlee native export errors and camera identity - 2026-11-03

Source review confirms that native CLI exports ignore MovieExporter/exportFrames
status and can return success after failure. Invalid camera names fall back after
localized warnings. Movie exports resolve a chosen camera by name again, which can
select another camera when names repeat. Movie buffering uses camera dimensions
instead of the actual requested output resolution.

1. Propagate native movie/image export failure through the CLI process exit status.
2. Reject missing/ambiguous explicitly requested cameras and unsupported explicit
   formats and invalid explicit numeric/range arguments; preserve the default camera and extensionless PNG conventions.
3. Carry native camera IDs from CLI/GUI selection into movie rendering, preserving
   name fallback only for legacy callers that provide no ID.
4. Base bounded movie buffering on actual output pixels and validate dimensions.
5. Add direct native CLI failure/ambiguous-camera and movie-versus-PNG camera
   composition fixtures, plus all existing reference/history/package checks.
6. Keep source changes as review commits, rebuild the pinned packages and record
   exact platform qualification independently. No upstream contact or stable release.
