# Claude Opus source review, bound checkpoint admission

This is untrusted external review evidence from a source-only packet, not runtime approval.

- Model: `claude-opus-5-5-medium` via `agy`
- Conversation: `4022d9fb-4d98-4f74-af54-64bc0fa7cfa0`
- CLI status: `SUCCESS`; turns: 1
- Packet: [exact submitted text](bound-admission-source-review-packet-2026-10-04.json) and [file hashes](bound-admission-source-review-manifest-2026-10-04.json)
- Packet SHA-256: `cf0b88df58446885ec07ee5a8380ed4530a54b888e39b47819f640acdb095eac`
- No weights, checkpoint Python, credentials or unrelated host data were submitted. The reviewer reported no tool use.

## Raw response

# Source review: Qwen3.8 bound checkpoint admission (7 files)

I did not create a plan artifact or call any tools, because you asked for none. This review is based only on reading the supplied text. Nothing was run, and nothing here says anything about the real checkpoint or MLX. Two modules the tests and fixture adapter import were not supplied: `qwen38_bounded_pager` and `test_qwen38_bounded_pager`. Any finding that depends on how they behave is marked **conditional**.

## Bottom line

I found no path where bytes that failed verification reach a caller through `VerifiedFiles.readinto` or `BoundCheckpoint.read_page_into`. The flow in `qwen38_verified_files.py:158-169` is sound:

* It reads the whole chunk with `pread` into immutable `bytes`.
* It checks the chunk's SHA-256 against the hash recorded at construction.
* It re-runs `check()`, then copies from that same `bytes` object.

Construction is also sound. The full-file digest and the per-chunk hashes are computed from the same buffers (lines 103-107), so a file changed during hashing can't produce chunk hashes that pass. The confirmed defects are around that core: catalog/file binding, provenance, file-handle (FD) lifetime, accounting, and test coverage.

---

## Confirmed code defects (ranked)

### C1 — Medium: catalog↔files binding is not enforced
* **Where:** `qwen38_page_catalog.py:192-208`, `:234-288`, `:305-309`; `qwen38_fixture_io.py:35-49`; spec line 3 ("Only the bound result may feed future runtime page reads").
* **Defect:** `BoundCheckpoint(catalog, files)` is a public constructor and doesn't check where the catalog came from. `PageCatalog` keeps no record of which `VerifiedFiles` set or manifest it was parsed from.
* **Unverified catalogs are easy to get.** The unbound `admit_checkpoint(root)` builds one from path-based headers, and `main()` (line 309) publishes it. That path:
  * checks `is_symlink()` and then opens the file in two separate steps (`:259` → `admit_qwen38_static.py:32`), so the file can be swapped in between;
  * opens with `path.open("rb")`, which follows symlinks;
  * runs no digest at all.
* **Triggering sequence:**
  1. `cat = admit_checkpoint(root)`. An attacker swaps a shard's header between the size check and `read_header`.
  2. `files = open_pinned_files(root)` succeeds once the real file is restored.
  3. `BoundCheckpoint(cat, files).read_page_into(k, buf)` returns authentic bytes from the wrong offsets, i.e. the wrong tensor or rows.
* **Tests:** `test_bound_page_uses_only_verified_spans` (`test_qwen38_verified_files.py:129-140`) does exactly this with an unrelated synthetic catalog, so the test suite treats the gap as expected behaviour.
* **Fix direction:** make `BoundCheckpoint` constructible only from `admit_checkpoint_bound` (for example with a private token). Store a reference to the `VerifiedFiles` object inside the catalog and assert `catalog._files is self.files` on every read.

### C2 — Medium: static admission output can overwrite any file via a symlink
* **Where:** `admit_qwen38_static.py:208-211`.
* **Defect:** `temporary.write_text(...)` follows symlinks and isn't opened exclusively.
* **Triggering sequence:** someone who can write to `--dest` (the same "ordinary mutation" attacker the spec has in mind) creates `static-admission.json.tmp -> ~/.zshrc`. The operator then runs `admit_qwen38_static.py --dest ...`. The target file's contents are replaced with the JSON, using the operator's permissions.
* **Side effect:** writing into the checkpoint root changes the directory's mtime/ctime. That poisons any `VerifiedFiles` open on the same root at the time (`qwen38_verified_files.py:139-140`). This fails closed, but it's a self-inflicted outage.
* **Fix direction:** write outside the checkpoint directory, or open the temp file with `os.open(..., O_CREAT|O_EXCL|O_NOFOLLOW, dir_fd=...)`.

### C3 — Medium (fixture scope): host-memory accounting undercounts when callers keep derived views
* **Where:** `qwen38_fixture_io.py:202-212`, `:100-115`.
* **Defect:**
  * `release()` releases only the parent `memoryview`s.
  * Any derived view (`seg[0:]`, `memoryview(seg)`, numpy/`mx` array built on the buffer) keeps the `bytearray` alive.
  * The pager then evicts the page, and `_reconcile` drops the buffer from `self.buffers`.
  * Result: `retained_host_buffer_bytes` and `resident_bytes` undercount real memory without any error. The comment at line 207 admits derived views can outlive the parents, but nothing tracks or caps them. The only remaining guard is the external `process_bytes` observation.
* **Triggering sequence:**
  1. `b = store.borrow(k)`, then keep `v = b.segments[t][0:]`.
  2. `store.gpu_done(b)`, then `store.release(b)`.
  3. Repeat on new pages. Real resident memory grows past the weight limit while the reported accounting stays inside it.
* **Related case:** if an extension holds an export on a parent view, `view.release()` raises `BufferError` partway through the loop. Some views are released, `segments` isn't cleared, and the lease stays pinned. That's safe, but untested.

### C4 — Low/Medium: the verified digest isn't stored immutably, and provenance checks are incomplete
* **Where:** `qwen38_verified_files.py:68` (`result[name] = entry` keeps a reference to the caller's dict); `:111` (`_File` doesn't store the digest it was verified against); `qwen38_page_catalog.py:237-253`.
* **Defects:**
  * `VerifiedFiles.entries` and `.files` are public, mutable, and share dicts with the caller.
  * In bound mode, `admit_checkpoint` checks only `repo`, not `schema` or `revision`.
  * The manifest is parsed twice: once in `open_pinned_files` (`:201`) and again in `admit_checkpoint` (`:237`).
* **Triggering sequence** (direct-constructor use):
  1. `vf = VerifiedFiles(root, entries)`.
  2. `entries[i]["sha256"] = D2`.
  3. Write manifest M2 with the same sizes, `D2`, and any revision.
  4. `admit_checkpoint(root, manifest_path=M2, verified_files=vf)` passes the comparison at `:251`.
  The bytes served are still the ones verified against D1, so integrity holds, but they're now labelled as M2 / another revision.
* **Scope:** the `open_pinned_files` path isn't exposed to the aliasing, because its entries come from freshly parsed JSON.
* **Fix direction:** deep-copy the entries; store the verified digest and algorithm in `_File` and compare against those; parse the manifest once and pass it down; check schema and revision in bound mode.

### C5 — Low/Medium: file-handle (FD) leaks and replaced exceptions
1. **Normal exit with an active lease leaks every fixture FD.**
   * Where: `qwen38_fixture_io.py:232-235`.
   * Sequence: `with store: b = store.borrow(k)` with no release. `close()` raises "cannot close" before reaching lines 225-227. `closed` stays `False` and there's no `__del__`.
2. **`close()` sets `closed=True` before cleanup.**
   * Where: `qwen38_fixture_io.py:219-227`.
   * If `pager.stop` raises anything other than `PagerStop` (conditional on the pager), the FDs leak and later `close()` calls do nothing.
3. **The exception-exit path can leak FDs and replace the original error.**
   * Where: `qwen38_fixture_io.py:246`.
   * `_reconcile()` can raise `PagerStop` (from the accounting-mismatch branch at `:104-106`) before the FD loop at `:247-249` runs. That leaks the FDs and replaces the "preserved" original exception, which survives only as `__context__`.
4. **`VerifiedFiles.close()` has the same ordering problem.**
   * Where: `qwen38_verified_files.py:184-190`.
   * `closed=True` is set first. Any `os.close` error (EINTR/EIO) stops the loop, permanently leaking the remaining FDs and `root_fd`.
* **Fix direction:** close every FD in `try/finally` and collect the errors; set `closed` only after cleanup, or close FDs no matter what the pager state is.

### C6 — Low: the digest-key check and the hashing code disagree on missing keys
* **Where:** `qwen38_verified_files.py:60-62` (checks `get(...) is None`) versus `:97-98, :108` (uses `in entry`).
  * `{"sha256": None, "git_blob_sha1": X}` passes validation, then `compare_digest(hex, None)` raises `TypeError`, not `VerificationError`.
  * `{"sha256": X, "git_blob_sha1": None}` prepends the Git blob header to a SHA-256 digest, giving a false mismatch.
* Both fail closed, but the wrong exception type can slip past handlers that catch `VerificationError`.

### C7 — Low (conditional): `_observe` relies on `pager.stop` raising
* **Where:** `qwen38_fixture_io.py:118-128`.
* If `stop()` returns normally (for example, an idempotent stop on an already-stopped pager), line 126 runs with `sample` never assigned and raises `UnboundLocalError`.
* It still fails, just with the wrong exception. Add an explicit `raise` after `stop`.

### C8 — Low: chunk size is read from the module global at read time
* **Where:** `qwen38_verified_files.py:154-156`.
* `CHUNK_BYTES` isn't stored per file. If the global changes after construction (or a `mock.patch` exits, as in `test_qwen38_verified_files.py:42`), chunk boundaries no longer line up. Every read then fails and poisons the set.
* This fails closed, but it's fragile. Store the chunk size in `_File`.

### C9 — Low: catalog geometry gaps
* **No cross-checks between the tensors in an affine triple** (`qwen38_page_catalog.py:93, :99-101`). Shapes of `weight`, `scales` and `biases` aren't compared against each other, against the group size, or against the config's quantization overrides. The bound path also skips the static checks for `num_experts_per_tok` and quantization (`admit_qwen38_static.py:108-115`).
* **Scalar shape gives the wrong exception.** A U32 scalar (`shape == []`, accepted by `inspect_shard_data`) raises `IndexError` at `:99` instead of `CatalogError`.
* **Zero-length spans are handled inconsistently.** Zero-sized dimensions produce zero-length spans. `BoundCheckpoint` accepts them silently, while the fixture's `_read_exact` (`qwen38_fixture_io.py:136`) rejects them.
* **Unverified row-mapping assumption.** `ple_key_for_global_row` (`:158-165`) assumes rows are laid out contiguously across shards. The source only asserts this in a comment.

### C10 — Low: leases can be forged
* **Where:** `qwen38_fixture_io.py:199-210`.
* `gpu_done` and `release` accept any `PageBorrow(lease_id=...)`. A forged or stale borrow can release another holder's lease, and lease IDs are presumably small sequential ints. That breaks pinning (but not byte integrity).

---

## Inherent limitations and hardening (not defects in this code)
* **Trust root:** the manifest itself isn't digest-pinned, as the spec acknowledges.
* **SHA-1 on catalog inputs:** Git-blob SHA-1 protects `config.json` and `index.json`, which are exactly the files that drive the catalog. Collision resistance is broken, so this matters only if the upstream publisher is adversarial. Recommend a SHA-256 for every file.
* **Directory mtime/ctime in the root identity** (`:139-140`): any file created in the checkpoint directory poisons the set. Examples: `.DS_Store`, lock files, a rewritten receipt, `static-admission.json`. This affects availability, not security.
* **Root path race:** `is_symlink` → `resolve` → `open` leaves an intermediate-component race (`:78-87`). Digests stop byte substitution, so only the meaning of "root" is affected.
* **JSON parsing:** `json.loads` keeps the last duplicate key, accepts `NaN`, and auto-detects UTF-16/32. Parsers in other tools may behave differently. Pinned bytes limit this to an adversarial upstream artifact; consider an `object_pairs_hook` that rejects duplicates.
* **The AST review of `qwen4_exp.py` is not a safety gate** (`admit_qwen38_static.py:123-140`):
  * Code that runs at import time is allowed: decorators, class bodies, base-class expressions, default arguments.
  * The import denylist misses `ctypes`, `sys`, `builtins`, `pickle`, `shutil`.
  * `getattr(builtins, "ex"+"ec")` gets around the dynamic-call check.
  * `ast.parse` on hostile input can be used for denial of service.
  * The `runtime_static_review` output field shouldn't be read as qualifying the file.
* **Per-span I/O amplification:** each read rehashes at least one whole 1 MiB chunk per span, so roughly 9 MiB per expert page with no chunk cache. Not benchmarked, as the spec says.
* **Other limitations:** no thread safety; in-process callers can mutate public state; APFS case and normalization insensitivity; writes through shared mmaps can lag mtime (covered by chunk hashing); type checks happen after open (a FIFO is harmless with `O_NONBLOCK`); the fixture marker is advisory.

---

## Tests that miss real bugs or prove less than their names suggest
| Test | Gap |
|---|---|
| `test_replacement_and_symlink_are_rejected` (`verified:60-66`) | Creating `replacement.bin` changes the root directory's mtime, so this can pass on the root check without ever exercising per-file inode detection. |
| `test_short_read_stops_and_releases_reservation` (`fixture_io:140-149`) | Truncation is caught by the pre-read identity check. The `preadv` short-read branch (`:150-151`) and the verified short read (`verified:163`) are never reached. |
| `test_bound_fixture_read_fails_closed_after_content_change` (`fixture_io:70-83`) | Fails on identity, not on the chunk hash, so the verified fixture path never tests chunk mismatch. |
| `test_chunk_digest_detects_content_when_metadata_check_is_stubbed` | Doesn't assert `poisoned`. |
| `test_unsafe_manifest_entries_fail_before_open` | Doesn't assert that `os.open` was never called. |
| `test_bound_page_uses_only_verified_spans` | Treats the C1 binding gap as expected behaviour. |
| *(missing)* | No happy-path or negative tests for `open_pinned_files` (schema, repo, revision, total size), the bound branch of `admit_checkpoint` (root, entries, sizes mismatch), or a successful `admit_checkpoint_bound`. |
| *(missing)* | Nothing covers C2–C8 or C10: symlinked tmp file, derived-view accounting, mutation after verify, FD leaks on exit or close errors, digest keys set to `None`, `CHUNK_BYTES` drift, `_observe` on a stopped pager, forged lease release. |

If you approve, I can write an implementation plan that fixes C1–C8 and adds tests that each reach exactly one failure branch.
