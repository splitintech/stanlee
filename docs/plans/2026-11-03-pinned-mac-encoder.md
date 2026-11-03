# Stanlee pinned Mac encoder build - 2026-11-03

The accepted Mac architecture packages exposed divergent Homebrew dependency
bottles: x265 4.3 / ABI 217 on ARM and 4.2 / ABI 216 on Intel. A universal merge
must not discard notices or silently accept missing slices. Build one common
pinned encoder source set for both CPUs instead.

1. Pin FFmpeg, x264, libvpx, Opus and LAME to immutable source URLs/revisions and SHA-256 values.
2. Build static software encoder/validator executables with identical configuration
   on ARM and Intel. Preserve MP4/H.264, WebM/VP8/VP9, GIF/APNG and native audio
   workflows; avoid unrelated auto-detected libraries and nonfree components.
3. Include exact source archives, notices and build provenance with binaries.
   Keep Qt's own media backend libraries separate from the CLI tools.
4. Verify local source builds, native movie/audio exports and relocated package
   acceptance. Update CI with source-hash caching and architecture-bound manifests.
5. Merge every runtime executable/library with both slices, retain architecture
   notices explicitly, test final universal bytes on both CPUs, then attest them.

The remaining editor/client/signing gates stay active. This is experimental
packaging, with no default-branch merge or stable publication authorization.
