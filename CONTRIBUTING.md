# Contributing

Contributions are GPL-2.0-only. Preserve upstream and dependency attribution.
Never commit session tokens, private documents or client credentials.

Run `python -m pytest`, build the Python wheel and test its clean installation.
Native changes belong in the Pencil2D fork and must preserve its existing tests,
manager boundaries, undo behavior and Qt 5/6 build compatibility. New C++ bridge
code uses C++17. Keep upstream-style builds unchanged unless automation is enabled.

Every operation requires a versioned contract, native mapping, coverage entries,
failure tests and evidence. Do not replace native rendering with a bitmap-only
approximation. Do not mark platform/client qualification complete from source or
mock tests. Update capability drift evidence on every upstream baseline change.
