# R001 Checkpoint-Free Complete-Scope Plan Qualification

## Authority and scope

- Feature: F017
- Machine: MacBook Pro M2 Max, arm64
- Starting R001 commit: `8c3e340c137f299be66c74be0b798a8b0c731d07`
- Starting R001 tree: `70828fd62bd97bca8eb97ca0b1c07954651685d9`
- D5R1 policy: `f017-m2-d5r1-bounded-checkpoint-free-repack-repair-v1`
- Policy SHA-256: `b2a00e4f895339c6ddf63e9c6624e0b3dfc7bdbc76d2a70ca534126227a575eb`

This qualification uses only synthetic in-memory inventory, admission, scope,
component, and shard descriptors. It does not resolve or open a checkpoint,
copy payload bytes, publish bundles, run inference, or execute Event 05 or 06.

## Production repair

`build_plans` now validates the complete component-role census before creating
any partial object plan. Each selected object must contain exactly one `gate`,
one `up`, and one `down` component. Unknown and duplicate roles fail with a
deterministic contextual error. Valid plans retain `gate`, `up`, `down` order.

## Complete synthetic domain

- Layers: 3 through 78
- Routed experts per layer: 256
- Shared experts per layer: 1
- Object plans: 19,532
- Components: 58,596
- Component order: `gate`, `up`, `down`
- Object order: layer ascending, routed before shared, expert ascending
- Synthetic quantization geometry: whole IQ2_XXS blocks
- Source ranges: checked, bounded, non-overlapping, and single-shard per object
- Plan generation: filesystem-free
- Two independently constructed and reordered inputs: byte-identical canonical plans
- Plan identity: `350ee7d581b425658f800c96cc877abdebd56e945a560d615ddfb38091b8f75a`

## Fail-closed cases

The production planner rejects duplicate gate, up, and down roles; an unknown
role; each missing required role; duplicate object keys; source arithmetic
overflow; bundle arithmetic/alignment overflow; source ranges beyond a shard;
stale or mutated plan identity; and unsafe relative paths. Existing symlink and
partial-nonce guards remain covered by the baseline suite.

## Validation disposition

- Baseline 42 Ultracode: 250 tests passed with Ruff and strict mypy green.
- Baseline R001 repack library: 7 tests passed.
- Rust validation: all baseline and new exact-role, complete-scope, and adversarial tests passed.
- Clippy: no new Sequence 10 warning; the known unused `checked_mul` library warning remains unchanged.
- Format: no bulk formatter was run because baseline formatting proposes unrelated production drift.
- Python verifier contract: executed without a source or checkpoint alias.
- Privacy scan: public-safe evidence only.

## Claim boundary

This evidence qualifies only the minimal duplicate-role repair and the
checkpoint-free complete-scope planning boundary. It is not permission for a
full-store repack, checkpoint access, inference integration, merge, release,
placement, caching, replication, or F017 closeout.
