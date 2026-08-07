# GLM-5.2 Limitations (sprint open)

## Active

1. **Disk admission failed** on M1 Ultra internal SSD (~346 GiB free after safe
   cleanup; need 500 GiB before download of ~222 GiB UD-IQ2_XXS).
2. **No GLM weights local** — no correctness or performance claims.
3. Architecture contract is **draft only**.

## Deferred by policy

- M2 Max testing
- External NVMe RAID
- Storing GLM on external drives

## Inherited from Qwen baseline

- Research path is not an optimized production serving stack.
- Architecture oracle ≠ llama fused bit-parity.
