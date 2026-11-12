# Fixed-route weighted host composition

`mlx_expert_mlp::weighted::setup` admits a profile, immutable `RouteBook`, copied arm and synchronous `Driver` against the published synthetic population. It returns a real `StepCoordinator` and checked input store. Use `host.backend().book().request(position)` with that store as the catalog and reader. Each commit moves one F32 [1,128] vector and fixture token 0 into coordinator ownership. The coordinator alone owns semantic position and retains the latest commit for delivery replay.

## Book and plan encoding

Construct a fixed book with `RouteBook::fixed("default")` or `RouteBook::fixed("mixed")`. The bounded constructor takes borrowed terms, verifies the weight domain and exact sum of four quarter-units per plan, then copies them into immutable owned slices. Setup checks the complete claimed identity against the published population before opening the source. The original 512-byte M=1 input uses the existing checked reader and SHA-256 gate. The staged request must match every field and the loaded activation.

All integers below are unsigned 32-bit little-endian. A field consists of its byte length followed by its bytes. Domain strings use ASCII and the indicated terminating NUL. Other text fields omit a terminator.

1. A plan starts with `weighted-plan-v1\0`, then its occurrence count, followed by each expert index and raw binary32 weight word in order.
2. A book starts with `weighted-book-v1\0`, then the profile and arithmetic version `binary32-rne-mul-then-add-v1` as fields. Append the raw 32-byte manifest, weight-content and input hashes in order. Append M, D, H, E, group size, layer, gate bits, up bits, down bits and plan count. Append each complete plan as a field.
3. SHA-256 over these bytes gives lowercase hexadecimal book and plan digests. The checkpoint set is the original weight-content hash. The revision is `weighted-route-v1.<book>`. The request ID is `weighted-v1.<book>.<decimal position>.<plan>`.

The five plans contain A, AB, ABC, ABA and ACB. They use 1; ¾+¼; ½+¼+¼; ¼+½+¼; and ½+0+½, respectively. The duplicate and the positive-zero term traverse the real cache and retirement boundary. During allocation and cache consumption the executor checks the occurrence demand and its component hashes against the next book term. Each lane starts at positive binary32 zero. Multiplication and ordered addition each round separately to binary32. An arithmetic failure discards the accumulator.

## Ownership and reservation

The executor uses the existing source, geometry, two-slot cache and occurrence pipeline. A plan reserves all of its diagnostic slots before payload access. An unvisited slot records that the callback did not run. An interrupted serialization retains its quota. Each instance has twelve slots, each capped at 32,768 payload bytes. No retry can replenish them. An uncertain retirement or failing finish quarantines the cache and poisons the coordinator adapter. The independent test Driver reports synthetic boundary facts, including device flags, imports and retirement.

`working_bytes()` supplies the sole standing charge W. It equals the actual cache ledger plus 1,114,112 host bytes and 32 MiB of prospective native allowance. `ledger()` exposes each part, including path-sensitive metadata, owned book capacity, staged and allocating tuples, pending demand, readbacks, the 512-byte private accumulator, record storage and a live JSON/serialization allowance. The coordinator owns the returned accumulator and charges input, output, previous output and history. Any result clones retained by callers are external. These logical reservations do not measure physical memory. The five observed coordinator peaks above W are 1,028, 1,544, 1,548, 1,552 and 1,556 bytes.

## Controlled evidence

The seven tests in `weighted_host` use both copied arms and both recipes. The Driver identifies each incoming role by all three component hashes before returning its authored vector. The stdlib Python reference computes each operation using signed dyadic integers and explicit ties-to-even rounding. Its golden lane words and route identities live under `fixtures/weighted-expert-mlp`. The standalone ABC/ACB control distinguishes ¼ from positive zero. A separate witness distinguishes rounded multiplication followed by addition from contraction.

| Completed position | Cached reads | Allocating reads | Fills | Hits | Evictions |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 9 | 9 | 1 | 0 | 0 |
| 1 | 18 | 27 | 2 | 1 | 0 |
| 2 | 27 | 54 | 3 | 3 | 1 |
| 3 | 36 | 81 | 4 | 5 | 2 |
| 4 | 54 | 108 | 6 | 6 | 4 |

The failed-delivery replay returns the original committed object. A fresh admitted input can still be read before an exact-stage refusal. The one-byte-short preflight cases refuse before the next input read. Fault controls cover payload corruption, partial projections, activation and down-domain refusal, cancellation, failed second occurrence, cleanup, unwind and cumulative exhaustion.

The source delta adds this weighted module, its integration test, the authored and golden fixtures, the Python reference and its controls, and the M2 and M3a notes. The inherited library root exports the module. The historical M2b README appends the acceptance outcome. The other 5,151 inherited objects retain their original bytes and modes. The weighted end-to-end native numerical bound and native attachment require a separate planner decision before physical preparation.
