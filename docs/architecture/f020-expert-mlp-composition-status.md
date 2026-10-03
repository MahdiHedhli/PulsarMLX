# F020 complete synthetic expert MLP: Studio qualification

The bounded packed gate → accepted activation → packed down composition passed on
the Mac Studio. This qualifies the frozen synthetic population and refusal/control
behavior. It does not qualify a real GLM payload, full-model execution, fusion, or
performance. Host copies and materializations remain explicitly counted.

The qualified implementation is commit
`2f0c4a3c5c1a44ba5be3068cb6032bf28329008d`, tree
`53cc79cbce807dee6f43b4d18b017197e7ea3e31`, package SHA-256
`c59f4d6f7662ea3c2549f80a99b621557b9c0b0547f5661f05d30ebcfaa45aee`.
The reviewed release binary SHA-256 is
`2a699731ed22a85987ef8410ed8019da445d5f4086169ca9cf8c99d9f5207527`.
The independent source/numerical review of this exact revision returned ACCEPT
with zero blocking findings before its first candidate execution. The actual
review model was `claude-opus-5-5`. The three nonblocking notes concern binary
build behavior, additional mock failure coverage, and early device/stream ordering;
the sanitized receipt records those limits.

## Frozen method and population

The accepted activation contract and its budgets remain unchanged:
`E_act = 1/128`, `beta_B = 5201/4194304`. Gate/up/down are selected as one
same-checkpoint, same-expert tuple with exact roles, packed shapes and resolved
default/override recipes. Candidate weights stay packed. The independent R1 starts
from the original fixture input and exact decoded packed weights; candidate hidden
values supply only the separately checked local down projection and admission.

All 48 positive cases passed, across `D,H ∈ {64,128}`, `M ∈ {1,32}`, three
experts and default/mixed recipes. Five refusal cases passed, the explicit injected
down-floor guard control passed, and all ten mutations were detected by their
frozen semantic predicates. The injected guard case demonstrates guard behavior;
it is not an end-to-end tiny-product positive case. The lower-gate-clamp witness is
also a separate stage control. No domain or budget was relaxed after observations.

The evidence exporter replayed all numerical decisions and all control predicates,
checking both raw and verified report custody. Its 380,160 exact stage comparisons
passed. Worst distance-to-budget display ratios were:

| Stage | Worst ratio |
| --- | ---: |
| Gate | 0 |
| Up | 0 |
| Hidden | 0.0007728830378018559 |
| Down local | 0.06728977428164273 |
| Complete output | 0.000570354304338598 |

These ratios summarize the unchanged exact gates; they do not create a new
tolerance. The JSON summary preserves exact distances, budgets and ratios.

The inherited 363-case primitive suite and 32-case expert-plane suite passed on
both baseline `2d388856593b96a136fa5a6036c0e973919cedff` and the qualified
composition commit. The raw primitive reports were byte-identical (SHA-256
`78742989517a1513421612ba430b2a2dda54b489c8a4299b0a20a879b8eb5499`), as
were the raw plane reports (SHA-256
`5c91ae99d57d361f9fb0ffd935028a5b92c47f2877aa1d3f4a82cc87f454d30a`).
Inherited source, fixture and interface files were unchanged.

Host validation passed five tuple tests, nine independent reference/admission
tests and one ownership test covering five modes and five partial-result failure
cases. The host mock has no numerical authority and is not linked to MLX.
The Studio release build passed. Workspace check and host test receipts are
included separately. The new CI step performs static/host validation; the complete
synthetic GPU qualification recorded here was admitted on the Studio.

## Evidence and publication state

Sanitized evidence is in
[`specs/020-mlx-safetensors-affine/qualification/expert-mlp-composition-studio-summary-v1.json`](../../specs/020-mlx-safetensors-affine/qualification/expert-mlp-composition-studio-summary-v1.json),
with review, source freeze, regression and host-check receipts beside it. Raw
reports, exact review capsule and CLI response, failed attempt and successful
attempt are retained in the private Studio handoff audit. The previous revision's
first attempt failed during activation setup after two gate/up projection outputs;
it accepted no activation or down output. The revision-4 handle-slot and cleanup
repair was independently reviewed before the successful second attempt. The zero
observation claim applies only to revision 4 before that review.

This evidence commit adds documentation and receipts to the qualified source.
It does not change the frozen package. Feature-branch publication and required
remote CI are pending explicit push authorization; the local result is not a CI
success or a main-branch integration. Main remains at the accepted baseline.

## Next real-payload gate

Before real execution, perform a read-only header/config census and bind the
actual GLM gate/up/down expert roles, recipes, shapes and byte ranges. Separately
qualify bounded expert-only range backing and its lifetime. The current synthetic
`Source::open` hashes and loads the whole checkpoint, so it must not be used to
open the approximately 182 GB real payload as the next experiment.

Then demonstrate the actual intermediate input domains and the unchanged down
admission floor for one bounded expert case, or independently review a necessary
domain extension before candidate execution. No whole-model scan, giant weight
copy/download, generation run or performance claim is authorized by this result.
The existing Studio model remains in place. The M2 source work and unrelated
Qwen track remain preserved.
