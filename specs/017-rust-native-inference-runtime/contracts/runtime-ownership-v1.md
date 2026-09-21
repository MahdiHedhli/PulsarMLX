# Runtime Ownership and Residency Contract v1

## Slot lifecycle

`Created -> Leased -> Pinned -> Released -> Reused/Disposed`

## Ownership guarantees

- `Pinned` slots are stable for lease duration.
- Native registrations must outlive all dependent Metal command work.
- Deallocation without lifecycle completion is a hard failure.

## Residency categories

- `CompressedResident`: compressed bytes exist; decode deferred.
- `DecodedResident`: decoded buffer available.
- `Transient`: short-lived materialized data for immediate compute.

## Contract rules

- Address reuse is deterministic and observable.
- Residency admission includes headroom and policy class from authoritative budgets.
- Missing residency yields explicit `ResidentOrMissing` with no synthetic defaults.
