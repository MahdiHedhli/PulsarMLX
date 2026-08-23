# F017 corrected-oracle numerical-authority supersession — Opus cycle 4 response

Opus reviewed exact committed bytes at `d85ddbf50989b370dffa2277941a15750cfddf70` in clean detached worktrees.

It reverified 49 exact binding mutations, both historical provenance audits, full-CI execution, target geometry, all ten tombstones, two byte-identical complete requalifications, measured synthetic-only shard opens, primary/secondary independence, minimal numerical-module attributes, and unchanged ledger/state.

Three `NON_BLOCKING_REQUIRED` findings remained:

- `F5-R3`: numerical-module attribute policy was tied to literal aliases `np` and `mx`, permitting alternate import spellings and from-import forms.
- `D1-R1`: builtin alias taint missed tuple/list/dict/default/walrus/loop binding forms and meta-loader globals.
- `D2-R1`: assigned graph-name collection skipped class bodies and class-attribute lambdas.

Two defense-in-depth observations concerned binding the validator/qualifier themselves and unconstrained method calls on injected objects.

No finding required a numerical formula, threshold, original-checkpoint, or independence change. Safety confirmed: Event 04 authorization absent; Event 04 unexecuted; real executions zero; original checkpoint access zero; P1 attempt 2 absent; historical ledger 175.

`REJECT`
