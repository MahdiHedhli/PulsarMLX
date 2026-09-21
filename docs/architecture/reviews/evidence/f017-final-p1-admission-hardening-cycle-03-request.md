# PulsarMLX F017 final P1 execution-gate repair — independent cycle 3 review

Review committed bytes only at exact pushed commit
`322b8c72922ba8b83f85b03b18c795095021549a` on branch
`feat/017-rust-native-inference-runtime`, using the repository read-only.
Do not edit. Do not execute P1, full-model inference, or read checkpoint payload.

The controlling exact-head GitHub Actions run is `32540722272`. Inspect its
head, conclusion, jobs, pinned native dependencies, qualification skips, and
test results directly rather than trusting this request.

The prior independent cycle-2 review at `33e394cd...` returned REJECT with:

- BLOCKING `F017-IR1-P1-001`: no committed exact admission-contract instance
  and no identity-bound real bounded-P1 executor that mechanically snapshots
  all 22 counters and emits the execution receipt.
- BLOCKING `F017-IR2-P1-003`: `platform.processor()` makes the M1 Ultra device
  gate always fail.
- DEFENSE_IN_DEPTH `F017-IR2-STATE-001`: textual state-root comparison permits
  symlink ancestry ambiguity.
- DEFENSE_IN_DEPTH `F017-IR2-ORACLE-003`: receipt schema/census too permissive.

Cycle-3 committed changes intentionally close only claims the repository can
substantiate:

- device identity now executes absolute `/usr/sbin/sysctl -n
  machdep.cpu.brand_string`, requires exact `Apple M1 Ultra`, and separately
  requires `arm64`; permanent mock tests reject M1 Max, M2 Ultra, generic arm,
  spoofed/trailing text, command failure, and wrong architecture;
- state-root validation requires exact absolute contract binding, symlink-free
  ancestry, strict resolved identity, current ownership, and private mode;
- receipt validation now pins exact top-level and nested key censuses, strict
  non-boolean non-negative integer 22-counter snapshots, all authority
  identities, token vector, result, terminal, and timestamps;
- contract validation now binds a repository-relative executable path and SHA,
  rejects traversal/symlinks/non-executable bytes, and pins `argv[0]`;
- exact CPython 3.13.13 / NumPy 2.4.5 oracle regeneration remained unchanged,
  Rust parity remained 4/4, and pinned native B1/B2 remained 13/13 locally.

Builder reconstruction found no honest implementation of the requested real
bounded P1 in the committed architecture: the real one-token model path is the
Python MLX `scripts/research/glm52_inference.py`, while the 22 Rust/native
ownership counters are split across `crates/stream` and an engine soak harness.
There is no production path that both performs the requested token 9703 ->
21615 and exposes a unified live 22-counter snapshot. Do not treat the
admission wrapper, a test fixture, hardcoded zeros, or a Python sidecar as a
real executor. Independently confirm or refute this from the tree.

Rerun/inspect at minimum these attacks:

1. execute without a committed exact contract instance;
2. substitute another executor or mutate executor path/SHA;
3. remove one mechanical counter source or spoof one receipt counter;
4. manually craft a receipt; add/remove fields; use bool as an integer;
5. replay the consumed authorization, submit a fresh authorization after the
   contract-wide claim, and race two consumers;
6. bypass mandatory stop, emit a second token, retry, or resume;
7. spoof M1 Ultra with M1 Max, M2 Ultra, generic arm, or trailing brand text;
8. exploit a state-root symlink or alternate equivalent path;
9. mutate checkpoint identity, Git identity, runtime identity, and executor
   identity;
10. verify exact-head CI, pinned MLX 0.31.2 / MLX C 0.6.0, native fail-closed
    behavior, and zero qualification skips;
11. rerun the B1 missing-native-free attack and exact B2 source-first/no-eval/
    no-sync sequence;
12. verify independent oracle identity/parity and that P1/checkpoint reads
    remain zero.

For every finding give a stable ID, severity (`BLOCKING`,
`NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`), exact path/symbol, evidence,
failure mode, smallest honest repair, CI requirement, and oracle impact.
Both BLOCKING and NON_BLOCKING_REQUIRED prevent acceptance.

Return exactly one final verdict:

- `ACCEPT_FOR_SINGLE_BOUNDED_M1_ULTRA_P1`
- `REJECT`

Do not authorize or execute P1.
