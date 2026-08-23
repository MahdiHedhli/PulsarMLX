# F017 corrected-oracle numerical-authority supersession — Opus cycle 5 response

Opus reviewed exact committed bytes at `efe2ae4908dd5e04c948ded37326bc95c40b119c` in clean detached worktrees and reconstructed cycles 1–4.

It verified exact import AST multisets (20/20 mutations), dangerous builtin/meta-loader rejection (68/68), recursive assigned-surface collection (24/24), validator/qualifier self-binding (13/13), all prior binding/provenance/retirement/geometry controls, nine committed tests, and byte-identical complete requalification `b25aaec9fc60fc209715fcbc84eae63ffd05caac01a4ace77f90407124619ad4`.

One `NON_BLOCKING_REQUIRED` finding remained:

`F5-R4`: the numerical-module attribute policy is name-bound rather than value-bound. Although exact imports require aliases `np` and `mx`, an in-file assignment such as `_backend = np` followed by `_backend.memmap(...)` evades the attribute-root policy. Opus demonstrated this passing policy validation, contract regeneration, complete requalification, the full validator, and all committed mutation tests. The committed cores contain no such rebinding and original checkpoint access remained zero, but the future-edit control is not fail-closed.

Two defense-in-depth observations concerned additional assignment-binding shapes and unconstrained method calls on injected objects.

No finding required formula, threshold, original-checkpoint, provenance, or independence changes. Safety confirmed: Event 04 authorization absent; Event 04 unexecuted; real oracle executions zero; original checkpoint access zero; P1 attempt 2 absent; historical ledger 175.

`REJECT`
