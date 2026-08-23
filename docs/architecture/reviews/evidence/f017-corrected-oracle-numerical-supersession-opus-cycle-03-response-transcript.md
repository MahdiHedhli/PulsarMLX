# F017 corrected-oracle numerical-authority supersession — Opus cycle 3 response

Opus reviewed exact committed bytes at `80f44b458824903f5dca101bc8f1d590f6845422` in clean detached worktrees.

It verified exact primary and secondary import allowlists, 41 import/dynamic/builtins escape mutations, 38 target-function census mutations, 47 contract/evidence binding mutations, thirteen provenance mutations, target geometry probes, all ten tombstones, and two byte-identical complete requalification regenerations. It also measured all 222 `.gguf` opens during qualification as ephemeral synthetic shard paths, with zero opens under the user home and both production checkpoint environment variables absent.

One `NON_BLOCKING_REQUIRED` finding remained:

`F5-R2`: the secondary pure-core allowlist necessarily permits `numpy` and `mlx`, but no exact attribute policy prevented `np.load`, `np.fromfile`, `np.memmap`, `np.save`, `numpy.lib.format.open_memmap`, or `mx.load`.

Two defense-in-depth observations concerned dangerous builtin aliasing and lambda-shaped target arithmetic.

No finding required formula, threshold, checkpoint, or independence changes. Safety was confirmed: Event 04 authorization absent; Event 04 unexecuted; real executions zero; original checkpoint access zero; P1 attempt 2 absent; historical ledger 175.

`REJECT`
