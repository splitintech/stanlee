# Stanlee publication crash transition matrix — 2026-11-03

Continue the approved crash-recovery work beyond the existing replacement-window
fixtures. This is scoped qualification of publication durability, not a claim of
complete native application/client/OS crash acceptance.

1. Kill a real publisher after durable preparation/backup, intent, replacement,
   per-output publication and complete-journal transitions, across two directories.
2. Exercise both overwrite-with-backups and creation-without-overwrite. Before
   durable completion recover the original set; after completion retain the new set.
3. Interrupt recovery itself after restoring/removing the first output, then repeat
   recovery to establish idempotence. Preserve unrelated files and permissions.
4. Exercise external changes and incomplete cleanup without allowing rollback to
   overwrite external content. Keep conflict backups/journals inspectable.
5. Run the process matrix locally and through Windows/Linux/Mac Python CI; retain
   exact evidence. Repair any demonstrated ownership/durability problem and rerun
   appropriate application validation. Keep native/OS power-loss and client crash
   qualification open where it has not been executed.
