# Manual staged-checks implementation plan

Python stdlib Fraction/int/struct/hashlib, no new dependencies or native imports.
New package scripts/research/f020_staged_v4/ with numeric.py (bounded exact
interval/certificate/contraction), source.py (immutable original packed custody),
owner.py (live barriers and receipts), mock.py (public CPU/mock driver).
Tests scripts/research/tests/test_f020_staged_v4.py and independent literals.py.
No old execution entrypoint is redirected. Future native integration must use
these stage boundaries and separately qualify an adapter; current driver cannot
issue real capability and has no real-path CLI. In-process Python ownership is
trusted-caller fault containment, not a hostile-code security sandbox.

Source context validates fixed geometry, nine lengths/hashes, strict manifest and
framing with inherited snapshot schema methods, original input hash, BF16 envelope
and packed nibble order. In-memory public synthetic framing only in this goal.
Original source bytes are immutable and hash-bound before reference calculation.
Preserve packed bytes; no dense weight matrices. Stream one row, transient64
metadata groups. Cache at most32 identical public rows/interval arguments by exact
bytes/values, only as a computation reuse optimization (not reference substitution).
Independent fixed-point exp enclosure uses N80 positive Taylor on |z|/32<=1/2,
outward 256bit rounding of each term, tail term81/(1-a/82), five squarings and
reciprocal for negative arguments. Arithmetic intermediates have explicit bounded
numerator/denominator checks (4096bits); no unbounded lane LCM. All output interval
endpoints must lie on2^-256. Reject unsuitable precision; do not adapt per result.

Original reference constructor takes only original source context, never candidate
buffers. Certificate immutable tuples include g/u/bg/bu/h/E/a/oldBh/y/D, common
Q, source and profile digest. Independently derive references in owner; do not
accept arbitrary caller-provided certificate/ideal reference as authority.
Mutation tests may corrupt private fields to prove digest/check refusal.
All 2048 E values validated/scaled on fixed Q; down row accumulators checked on
every update<=768bits including signed ideal contraction and absolute propagation.
Original gate/up and local down affine preserve abs(s)*q+abs(b) Phi (not abs(w)).

Backend protocol separates gate_up(original), activation(g,u), down(h,original),
cleanup(); returns owned bytes and stage provenance/resource reports. Owner never
hands a mutable checked buffer back; bytes passed to down are identical object
and digest checked after callback. Backend mocks have explicit call counters and
failure seams. Reentrancy uses a nonblocking owner state flag before callback; any reentry
immediately terminalizes, with once-only cleanup after the outer callback unwinds; process-local consumed-attempt
registry refuses same identity even across owner objects; no persistence/real
retry authority is created. Terminal receipts frozen, linked, no replay API.
Backend compliance is not inferred merely from its declared counters: tests use
independent spy backend, and final source review audits dispatch call sites.

Resource design: bound packed source (~14MiB), immutable F32 stage buffers,
2048/4096-sized exact arrays, at most32 row caches and<=4096bit arithmetic
scratch. Reserve logical working bytes before buffers; measure CPU process peak
RSS with installed OS facility in tests. Actual native allocator/RSS/census cannot
be measured by mocks; inject strict report/schema failures and mark native controls
NOT RUN. Fixed deadlines and per-stage sample tests do not claim an independent
100ms native watchdog; retained watchdog source stays a mandatory native gate.

Order: docs+population -> cross-artifact analysis -> pre-review ACCEPT/0 -> literal
oracles/tests -> implementation -> CPU/mock and offline compile -> exact final
review/fixes -> local commit/freeze -> postcommit binding check -> handoff.
Do not run workspace native tests: explicitly inventory safe Python tests and
CPU-only Rust targets before selecting any. No Cargo build is needed for this Python-only change. No metadata setup scripts, new workers or installs.

Review01 explicit implementation obligations: require exact type bytes (reject
bytearray/memoryview), immutable tuple[int] clamp words and frozen/canonical report
copies. Recheck retained G/U/H digests and bound identities after every callback.
Certificate/receipt include checker and proof hashes. Interval ideal Y on2^-256;
E onQ; propagated D onQ*2^39; R retains gamma145 denominator2^24-145.
Periodic row checkpoints enforce deadline/RSS while computing reference, not only
at dispatch boundaries. ru_maxrss is bytes on Darwin, KiB on Linux; unknown units
refuse. Cache key includes role, packed row, both metadata rows and exact x/H
digest; max32entries, no cached omission of metadata. Native independent polling
remains a separate unrun gate. Decimal120 mock values are rounded through exact
rationals to F32 ties-even with an independently tested conversion algorithm.

Build identity for this Python-only implementation binds interpreter binary SHA,
base interpreter binary SHA, resolved path, version and optimize flag. Offline
compilation is Python bytecode compilation to own audit only. No Cargo/native
compilation is required absent Rust changes; no native executable runs.
Each full-shape positive executes in a fresh CPU child with lifetime ru_maxrss
used as an absolute cap; no baseline subtraction. Report actual elapsed time.
EPERR names the max-endpoint function; Q exclusively names the shared denominator.

Review03: record per-role cache hits/misses with each positive elapsed/RSS.
Periodic synthetic rows do not forecast nonperiodic original cost. Add the
reviewer-required A07P off-center integrated mock positive; original input/source
and certificates unchanged. This acceptance-side test detects omitted propagation.

The data-only Stage protocol lives in protocol.py so mock/oracle imports remain
independent of checker/source/owner. See resources-v4.md for logical accounting
and its separation from measured absolute CPU RSS and unrun native enforcement.
