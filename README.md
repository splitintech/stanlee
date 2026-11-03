# Stanlee

Native Pencil2D automation for external AI clients through MCP and a shared CLI.

**Under development; no qualified alpha or stable release yet.** Stock Pencil2D
provides CLI export. Live editor control requires a separately built, explicitly
enabled Pencil2D–Stanlee application. The bridge is optional and disabled by
default; it contains no Python or AI runtime.

The complete scope and acceptance gates are in [the build plan](docs/BUILD_PLAN.md).
Implementation, tests, platform qualification, client qualification, and release
publication are tracked independently. A listed operation is not proof of native
implementation or acceptance.

Python 3.11+ is required; development uses Python 3.12 and official MCP SDK 2.3.0.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/stanlee --help
```

Pencil2D source and application changes live in
[splitintech/pencil](https://github.com/splitintech/pencil). Builds start from
upstream revision `408563a37068daf7f1b4c6a9291daef039be8cb5`.

The pinned native build includes fixes for stroke frame ownership (#1332),
hidden-layer edits (#1942), and download verification (#1964). Review the
[bundled patches](patches/pencil2d/README.md) and
[project context](docs/PROJECT_CONTEXT.md) for source revisions, upstream requests,
and validation limits.

The development command set supports authenticated sessions, native inspection,
layer properties/order/duplication, keyframes/exposure, camera animation, strokes,
atomic document batches, undo/redo, previews, save/reopen, independent snapshots
and validated saved/snapshot export jobs. Full editor coverage is unfinished.
See [native editing](docs/EDITING.md), [current status](docs/STATUS.md) and [setup](docs/SETUP.md).

GPL-2.0-only. See [LICENSE](LICENSE) and [dependency notices](NOTICE).
