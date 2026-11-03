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
advertising `undo: native_document_transaction` are eligible. The entire batch
has a 16,384 pointer-sample budget. Nested batches, file writes, exports,
application settings, undo/redo, and view/tool selection are excluded. Select the
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
