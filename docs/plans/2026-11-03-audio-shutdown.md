# Stanlee audio/export shutdown qualification — 2026-11-03

A newly relocated package returned a process failure after reporting a successful
PNG render of a document with audio. Publication correctly withheld outputs. The
cause is not yet established. A retained-workspace repeat also exposed a cold
application version probe exceeding ten seconds; these are separate observations.

1. Reproduce the export failure in a retained generated document and obtain a
   native debugger trace; distinguish shutdown faults from startup/toolchain issues.
2. Inspect media-player, clip and backing-device lifetimes. Fix a demonstrated
   native ownership problem without suppressing failure exits or weakening checks.
3. Add regression coverage for repeated media load/export/close and retain exact
   source/package evidence. Do not retry failed exports as if they succeeded.
4. Rebuild enabled/disabled native configurations and the relocated installed-wheel
   package; keep previous successful platform checkpoints distinct.
5. Record qualification limits and source review commits. No default merge,
   upstream contact, trusted signing or stable release is implied.
