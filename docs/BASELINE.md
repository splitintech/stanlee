# Baseline evidence — 2026-11-02

Upstream `408563a37068daf7f1b4c6a9291daef039be8cb5` built unchanged on macOS arm64 with Qt 6.12.0 and Apple Clang using qmake and make. `QT_QPA_PLATFORM=minimal build-baseline/tests/tests` passed: **768 assertions in 58 test cases**. No application integration had been added at test time.

The unchanged baseline subsequently passed all six configurations in the
[native matrix](https://github.com/splitintech/stanlee/actions/runs/41447495951):
Linux Qt 5.15.2/6.5.3, Windows x64 Qt 5.15.2/6.5.3, macOS Intel Qt 5.15.2 and
macOS arm64 Qt 6.5.3. Distributed universal application packaging is a separate,
unfinished release requirement.

The inventory discovers 124 main-window actions and 2,159 UI/API entries. Run `python scripts/inventory.py /path/to/pencil --check` to detect source-surface drift. This mechanical inventory is deliberately marked semantically incomplete: dialog controls and declarations still require individual preconditions, inputs, undo semantics, API mappings and acceptance tests. It is not a claim of complete application coverage.
