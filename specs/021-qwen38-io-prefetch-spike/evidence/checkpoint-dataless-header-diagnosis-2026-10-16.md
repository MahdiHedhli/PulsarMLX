# Pinned checkpoint header stall: File Provider dataless shards

Initial read-only diagnosis on 2026-10-16. No Qwen or Agy worker/header scan was
running at preflight. At that point no checkpoint Python, tensor payload,
full loader, inference, benchmark, file download or rehydration was requested.

The checkpoint directory has the `com.apple.fileprovider.dir#N` attribute.
`stat` and `ls -lO@` agree that three of eleven Safetensors shards, plus the
small `LICENSE` file, have full logical sizes but **zero allocated blocks**
and macOS `compressed,dataless` flags (`SF_DATALESS = 0x40000000`):

| Shard | Logical bytes | Allocated blocks |
| --- | ---: | ---: |
| `LICENSE` | 3,235 | 0 |
| `model-00006.safetensors` | 10,412,855,614 | 0 |
| `model-00009.safetensors` | 10,413,658,096 | 0 |
| `model-00011.safetensors` | 4,876,940,562 | 0 |

The three shards represent **25,703,454,272 logical bytes (23.938 GiB)** not
currently resident; including `LICENSE` gives 25,703,457,507 bytes. The other
eight shards have allocated blocks roughly
equal to their logical lengths. The Data volume had 285 GiB available, so
simple volume capacity does not explain the stalled header open. The prior
catalog attempt was interrupted in `read_header()` while waiting for the
first eight bytes of a shard. Since catalog traversal is sorted and shard 6
is the first dataless shard, File Provider hydration is the most likely cause;
the traceback did not identify the exact filename. A full-file digest read
would similarly require currently unavailable bytes. A historical acquisition
receipt is not evidence of present local residency.

Only the eight resident shards were inspected with a 3-second subprocess
deadline per file. Each probe read exactly the 8-byte Safetensors prefix and
the declared JSON header, capped at 32 MiB; it did **not** read tensor data.
The resident headers were responsive (the first was 65,663 bytes and took
about 1 ms). Static shapes from all eight contained **94 complete expert
triples of 144** and **128 complete PLE triples of 128**. All 222 available
triples satisfied U32 packed weight / BF16 partner dtype and the new
packed-word-to-affine-group equation; no mismatch was observed. The other
50 expert triples could not be checked because at least one component was
in a dataless shard. Representative observed shapes were:

```text
Expert 4-bit/group-64: weight [512, 640, 320]; scales/biases [512, 640, 40]
PLE 4-bit/group-32: weight [2500012, 20]; scales/biases [2500012, 5]
```

The dataless flags and zero-block counts remained unchanged after the
resident-header pass. Thus **the new full-checkpoint geometry admission is
untested, not passed**. Safe completion requires these exact shards to become
locally resident through an authorized File Provider operation, then a
bounded full-file digest/identity and header admission. Preflight should check
`SF_DATALESS` before opening any shard to avoid silently initiating a large
rehydration. A local unpublished fail-fast repair now checks every manifest
entry before digesting any file and rejects the flag in header-only admission
before opening a shard. A synthetic File Provider flag test verifies no digest
read occurs; the affected verified-file, catalog and adapter suites pass
15, 26 and 39 tests. Against the real current checkout, both header-only and
bound-verifier preflights rejected `LICENSE` with a `dataless checkpoint file`
error in about **0.06 seconds**, with no tensor/header read. These are expected
safe failures, not checkpoint admission passes. No hydration was performed.
This storage finding does not authorize a full-model load or change the
independent source-review and runtime/memory gates.

## Supported local download attempt, 2026-10-16

The user subsequently authorized local File Provider downloads of the existing
`LICENSE` and shards 6, 9 and 11. Before requesting content, the Data volume
still had **285 GiB available**, and `brctl quota` reported remaining iCloud
quota far above the size of those four files. File Provider evaluation
reported `isUploaded=1`, `isDownloaded=0`, `isDownloadRequested=0`,
`isDownloading=0`, and `isSyncPaused=0` for `LICENSE` initially. No account or
security settings were changed, and no source was moved or deleted.

One exploratory Foundation URL status invocation used the wrong Swift argument
form and inadvertently opened the `LICENSE` placeholder. The invocation was
interrupted; it had implicitly set `isDownloadRequested=1`. We then explicitly
called Apple's supported `FileManager.startDownloadingUbiquitousItem(at:)` for
`LICENSE` only. It returned successfully in about 0.26 seconds, which means
the request was accepted, **not** that the content downloaded. Multiple bounded
polls over several minutes continued to show `isDownloadRequested=1`,
`isDownloading=1`, `isDownloaded=0`, `isSyncPaused=0`, and zero allocated blocks
for the 3,235-byte file. No provider progress or actionable permission error
was reported. General connectivity to `www.icloud.com` and available account
quota do not prove the File Provider content route is healthy.

The three large shards remained `compressed,dataless` with zero allocated
blocks. Evaluation of shard 6 confirmed `isDownloadRequested=0`,
`isDownloading=0`, `isDownloaded=0`, `isSyncPaused=0`. No large shard download
was started while the tiny test file was stalled. At that point, the expected
full-file digests and all-shard header geometry could not be verified, and
the prior receipt remained historical evidence only. Do not open a dataless
shard as a probe or load the model.

## Separate pinned recovery and mixed-root static admission, 2026-10-16

The user then authorized checking a separate public upstream recovery. The
project-owned manifest pins repository
`pipenetwork/Qwen3.8-Flash-Next-MLX-mixed-4_8bit`, revision
`b2c422f3c643e36f04227a64d61796b44a4b1029`, exact sizes, three shard
SHA-256 values, and the `LICENSE` Git blob SHA-1. Header-only HTTP requests to
the pinned public `resolve` URLs returned 200 for `LICENSE` and shard 6; no
credential or access bypass was needed. A four-file subset of the exact
manifest was written under `/tmp`. The existing project-owned resumable
`acquire_qwen38_pinned.py` downloader passed its preflight with
306,707,886,080 bytes free, 25,703,457,507 bytes required, and a projected
281,004,428,573 bytes free, above its 100 GiB stop floor. It then downloaded
the four files into `/tmp/qwen38-recovery-b2c422f3`, one at a time, and
verified each file's pinned full-file digest before renaming its `.part` file.
The four-file receipt reports `complete=true` and 25,703,457,507 verified
bytes. All four files have nonzero allocated blocks and no dataless flag.
Independent fresh full-file digest checks immediately before header parsing
also passed for all four staged files. The expected shard SHA-256 values are:

| Staged file | Pinned SHA-256 |
| --- | --- |
| `model-00006.safetensors` | `c03d042c95831b6e79eb2e5cb361423d681f55ebecb7905688015ecf8cb47bb5` |
| `model-00009.safetensors` | `750853b2812719c2b76136677f1378bca9c316c3c350588bb50ccce8bdfde187` |
| `model-00011.safetensors` | `8e7b68292208146a0298e8e07548efd25889ba1c36d39a5ed27ab46b0d635436` |

The project-owned header-only `admit_checkpoint` routine was run through a
read-only path adapter selecting these four staged files and the original
resident paths for the other 21 manifest entries. It checked every selected
file's size, absence of symlinks and dataless flags, then parsed all 11 shard
headers and the index. The result was **3,215 tensors, 24,576 expert pages,
39,168 PLE pages, 2,764,800 bytes per sampled expert page, 819,200 bytes per
sampled PLE page, 5,348,837,400 fixed text tensor bytes, and 897,862,112
excluded vision tensor bytes**. The complete packed affine geometry passed.
This was a mixed-root static diagnostic, not a production bound admission:
the eight original resident shard payloads were not freshly rehashed, no
single verified root was assembled, and no tensor payload or checkpoint Python
was loaded or executed.

The original `LICENSE` and shards 6, 9 and 11 still had zero allocated blocks
and `compressed,dataless` flags afterward. File Provider later showed the
`LICENSE` request cleared (`isDownloadRequested=0`, `isDownloading=0`,
`isDownloaded=0`), without making it resident. The original directory was
not altered. At that stage the separate staging directory was only under
`/tmp`, where the operating system may remove it. Free disk after recovery
was about **261 GiB**. The
independent review, real I/O, MLX fence/residency, sampler, and numerical
parity gates remain open.

## Durable non-synced full root and strict bound admission, 2026-10-16

To avoid relying on `/tmp`, the four digest-verified recovered files were
APFS-cloned, not hard-linked, into the project's existing local
`~/Models/PulsarMLX` convention. `fileproviderctl evaluate` returned
`NSFileProviderErrorDomain Code=-1005` (`No item for URL`) for both that
parent and a copied file, including a large shard. The destination is on the
internal Data APFS volume, outside the File Provider-managed Documents tree.
The destination files have distinct inodes, nonzero allocated blocks and no
`dataless` flags. The original four placeholders retain their zero blocks and
`dataless` flags.

The other **21 resident original files (80,514,986,686 bytes)** passed a
pre-copy regular-file, size and non-dataless check. Their APFS clone copies
were assembled with the four recovered files into a separate exact-name root:

`~/Models/PulsarMLX/Qwen3.8-Flash-Next-MLX-mixed-4_8bit-b2c422f3`

The preflight had 280,981,512,192 free bytes and projected
200,466,525,506 bytes even if cloning required full physical copies, above
the 100 GiB floor. After cloning, the Data volume still reported about
**261 GiB free**, consistent with copy-on-write sharing. The original
checkpoint directory was neither moved nor replaced. The `/tmp` recovery
remains an extra copy, but the durable local root no longer depends on it.

The project's strict `admit_checkpoint_bound` entry point was run on the
**final path**. It opened all 25 manifest files through retained descriptors,
repeated every pinned full-file digest, checked file identity and shard
headers, and returned **25/25 files, 106,218,444,193 verified bytes, 3,215
tensors, 24,576 expert pages and 39,168 PLE pages**. Verification handles
closed cleanly. A fresh 25-file acquisition receipt was written after the
successful first bound pass; the header-only CLI also passed on the final
path. The strict bound pass was repeated after the directory received its
final name, so its result applies to that exact path. No checkpoint Python,
MLX model graph, payload inference or benchmark ran. A future runtime session
must call the strict bound entry point again and retain its live descriptors;
this one completed local pass does not create a persistent authorization token
or qualify device residency, fences, memory sampler, numerical parity or
performance.
