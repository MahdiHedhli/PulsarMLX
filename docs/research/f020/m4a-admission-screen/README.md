# Selective admission on synthetic metadata

`screen-admission` compares successful serial cache calls with two persistent slots. It validates the complete input before starting with empty slots, zero clocks and empty history. It reads one metadata file and creates one report in a fresh directory. It owns no payload reader or native backend.

```sh
cargo build --offline --locked -j 2 -p mlx-expert-ranges --bin screen-admission
target/debug/screen-admission fixtures/admission-screen/template.json AdmitAll 12000000 ./screen-control
target/debug/screen-admission fixtures/admission-screen/template.json TwoHit 12000000 ./screen-candidate
python3 -B scripts/research/f020_admission_screen_reference_v1.py --check
```

Both output directories must be absent. An occupied directory, insufficient charge or invalid trace produces a nonzero exit status. The 8 MiB report cap also bounds each fresh output directory below 64 MiB. A caller who needs the exact charge can use `Trace::parse(bytes)?.ledger()?.logical_total`. Supply that integer to either arm. A report includes the exact input SHA-256, domain, binding catalog, policy, counters, event journal, final state, and logical charge.

## Input and identity

The closed JSON schema is `pulsarmlx.admission-screen.input/1`. See `fixtures/admission-screen/template.json` for a complete input. Every input has `provenance_kind` equal to `synthetic`. All numbers are unsigned integers.

| Field | Meaning |
| --- | --- |
| `class` | Source content and metadata SHA-256, one routed layer, D and H divisible by 64, group size 64, three 4- or 8-bit role widths, nine component lengths and two persistent slots |
| `catalog` | Ordinal-indexed routed experts, each with the class domain and a unique complete plan/content binding |
| `calls` | Ordered arrays of expert ordinals. Each array is exactly one cache call. Every supplied occurrence executes |

Role order is gate, up, down. Component order within a role is packed weight, BF16 scale, BF16 bias. Per-role shapes are H×D, H×D and D×H. The parser checks every byte length and the 32 MiB tuple ceiling. In the differential test, the real cache supplies its admitted `Demand.binding` verbatim. A synthetic opaque binding is a metadata commitment supplied by the caller. The model has no tensor payload from which to authenticate it.

An unambiguous routed identity consists of the bound domain, expert ordinal and plan/content binding. The domain digest covers ASCII `admission-screen.domain/1` with a terminating NUL, the two raw 32-byte content and metadata digests, seven little-endian u32 values (layer, D, H, group, three role widths), then nine little-endian u64 lengths. Hashes are lowercase hexadecimal. Each catalog row must declare this same digest. A duplicate binding or a nonsequential or repeated expert refuses. A different input never resumes an old slot or history.

The limits are 8 MiB of encoded input, 4,096 catalog entries, 4,096 calls, 1–64 occurrences per call and 65,536 total occurrences. The input must contain at least one call, one expert and a complete tuple. Unknown/duplicate fields, positional objects, nonfinite values, unsupported classes, truncation and trailing JSON refuse. The reference checks the equivalent schema and reads only the synthetic policy fixtures.

## What is retained

Each call is split into maximal contiguous waves with at most two distinct identities. Both arms protect all wave-entry hits before admitting any miss. Missing identities materialize in first-occurrence order. An admitted miss takes the lowest free persistent slot or the least recently used unprotected slot. A recency tie selects the lower slot. Each persistent fill increments that slot’s generation. Every successful occurrence advances the common clock. Only use of a persistent slot updates that slot’s recency. Transient tickets use a separate kind, an index within that wave and the wave epoch.

AdmitAll retains every materialization. TwoHit retains a miss if its identity was already in the 64-entry FIFO at wave entry. Other misses materialize into transient slots for that wave. Repetition within a wave reuses the bytes. It cannot promote an identity. At successful wave end, remove newly resident entries, then insert bypassed entries in first-miss order, discarding the oldest entry if necessary. A persistent eviction earns no FIFO credit. A catalog index in a slot or the FIFO refers to immutable full identity metadata shared by both arms.

Each occurrence belongs to exactly one category:

| Category | Meaning |
| --- | --- |
| R | The identity was persistent at wave entry |
| M | First occurrence of a unique wave miss, including a bypass |
| U_R | Later occurrence of a newly retained miss in the same wave |
| U_T | Later occurrence of a bypassed miss in the same wave |

Materializations equal M. Issued bytes equal M times tuple bytes. Each materialization requests nine logical components. Read avoidance is R + U_R + U_T. The real AdmitAll cache hit counter corresponds to R + U_R. Counts and byte totals have separate fields. Ratios are integer numerator/denominator pairs over executed occurrences. Per-request averaging, physical I/O, latency and shipping speed are outside this measurement.

## Charge and journal

Both policies receive the same trace-specific standing envelope. It includes two modeled persistent and two modeled transient tuple capacities, the bound catalog and parsed calls, FIFO64, fixed state and tickets, one event per admitted occurrence, 16 KiB of transactional/encoding scratch and 8 MiB for report encoding. Payload capacity is modeled only. Actual retained catalog bindings occupy 32 bytes each. Slot and history references use compact catalog ordinals. Parsed call arrays and binding arrays have exact boxed lengths. The journal reserves the admitted occurrence count. The temporary call state, wave tickets and individual binding formatting fit inside the fixed control/scratch allowances. Input parsing precedes model admission. The CLI drops the raw input buffer before running the policy.

For the supplied template on the verified host each arm’s charge is 8,463,508 bytes. Each modeled tuple is 13,824 bytes. The unchanged real cache has its own path-sensitive charge. It includes its actual two-slot pool, source metadata, 1 MiB control allowance and 64 KiB workspace. Logical charges do not measure peak RSS.

The event digest starts with `admission-screen.events/1\0`, raw input SHA-256, raw domain SHA-256 and one policy byte (0 for AdmitAll, 1 for TwoHit). Each row appends call index (LE16), one-based wave epoch (LE64), expert ordinal (LE16), category (0–3 in table order), ticket kind (0 persistent, 1 transient), slot (u8), then generation (LE64). The state digest uses `admission-screen.state/1\0` with the same input/domain/policy prefix, followed by the compact UTF-8 JSON for the final slots, FIFO and counters in their declared field order. Digests and the bound catalog let a reader verify the ordered full identity journal. The independent reference reconstructs both digests and the complete named journals. Its `verify_report(input_bytes, policy, report_bytes)` function independently rejects missing, reordered or altered rows and checks the common payload and envelope arithmetic.

## Evidence and limits

The reference corpus contains all 1,092 nonempty words of lengths 1–6 over three experts. Two partitions and two policies yield 4,368 runs. Its ordered digest is `dbece58b3c20a3f9208a696959ae3b5e03ed7f1d8c241c62710a47d24c9ce0ff`. The CPU differential checks the unchanged cache on the two original copied recipes. Per recipe, it uses every word of lengths 1–4 with both partitions (240 runs) plus six named schedules. It checks all nine borrowed component hashes, callback order, slot and generation, fills/hits/evictions, component reads and requested bytes. Wave boundaries on the real side follow the unchanged source partition; callbacks expose the actual slots and generations. M2a includes its warm single-A call, M2b retains its two calls, and M3 retains all five, including the zero-weight C.

| Synthetic schedule | AdmitAll materializations | TwoHit materializations |
| --- | ---: | ---: |
| Two hot experts with two pairs of scan misses | 10 | 8 |
| One wave with duplicate demand | 2 | 2 |
| Two singleton calls for the same expert | 1 | 2 |

The hand-checked examples illustrate retention mechanics. They supply no workload distribution or policy recommendation. Boundary controls also exercise FIFO eviction at 65 distinct identities, a fresh bypass after persistent eviction, signed/invalid input refusal, exact/short admission, atomic counter overflow and the maximum catalog/call/occurrence population.

The bounded authentic input inventory returned `TRACE_INPUT_UNAVAILABLE`. Across two pinned repository subdirectories and the worker’s retained Rust007–020 evidence roots, 7,907 paths were inspected. None of the seven requested basenames was found. No candidate bytes were read. Compiler outputs, scratch, dependency trees, unrelated checkouts and external symlink targets were outside this inventory. The archived historical driver and aggregate curve describe LFU with decay. They cannot establish full calls, denominator, starting state or a held-out selection for this policy.

Full M3 was accepted at `a77e3e44ae1461c5249d88c2f8d2e2f28b7c687f` for fixed-route copied synthetic composition. That result includes 48 occurrences, 144 projections, 48 activations and 20 weighted vectors in four serial physical children. Both 2,560-coordinate gates passed under the original result commitment `cea19eb076ceeea1d927ee94dddb5b6a942e8e3e302e787736c1044ebea7dbec`. The weighted claim is spent (1/1). This host foundation leaves M4A acceptance pending. A future workload screen needs admitted original capture bytes, complete call boundaries, denominators, initial state and a held-out rule. Native confirmation and M4B–M4D require separate decisions. Copying remains the default.
