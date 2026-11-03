# Experimental application packaging

The package workflow builds pinned native source with official Qt 6.12 on Mac
ARM/Intel, Windows x64 and Linux x64. It deploys Qt plugins, FFmpeg and ffprobe,
embeds native corresponding source, Qt SBOMs and license texts, records source revisions and
per-file hashes, then tests the extracted application in a different directory
using an installed MCP wheel. The encoder's Mac libraries are isolated from Qt's
media libraries even when their SONAMEs match. The headless platform plugin is
included explicitly.

The reference fixture exercises atomic pressure edits and undo/redo, camera keys,
vector geometry, imported independent sound bytes and decoder timing, save/new/
reopen, PNG frames and an audio-bearing 24 FPS movie. It verifies output metadata
and source-file preservation. This is automated SDK acceptance, separate from
human/client acceptance and the complete editor reference workflow.

Mac architecture artifacts are merged only when resources and source pins match;
every executable and native dependency must contain both slices. The merged final
archive is tested on both Mac architectures. A failed merge or either acceptance
job prevents nightly publishing. Each artifact has a SHA-256 sidecar; archives
retain executable permissions and symlinks. CI artifacts expire after 14 days.

`packages.yml` runs on review-branch pushes. Scheduled publication starts only once
the workflow reaches the default branch. Manual publication requires its explicit
`publish` input. `publish_nightly.py` requires all six acceptance results at the
exact source revision and matching archive hashes. Existing tags/releases/assets
are never overwritten. Snapshots are prereleases named `nightly-DATE-REVISION`.
No alpha/stable or PyPI publication is performed by this workflow.

Before distributing packages as qualified releases, complete the dependency notice
and corresponding-source audit, full native format/codec/reference fixtures,
clean-machine OS qualification, upgrades/rollback/uninstall, real client matrix
and signed final-byte acceptance. Those remain explicit gates. Current Homebrew,
Ubuntu and Chocolatey encoder toolchains are not yet reproducible locked inputs.

## Signing and qualification

Run `packaging/sign_application.py --root UNPACKED_PACKAGE` on its native platform.
Mac signing uses an already provisioned `STANLEE_APPLE_SIGN_IDENTITY` and
`STANLEE_APPLE_NOTARY_PROFILE`; the script signs native files with hardened runtime
and timestamp, submits through `notarytool`, staples, and checks Gatekeeper.
Windows uses the installed certificate identified by `STANLEE_WINDOWS_CERT_SHA1`,
SignTool SHA-256 signing/timestamping and verification of every EXE/DLL. Missing
configuration fails before signing. No credentials are downloaded or inspected.
These paths require actual signing-environment acceptance before release use.

Signing changes bytes. Repackage, regenerate checksums and rerun acceptance before
recording a release. `qualify_release.py --record RECORD.json` checks semantic
coverage, all platform/client combinations, exact source revisions, final archive
hashes, signed/universal requirements and full reference/crash qualification.
It returns failure while any gate is missing. Signing by itself never marks an
artifact stable-qualified or publishes it.


Qt 6.12 Linux uses `linux_gcc_64`. Its Windows catalog separates the MSVC repository;
`install_qt_windows.py` adapts pinned aqt 3.3's repository suffix for that exact
version/architecture while retaining normal archive checksum verification and
relocation. Other Qt versions/architectures are not rewritten. The official catalog
dry run resolves base and multimedia archives. Acceptance removes build-machine
Qt plugin/loader/PATH settings before launching the extracted application.
