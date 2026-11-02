# Native issue fixes and upstream review

The native application pin includes the three fixes listed below. They are
bundled as a reproducible patch in `patches/pencil2d`, with original authorship
retained in the native fork's Git history.

| Issue | Native feature branch | Upstream review |
| --- | --- | --- |
| #1332, stroke frame ownership | `fix/stroke-frame-1332` | [PR #2038](https://github.com/pencil2d/pencil/pull/2038) |
| #1942, hidden-layer edits | `fix/hidden-layers-1942` | [Merge/review follow-up on PR #1989](https://github.com/pencil2d/pencil/pull/1989#issuecomment-6577811329) |
| #1964, download verification | `contribute/download-verification-1964` | [PR #2039](https://github.com/pencil2d/pencil/pull/2039) |

The standalone combined fixes revision is
`7c0cdc1974c1a9725b32c0e77125818e5d84c106`. Its runtime code matches the earlier qualified fixes revision; the later change
only makes download-verification documentation neutral for upstream.
[The preceding hosted run](https://github.com/splitintech/pencil/actions/runs/41440231887)
has six successful native build/test/package configurations and one cancelled
Intel/Qt 5 dependency installation. The aggregate workflow is not fully green.
The download-verification tests pass on hosted Linux, Windows, and macOS.

Original frame-switch code fails the new stroke regression tests. Coverage
includes bitmap/vector ownership, tablet pressure/device identity, continuation,
same-frame navigation, and both undo modes. Hidden-layer tests check warning
requests and unchanged pixels, clipboard, selections, frame content, and dirty
state. Warning presentation is overridden in unit tests to avoid nested native
message-box loops; production warning presentation retains its existing body.

## Integrated Stanlee qualification

The build manifest pins the current bridge plus all three fixes. The merge
preserves independent snapshot support and the shared editor modifiability
check. The integrated Qt 6.12 macOS build passes **67 native cases / 942 assertions**.
Stanlee passes **28 Python, CLI, and real MCP/native tests**, with one Windows-only
test skipped on macOS. The complete application builds, including its optional
bridge. Patch replay reproduces the exact standalone fixes tree and ancestry
checks confirm that the immutable pin includes both bridge and fixes.

These are local integrated results. They do not establish hosted Windows/Linux
bridge acceptance, all interactive client acceptance, or completion of the alpha.

## Reproducing the source bundle

```sh
python scripts/verify_native_fixes.py
python scripts/verify_native_fixes.py --native /path/to/pinned/native-checkout
```

The second command confirms native HEAD, bridge/fix ancestry, and exact patch
replay against the recorded upstream tree. Use a full-history native checkout.
See [patch instructions](../patches/pencil2d/README.md) before applying changes to
another checkout; Stanlee's pinned native source already includes them.

Upstream merge decisions belong to Pencil2D maintainers. These requests concern
the independent fixes; they do not submit the entire experimental MCP bridge.
