# Release policy

Unsigned development previews are experimental. An alpha requires the complete
Mac reference workflow and automated native integration tests. Upstream outreach
begins only after that gate. Stable release requires every acceptance gate in
BUILD_PLAN.md, all platform/client combinations, signed/notarized macOS universal
and signed Windows x64 binaries, and a qualified Linux x64 package.

Record source/fork revisions, SDK and protocol versions, toolchains, checksums,
dependency notices, provenance, test results and known limitations per artifact.
Publish `stanlee-mcp` only after checking name ownership. Do not tag or describe a
development snapshot as a working alpha. Package upload, native signing and
upstream acceptance must be reported separately from source delivery.
