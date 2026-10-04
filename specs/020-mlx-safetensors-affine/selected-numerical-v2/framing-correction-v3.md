# Strict original capture framing correction, contract v3

Source33b6e450/review03 release passed full39 synthetic and363/32 inherited
regressions plus requiredCI37181187966. Its first real attempt was refused in
strict header parsing: the accepted capture writer emits a top-level `scope`
field that both new readers and their synthetic headers incorrectly omitted.
The reader consumed3612 framing bytes and zero packed payload bytes, deduced
from its failure point and fixed file/payload sizes. No real affine/activation
R1 or native observation occurred. Preserve that failed receipt and consumed
ledger; do not retry under that commit/contract. The other manifest predicates
match the preserved capture metadata in a metadata-only diagnostic.

V3 requires exactly schema/owned/payload_lengths/scope, with the existing writer
scope literal `selected packed content only; no numerical qualification`.
Unknown, missing and wrong scope fields refuse before payload access. Include
the original capture writer in the independent source review. Add missing-scope
and wrong-scope full-shape host refusals: population2+26+13=41; native work
remains9QMM/75497472MAC and12activation/24576lanes. Add an actual writer-to-reader
host compatibility regression using only small generated synthetic tensors.
Preserve numerical contractv2; new selected-numerical-v3.json changes framing
and refusal inventory only. Input remains v2 and hash746ed37cdd4a6a1792ec512ada02f9a2bd2cfa9c5a88d2eae2758ccbd9b2d799.
All numerical formulas, budgets, domains, original-byte provenance, positive
payload bytes and resource limits remain unchanged. No retuning or rescue.

Sequential gates: requirements/contract/analysis update; strict source and
synthetic fixture repair; host tests; release source/build freeze; independent
exact ACCEPT/0; full41+363/32 qualification; reviewed validated push and exact
requiredCI success; then new exact-version ledger and original-byte real R1.
All prior observations must be disclosed by version; zero pre-review means
zero observations under the new exact version, not erasure of prior attempts.
