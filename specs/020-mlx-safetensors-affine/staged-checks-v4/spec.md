# Prospective selected staged checks v4

Status: approved implementation scope; NOT numerical/native qualification.
Base adda03ad9097372fe7e9d8fa59d2853281af6c1f, isolated numerical worktree.
The 2026-10-04 user approval supersedes prior pending implementation decisions.
Parallel ownership adaptation: preparation integration has its own existing owner
and worktree; this numerical track has one sole owner and no additional workers.
No shared source, feature selector, historical contract or ledger is modified.

US1 (P1): independently derive an original-input certificate before any backend call.
FR01 preserve v3 bytes and all fixed source/input/shape/recipe/resource identities;
create prospective contract4 with A-CHECK-MAG and no executable authority.
FR02 original immutable packed bytes alone define exact G,U,Phi,Bg,Bu,H,Y;
all 2048 original rectangles lie in [-16,16]^2; fixed certified q,p yield
Lg=Cmax*min(3/2,q+M*p), Lu=min(10,M*q), constant-clamp zero derivatives.
a=2^-20+2^-23*Cmax*T+2^-126; E=Lg*Bg+Lu*Bu+a <= old Bh. Inherited exact-zero
criterion forces H=[0,0],E=0; all other lanes preserve floor2^-32,cap2^32,
row sum2^40. One full-vector digest binds E and every subsequent check.
FR03 fixed 256-bit outward interval lattice, width<=2^-160, shared denominator
Q=D0^3*2^256,D0=2^94*(2^24-273), scaled E<620bits and down accumulators<=768bits.
Fail on width, lattice, metadata, shape, range, identity, resource or integer bound.

US2 (P1): run live guarded stages against a backend, retaining owned immutable buffers.
FR04 UNUSED->CLAIMED->PRE_ADMITTED->GU_CHECKED->H_CHECKED->DOWN_CHECKED->TERMINAL.
Claims are serial process-local mock/source attempts, not real capabilities or
persistent attempt ledgers. Duplicate attempt IDs/replays/reentry/reset refuse.
An exception after claim terminalizes and invokes owned cleanup; later dispatches
must be zero. Receipt chains bind source/build/checker/proof/contract/profile/attempt/reference,
previous receipt and all checked byte digests. No externally supplied receipt can
advance an owner. No production crash-durability claim.
FR05 gate/up dispatch then exact all-lane projection checks before activation;
activation returns immutable hidden and semantic clamp bits, checked against exact
clamps, local original-independent activation EPERR<=a and Eact, and original ideal
EPERR<=E and old Bh. EPERR is MAX endpoint error (alias of approved Q(v,H)), distinct from denominator Q, never interval distance.
FR06 actual SAME checked hidden bytes pass finite/zero-or-floor/magnitude/row-sum/
lattice/down-metadata checks BEFORE down dispatch. Local down uses candidate H;
ideal H/Y never do. Check local output <=gamma145*Phi(h), ideal <=R+sum|W|E;
retain old ceiling and all family/identity/resource/cleanup requirements.
FR07 budgets remain referenceRSS256MiB,workingdata512MiB,allocator64MiB,
nativeRSS1GiB,poll100ms,deadline900s. Owner checks monotonic elapsed/resource
samples at every boundary and before dispatch; mock fault samples test refusal.
A future native watchdog must enforce independent polling/census; no sampled
physical instantaneous global RAM guarantee. Math scratch is separately bounded.

US3 (P1): independently reviewed public CPU/mock evidence and local freeze.
FR08 A01..A12 in population.md must run with literal independent expectations,
including full 2048-lane corruption and actual dispatch counters. Two inherited
nonzero full-shape public positives retain original generators and independent
analytic domains. Preserve all41+363+32 source populations; execute only safe CPU
portions; explicitly mark all native controls NOT RUN.
FR09 exact fresh tools-disabled Opus5.5 preimplementation design/population review
and final source/build/test review ACCEPT/0, actual model/exit0/full descriptor,
current/quoted/committed hashes verified. Preserve every failed review.
FR10 additive local commit after checks/review, inventory, own-audit REPORT.md and
handoff.json. No push/merge. No real bytes, original-real R1, GPU/MLX/Metal numerical
execution, capabilities or ledger mutations. Real goal remains refused/unqualified.

Success: FR01..FR10 evidenced for source/CPU/mock implementation. Native physical
ownership, all41+363+32 native requalification, selected compiler premises and
any new real probe remain separate unfulfilled gates requiring explicit approval.

Checker identity binds numeric.py, source.py, owner.py and literals.py hashes;
proof identity binds approved theorem, uniform-certificate and exact-stage hashes.
Both enter the certificate and every linked receipt, with A08 mutations.
