# Prospective decisions

- Choose x=(2+ThueMorse)/4096: F32 exactly representable, row L1=2,
  group L1=sum=1/32; each bias perturbation delta produces delta/32 in its
  projection row. Simultaneous adversarial errors can cancel; no single vector
  establishes arbitrary error detection. Bias omission and gate/up swap require
  separately specified synthetic witnesses. Unknown real signals are not proof.
- Retain nonlinear Taylor/rational interval method, but use streamed packed
  rows and integer dyadic accumulators. No dense full-shape Fraction matrices.
- For M1,N2048/K4096 and N4096/K2048, pinned vector_family selects qmv_fast;
  four-bit exponents K/16+17 are 273 and 145. Gamma unchanged. Old M1 shortcut
  K/4+5 is not the exact selected family definition and is not reused.
- New full-shape positives use concrete row formulas in population-v2.md;
  independently establish their admissibility without MLX observations.
- Memory caps are prospective: 256MiB reference process RSS; 512MiB aggregate
  working data including owned host/native buffers; native runtime overhead
  separately measured and bounded at 1GiB process RSS above tracked data.
  Owned buffer admissions, a source-derived native allocation ledger, allocator
  peak checks and a supervisor RSS watchdog are required before acceptance. Sampling alone is not a hard global instantaneous memory bound;
  reports must distinguish allocator/owned caps from observed RSS and polling
  overshoot. If an enforceable claim is unavailable, refuse that claim/run.

Full-lane admission is a structural requirement: each of 2048 nonzero ideal
hidden lanes must exceed 2^-32+Bh in magnitude, and Bh is at least1/128.
A single lane violating this requirement terminally refuses this fixed probe.
The formula establishes bias observability, not the likelihood of real admission;
without real magnitudes we do not assign a refusal probability. Refusal never
permits input/tolerance retuning or substitution of a submatrix as completion.

Resource source inspection: pinned native/include/mlx/memory.h lines36-40
explicitly describes set_memory_limit as a guideline, with allocation exceptions
only when memory (including swap) is exhausted. It is not a hard cap and must
never be reported as one. T009 remains open: establish the concrete fixed graph
allocation ledger and independently review its bound, then measure allocator
peaks and process peak RSS, with fail-closed qualification on excess. A polling
watchdog alone cannot prove an instantaneous global memory maximum. No native
resource-compliance claim or execution capability exists yet.
