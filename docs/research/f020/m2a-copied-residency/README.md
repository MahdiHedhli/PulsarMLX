# M2a copied host residency

The two-slot cache owns complete, verified CPU tuples. Both fixture recipes produced four fills, two hits, two evictions and six ordered consumptions for `A B A C B A`. The retained-descriptor reader attempted 36 component reads. The allocating control attempted 54. One cold tuple costs nine reads and a warm hit costs zero.

| Fixture role bits | Bytes per slot | Two allocated slots | Source metadata M | Standing charge W |
|---|---:|---:|---:|---:|
| 4/4/4 | 13,824 | 27,648 | 5,074 | 1,146,834 |
| 8/4/8 | 22,016 | 44,032 | 5,550 | 1,163,694 |

These are observed fixture ledgers. Root-name and path lengths contribute to M. Each W includes both slots, M, the 1 MiB control allowance and the 64 KiB executor workspace allowance. Occupied bytes increase with successful admissions, while W also covers idle or quarantined slots. The generated fixtures have D=128, H=64, E=3.

The success and replay test charged W plus 45 bytes for the activation, scratch, owned digest and next token. Delivery failed after the first commit. Replay returned the retained result with one total activation read and one total executor dispatch. A budget one byte below the combined charge refused before reading. Cancellation and a failed finish retained distinct errors, released request resources, and kept the quarantined cache charged.

[Host API and ledger](../../../../crates/mlx-expert-ranges/README.md) · [Integration manifest](integration.json) · [Host test results and executable linkage](host-evidence.json)

The host qualification used offline, locked debug and release builds of `expert-residency-core`, `mlx-expert-ranges` and `backend`, with two Cargo jobs. Each profile compiled without running tests first. Executables were checked with `otool -L` before the 14 test binaries ran serially, each with one test thread. Each profile passed 135 tests. The two built host lifecycle examples were inspected and excluded from the test count.

M2a is host-qualified. Full M2 still needs a copied native importer/MLP attachment, owner-thread evaluation, verified copied-tensor lifetimes and numerical checks on authorized hardware. M3 and M4 are unstarted. The completed Studio005 timing screen was inconclusive. Copying is the shipping default.
