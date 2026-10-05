# Disposition of bound admission source review

The [Claude Opus report](bound-admission-claude-review-2026-10-04.md) reviewed the [exact pre-remediation source packet](bound-admission-source-review-packet-2026-10-04.json). Its findings were checked locally against the synthetic implementation. This document records subsequent changes; the external reviewer did not inspect the final commit.

| Finding | Local disposition |
| --- | --- |
| C1. Catalog could be paired with unrelated files | Confirmed and fixed. `BoundCheckpoint` requires a private constructor token and a catalog marked as parsed from the identical `VerifiedFiles` object. Every bound read rechecks that association. Direct construction with a path-admitted catalog now fails. This is an API guard for honest callers, not an in-process sandbox. |
| C2. Static report temporary symlink | Confirmed and fixed. The static checker creates a unique exclusive temporary file and atomically replaces its output; a pre-existing `.tmp` symlink is not followed. Run the static checker before opening a bound file set, since writing in the root deliberately invalidates its directory identity. |
| C3. Derived views outlive fixture accounting | Confirmed limitation. Python callers can retain derived views after the parent borrow is released; logical page counters do not cover those allocations. A production adapter still needs independent process/MLX measurement and explicit buffer ownership. |
| C4. Mutable manifest provenance | Confirmed and fixed for ordinary callers. Manifest entries are copied into read-only mappings, verified digests and algorithms are retained, and bound catalog admission checks pinned schema/revision plus the exact entries/root/file sizes. The bound path still parses the manifest twice and checks equality; malicious in-process mutation remains outside this file-byte boundary. |
| C5. Descriptor cleanup | Confirmed and fixed for fixture context exits and verified-set close. Cleanup attempts every descriptor after an error; a normal fixture context exit with a live lease aborts and closes descriptors while keeping the leased buffer pinned. An OS close failure is surfaced; the fate of that one descriptor is OS-dependent. |
| C6. Digest key presence | Confirmed and fixed. Exactly one digest field must be present and well formed; `None` is rejected as `VerificationError`. |
| C7. Sampler stop return | Conditional claim does not apply to this pager: `BoundedPager.stop` always raises `PagerStop`. The adapter remains dependent on that contract. |
| C8. Mutable chunk-size global | Confirmed and fixed. The chunk size is captured per admitted file and used for later reads. |
| C9. Catalog geometry | Scalar and zero-row PLE tensors now fail with `CatalogError`; the bound catalog checks top-k and quantization override counts from the pinned config. Exact affine group-shape relationships and the PLE global-row convention remain numerical/runtime gates. |
| C10. Forged fixture leases | Confirmed and fixed. The store requires the original borrow object for GPU acknowledgement and release. |

The reviewer found no path where a failed chunk hash reaches a caller through the bound read API. This is a source observation, not a runtime proof. The pinned 106,218,444,193-byte checkpoint was not read under this new gate. The manifest remains the source trust root, Git-blob SHA-1 remains on some small metadata files, and per-span whole-chunk hashing has unmeasured I/O amplification. No real checkpoint I/O, MLX execution, inference, package installation, or benchmark was performed.
