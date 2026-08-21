# F017 Apple Serial-F32 RN3 Partial-Root Recovery v1

1. A root is partial when it exists without an independently valid COMPLETE
   terminal and matching artifact inventory.
2. No program automatically deletes, renames, truncates, or overwrites it.
3. The operator first runs the read-only v2 terminalizer. Owner, attempt-start,
   receipt, terminal, and inventory hashes must resolve from the same root.
4. If durable attempt-start exists, the one attempt is consumed forever. The
   root may only be archived after a terminal adjudication; it can never be
   cleared to permit replay.
5. A pre-start root may be cleared only when owner/attempt-start/comparison-
   start/output/receipt/terminal are all absent and an operator signs an
   append-only clearing receipt containing device/inode census, path, hashes,
   release identity, reason, and timestamp.
6. Any orphan, missing inventory member, owner mismatch, receipt discontinuity,
   published output, or ambiguous process state requires operator intervention.
7. The clearing receipt is committed before a replacement approval can be
   considered. A replacement keeps a new event/release/attempt identity.
