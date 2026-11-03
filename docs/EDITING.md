# Native document editing

These are development APIs, available through MCP `command` and CLI `command`.
Discover the exact schemas in `stanlee://operations` and each operation resource.
Inspect first and pass the returned `session_id`, `document_id`, and
`expected_revision` on every mutation. Layer indices describe the current stack;
refresh them after reorder/delete. Public layer IDs keep their native identity
through undo/redo and are never reused within the same live document. Reopening
or replacing a document invalidates all its old handles.

## Layers and timeline

| Operation | Native behavior |
|---|---|
| `layer.create` | Create bitmap, vector, sound or camera content and select it |
| `layer.select` | Select a current layer; view state, outside document batches |
| `layer.update` | Rename and/or set visibility explicitly |
| `layer.duplicate` | Copy type, properties and keys under a new layer ID/name |
| `layer.reorder` | Move one layer to an explicit stack position |
| `layer.delete` | Delete an explicit layer; retain the protected bottom camera |
| `timeline.add_key` | Add a key at an empty position on the current visible layer |
| `timeline.duplicate_key` | Copy an exact key to an empty position |
| `timeline.move_key` | Move one exact key; destination replacement requires `swap=true` |
| `timeline.remove_keys` | Remove exact keys; a non-sound layer retains at least one |
| `timeline.select_keys` | Select explicit keys; view state, outside document batches |
| `timeline.reverse` | Apply native reverse-order semantics to exact selected keys |
| `timeline.expose` | Add/subtract native exposure for explicit selected keys |
| `timeline.scrub` | Select a frame without creating content |
| `content.opacity` | Set uniform bitmap/vector opacity on exact keys |
| `project.fps` | Set project timing without changing the application default FPS |

Frame selections contain 1–4,096 unique exact keys, positions 1–1,000,000.
Timeline content edits require a visible layer. Exposure delta is -1,000–1,000,
nonzero, with a 16,384 cumulative step budget and a resulting frame-position
limit. Native collision/minimum-exposure rules still apply. Whole-layer opacity
is expressed by enumerating that layer's keys; native fade controls are pending.

## Camera keys and previews

`camera.configure` sets camera dimensions, 1–8,192 per axis.
`camera.key` creates or explicitly overwrites an exact key. Translation uses
canvas coordinates; rotation uses degrees; scale is positive (0.01–100).
`easing` is the native enum (0 linear through 40 out-in-bounce); the shared
contract describes all 41 values. Optional `path_x`/`path_y` must be paired;
`path_moved` determines whether native interpolation uses the custom path point.

`camera.reset` uses native field options: 0 transform, 1 translation, 2 scale,
3 rotation, 4 horizontal alignment, 5 vertical alignment, 6 hold. Alignment and
hold affect the following key and require it to exist.

`frame.preview` and MCP `preview` accept an optional `camera_index` and `frame`.
Previews use independent content, native composition and minimal bitmap bounds
matching native save/export. They do not crop live images or load their backing
assets into live keyframes. Preview dimensions are limited to 4,096 per axis;
encoded PNGs are limited to 2 MiB.

## Atomic batches and history

An `edit.batch` contains 1–64 `{operation, arguments}` steps. Only operations
advertising `undo: native_document_transaction` and not `atomic: false` are eligible. The entire batch
has a 16,384 pointer-sample budget. Nested batches, file writes, exports,
external asset imports, application settings, undo/redo, and view/tool selection are excluded. Select the
appropriate tool and its settings before batching native strokes.

```json
{
  "operations": [
    {"operation": "project.fps", "arguments": {"fps": 24}},
    {"operation": "layer.create", "arguments": {"type": "bitmap", "name": "Gesture"}},
    {"operation": "canvas.stroke", "arguments": {"points": [{"x": -20, "y": 0}, {"x": 20, "y": 20}]}}
  ]
}
```

Schemas and batch eligibility are checked before any step executes. Native
context requirements are checked as each step runs. The GUI thread executes the
bounded batch without yielding to another edit. Success adds one native undo
entry. Failure restores the before-state and preserves earlier undo/redo history;
reinspect after failure because restoration signals can advance the revision.
`rollback_failed` reports a restore failure explicitly. Cancellation is supported
before dispatch; a dispatched bounded edit completes or rolls back.

Document transactions integrate with both Pencil2D history modes. They retain
the same Object, working directory, source path and document identity. Sound
bytes are cached independently for the lifetime of document history. Native
human strokes before and after agent edits retain their own undo entries.
Active colors, tools, viewport and application preferences remain live.

Some native human actions do not create history entries. `history.undo`/`redo`
check content signatures before restoring a document transaction and return
`history_conflict` if newer unrecorded document changes would be overwritten.
The history index stays unchanged. Reconcile those changes explicitly; a failed
conflict check is not permission to discard them.

Transactions currently retain full independent document snapshots. Memory and
snapshot preparation cost grow with project size. Large-project responsiveness,
complete vector/audio editing, and remaining native actions are still release
qualification work. `contracts/coverage.json` records reviewed mappings separately
from the larger pending inventory.


## Vector content, palettes and assets

`vector.inspect` returns paginated native cubic curves, handles, pressure and
styles. At most 4,096 segments are returned per response. `vector.path` accepts an
origin and 1–2,048 cubic segments; colors use native palette indices. Geometry,
explicit curve selection, affine transform, width/feather/color/visibility styles,
native closed-path fill and deletion have separate operations. Invalid indices,
singular transforms and unfillable paths fail without retaining partial edits.

Palette add/update/remove/move preserve native references. Used vector colors
cannot be removed. Native XML/GPL import can append or replace; replacement must
retain existing indices. Export requires an explicit granted path and overwrite
consent. Palette/file imports are outside atomic batches.

`audio.import` copies at most 64 MiB of source bytes into a sound layer at an exact
frame. Replacing an existing key requires `overwrite`. Source deletion cannot
remove the imported content. Inspection reports decoder duration, pending timing,
name and playability. Timing is asynchronous and advances the revision; inspect
again before mutating. `audio.update` changes the native clip name. Invalid decoder
formats may remain unplayable; complete codec qualification is pending.

`import.image` uses native placement rules on a visible paintable layer. Bitmap
preflight bounds dimensions and decoded pixels; `content.clear` clears explicit
bitmap/vector keys with undo. Vector import formats need further qualification.

`project.playback` sets undoable range/loop values. `playback.set` changes live
play/stop and sound state. Stop is allowed while playing; unrelated mutations
remain busy. `view.inspect`/`view.set` support pan, center and horizontal/vertical
flips in addition to scale and rotation. These are view changes, outside batches.

`session.close` requires a clean document or explicit discard and flushes the
response before quitting. It cancels close if newer document/tool/modal activity
appears. It does not mark human history clean as a shortcut around save prompts.


## Bitmap regions and scanned paper

`bitmap.inspect` normalizes an independent image copy and returns its canvas bounds,
opacity and up to 1,024 explicitly requested RGBA samples. It preserves live image
backing data, revision, dirty state and history. Samples outside content are
transparent. Native image coordinates include negative positions; centered imports
place their top-left at `(-width/2, -height/2)` before the chosen native placement.

`bitmap.transform` applies a six-number native affine matrix to an explicit region
or the full bitmap bounds. It clears the old region and pastes the transformed
pixels in one document transaction. Singular and oversized transforms fail before
retaining any edit. Optional `smooth` selects native interpolation. Existing frame
opacity remains attached to the keyframe.

`bitmap.copy` copies a source region into an exact existing destination bitmap key.
`target_index` and `target_frame` identify the destination; `dx`/`dy` offset canvas
coordinates. `cut: true` clears the source region in the same undo unit. Both layers
must be visible. This operation preserves the system clipboard. Clipboard exchange
and full vector transfer workflows remain separate unfinished capabilities.

`bitmap.paper` applies Pencil2D's native scanned-paper algorithm to 1–256 exact
bitmap keys. Threshold is 0–255; `red`, `green` and `blue` explicitly choose native
line-color retention. The native algorithm classifies lines and existing alpha;
it can stop a column at an existing transparent pixel. Processing is bounded to
four million source pixels per command. Rectangle/affine/copy allocations are
bounded to 8,192 per axis and 32 million pixels, with bounded canvas positions.
Large projects require explicit smaller regions or key groups.

Exact-pixel fixtures cover independent imported bytes, reflection, region movement,
cut/paste, atomic rollback, opacity, single/multiple-key paper processing, threshold
zero, undo and save/reopen. These are automated local capability tests; the complete
platform/client and performance matrix remains a release requirement.


## Native export failure and camera selection

The pinned native CLI returns failure for failed image/movie exports, unsupported
explicit extensions, missing/ambiguous explicit camera names and invalid numeric
options/ranges. Extensionless exports retain PNG behavior. Explicit CLI movie
transparency fails; Stanlee continues to qualify transparency only for PNG.

Movie descriptors carry a camera layer ID from CLI or GUI selection. Duplicate
labels therefore do not replace a GUI-selected camera with another layer. Name
fallback remains for legacy descriptors without an ID. Automated CLI fixtures
compare selected-camera movie/image composition; the complete GUI dialog workflow
remains a separate acceptance gate.
