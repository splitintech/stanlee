# Development setup

Use the exact fork revision in `build-manifest.json`. Native build instructions:

```sh
# Run from the Stanlee repository root.
stanlee_native_revision=$(python3 -c 'import json; print(json.load(open("build-manifest.json"))["fork_revision"])')
git clone https://github.com/splitintech/pencil.git ../pencil-stanlee
git -C ../pencil-stanlee checkout --detach "$stanlee_native_revision"
python3 scripts/verify_native_fixes.py --native ../pencil-stanlee
cd ../pencil-stanlee
mkdir build
qmake -o build/Makefile STANLEE_AUTOMATION=1 CONFIG-=debug_and_release CONFIG+=release
make -C build -j4
QT_QPA_PLATFORM=offscreen QT_STYLE_OVERRIDE=Fusion build/tests/tests
```

For reproducibility, check out the manifest's exact commit after cloning. The
branch can advance. macOS requires Qt Core/Widgets/Gui/XML/Multimedia/SVG/Network
and LinguistTools plus Apple command-line build tools. Local validation uses
Qt 6.12.0 arm64. The qmake application is
`build/app/Pencil2D-Stanlee.app/Contents/MacOS/pencil2d-stanlee` on macOS and
`build/app/pencil2d-stanlee` on Linux. Full platform qualification is pending.
ffprobe is required for validated exports; FFmpeg is required for native movies.

Install Python dependencies and the local package as described in README. Use
absolute paths for workspace grants and the native application executable.
Place discovery in a short private directory to stay within Unix socket path
length limits. Stanlee refuses existing discovery directories readable by others.

```sh
stanlee --workspace /absolute/animation-workspace \
  --discovery-dir /absolute/private-short-directory \
  --application /absolute/native-executable launch

stanlee --workspace /absolute/animation-workspace \
  --discovery-dir /absolute/private-short-directory sessions
```

`launch` starts asynchronously. Poll sessions for discovery, inspect the
document, then send commands with its current session/document IDs and revision.
Every operation's schema, native mapping and undo behavior is available through
`stanlee operations` and MCP `stanlee://operations`. Unsupported operations fail
explicitly. Layer creation, FPS and supported content edits now use native undo
transactions. `edit.batch` groups only advertised reversible document operations;
see [native editing](EDITING.md) for bounds, context rules and conflict behavior.

Run the MCP adapter using the same global flags followed by `serve`. Stdout is
reserved for the official SDK's stdio protocol. Native diagnostics never include
the private token. Inspect again and reconcile changes after a revision conflict.
Connection status and a disconnect button appear in the native application's
status bar.

`export` accepts native input, repeated `--export`/`-o`/`--export-sequence` outputs,
camera, dimensions, start/end including `last`/`last-sound`, transparency, explicit
overwrite and timeout. Only formats in the pinned native parser are accepted;
transparency is currently qualified for PNG sequences. Native warnings fail the
job and staged outputs must decode before publication. Multi-file publication is
atomic per file. A later failure rolls earlier outputs back. External changes
prevent destructive rollback and produce `publication_recovery_required` with
retained backup paths. Output directories are locked during publication. Process
death can leave `.stanlee-publication.lock` and backup files; crash recovery is
unfinished, so inspect the owning process and retained files before recovery.

MCP `export_document` creates an independent native snapshot of unsaved state,
then submits an export job. Its optional FPS override changes only that snapshot.
Snapshots are retained in the first workspace's private `.stanlee-snapshots`
directory for recovery. `document.checkpoint` also saves an explicit native
checkpoint without changing active state. `document.recover` accepts that path,
optional `source_path`, and explicit `discard` for dirty active content. It replaces
the document, invalidates prior handles/history, and marks recovered content dirty.
Poll `job_status`; `cancel_job` affects only workers owned
by the running service. Jobs persist locally under the discovery directory's
parent. Windows interruption recovery and global cross-process concurrency are
not yet fully qualified. Job metadata is visible only when the server's grants
include every recorded originating workspace. Confirmed dead session records
are cleaned without signalling processes; regular files at socket paths survive.
Abrupt parent-process death can require manual worker cleanup;
restart evidence is not a claim that worker supervision is complete.

## Client configuration

`stanlee --workspace … --discovery-dir … --application … config --client codex`
prints an argument vector for the official `codex mcp add` command. It does not
execute it or overwrite configuration. This follows the [official Codex MCP
documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli). The local
command syntax and a real native subset workflow were tested with Codex CLI
0.164.0-alpha.11.1. See the [recorded evidence](evidence/2026-11-02-codex-cli.json).

Read tools publish MCP read-only annotations. The generic native command and
export tools retain destructive annotations because they can discard content or
overwrite files. The noninteractive Codex test used the official per-tool
`mcp_servers.stanlee.tools.<tool>.approval_mode` configuration for its already
authorized disposable workspace, supplied only to that invocation. The
[official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
documents these controls. Configuration generation preserves the client's own
approval choices.

For Cursor or Claude Desktop, choose `--client cursor` or
`--client claude-desktop`. Pass `--existing /absolute/config.json` to produce a
merged JSON document on stdout. Unrelated settings are preserved, and an existing
Stanlee entry produces a conflict. Inspect the generated result before saving it
to the client's documented configuration location. See [Cursor's documentation](https://cursor.com/docs/mcp)
and the [official local-server guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers).

Generated stdio configuration is also tested by starting the installed Python
module through the official SDK client. The Codex evidence covers its recorded
subset only. Cursor and Claude Desktop qualification remain pending.
