# Persistent exports and crash recovery

Each export runs in an owned supervisor. The service keeps its parent pipe open;
EOF on service death terminates the native worker tree. POSIX uses the supervisor's
own process group; Windows uses a kill-on-close Job Object. Explicit cancellation
and deadlines stop owned processes before publishing any staged output. The
service never kills a discovered human editor.

`--workers 1..8` bounds rendering. Kernel lease slots enforce the same configured
limit across services sharing a job directory. Use one common worker setting for
those services. Jobs retain an owner UUID with a kernel lease, so a reused PID does
not make an old job look alive. Legacy records use conservative liveness checks.
Restart reports proven-dead work as interrupted and preserves unknown ownership.

Output publication writes and fsyncs a journal before destructive replacements.
It retains original backups and fingerprints each staged/published file. A crash
between replacing a file and updating its journal is recoverable. Recovery rolls
back unfinished publications only while the current target still matches this
publisher's bytes/identity. New external edits are preserved; conflicting backups
and journals remain available and their paths are reported. Completed journals
keep validated output and finish cleanup. Readers can observe intermediate files;
this is recoverable sequence publication, not a multi-file filesystem transaction.

CLI `recover-outputs DIRECTORY...` and MCP `recover_outputs` inspect only explicitly
granted output directories. Live publishers hold kernel leases and cannot be
recovered. Startup also inspects output parents of interrupted jobs whose stored
request remains within the current workspace grant. It does not scan unrelated
folders. Review conflict reports before deciding how to use retained originals.

Persistent `.stanlee-publication.lock`, owner and worker lease files are expected.
Kernel locks release on process death. Unlinking lock files while another process
holds an old descriptor would break mutual exclusion, so idle files are retained.
A hard crash during initial staging can leave an empty orphan stage; recovery
protects user outputs, but exhaustive orphan cleanup remains unqualified.


## Multi-directory crash transitions

The real-process matrix kills publication after journal preparation, stage/backup
announcement and copying, intent, replacement, per-file publication, the durable
commit and partial cleanup. Both overwrite and new-file modes use two distinct
output directories. Recovery itself is killed after restoring/removing an output
and then rerun to verify idempotence. POSIX original permission bits and unrelated
files are preserved.

A committed transaction keeps its durable `complete` phase when later external
edits are observed. It returns a conflict and retains available backups/journal;
repeated recovery never converts this commit into rollback of other committed
files. Earlier source could downgrade that phase and subsequently restore/delete
other committed outputs. The regression tests demonstrate and prevent both modes.
Stage/backup directory entries are synced in each destination directory before
publication intent, even when the transaction journal lives in another directory.

The 42-case transition matrix passes locally. Cross-platform execution must be
recorded independently. These process-death fixtures do not establish power-loss,
filesystem-corruption, native editor crash or complete client/platform qualification.
The initial unjournaled empty-orphan window described above remains open.

## Native project archive publication

Native `.pclx` compression now streams through `QSaveFile` with direct-write
fallback disabled, rather than opening the original archive with `wb`. Compression
or commit failure leaves the original intact; only a complete archive is renamed
into place. A native child-process fixture exits after writing a source asset but
before finalizing/committing the archive, verifies the original bytes and archive
remain valid, and verifies a subsequent save succeeds. Missing-source compression
also preserves existing bytes.

This closes the direct-truncation path independently of the Python output journal.
It does not establish OS power-loss/filesystem guarantees or atomic publication of
the legacy `.pcl` plus data-directory pair. The bridge continues to save `.pclx`.
Successful Python export overwrites preserve existing POSIX access modes; newly
created private outputs use mode `0600`.
