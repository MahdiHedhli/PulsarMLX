# Bounded real affine row review packet

**Status:** Frozen local source snapshot for independent review. No packet has
been sent externally, and the real-checkpoint command below has **not** been
run. The earlier denied Claude review route is unchanged; this packet does
not authorize a retry or another provider. No commit or publication is made.

## Exact source snapshot and evidence

The working branch is `research/qwen38-strata-pager-m2-20261003` at base HEAD
`d2d77047cef93095a251cf1378f4ec16b2fc4c6d`. It has uncommitted Qwen work;
the hashes below, rather than HEAD alone, identify this candidate. The exact
proposed reviewer payload is these **five project-owned text files**, totaling
**58,064 bytes**. Send no checkpoint file, weight bytes, tokenizer, receipt,
environment file, credential, or unrelated source.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `scripts/research/qwen38_affine_slice_review.py` | 8,886 | `01735b1b68eef398a89f9ab2be6c886f0ce12be2ce0bcd0488b7bbdb0bbd6105` |
| `scripts/research/tests/test_qwen38_affine_slice_review.py` | 5,911 | `5aec75dbcfcee3babf305c19765441b459fa34305b64f3300188c95be45e1dd8` |
| `scripts/research/qwen38_page_catalog.py` | 19,756 | `655212185ae3d55be521a1a24746041e426881980def327392a136b2df96c65f` |
| `scripts/research/qwen38_verified_files.py` | 11,210 | `c915f2038230c9ccf35636eb2f2f6e023928960bdb853bcae89cdaf1e51b41a5` |
| `scripts/research/admit_qwen38_static.py` | 12,301 | `f2488734a30c66dc8023f5f8d7d7eca4e36f39de6c9eaaa714a6e57cc36f400e` |

The project-owned [pinned manifest](checkpoint-manifest.json) has SHA-256
`afe5b9b7ec19375c6815eceed6a1607212463c5c6525c6fdd67385db30e6f06f`
and pins upstream revision `b2c422f3c643e36f04227a64d61796b44a4b1029`.
The [durable checkpoint evidence](evidence/checkpoint-dataless-header-diagnosis-2026-10-16.md)
records a strict local bound pass on all 25 files, 106,218,444,193 bytes and
3,215 headers at the non-File-Provider `~/Models/PulsarMLX` root. That completed
pass is historical evidence; the proposed operation repeats live bound
admission and holds its descriptors through both row reads. The original
Documents copy remains dataless and is excluded.

## Frozen proposed operation

After this exact packet has independent source review and the separate
numerical-execution authorization required by the
[production adapter gate](production-adapter-next-gate.md), a resolved hashed
MLX environment would run the single explicit `--checkpoint` command in
`qwen38_affine_slice_review.py` against the durable local root. This is a CPU
affine primitive comparison, not the model graph, inference, a GPU fence test,
or a throughput benchmark. The script does not import checkpoint Python.

The two exact header-pinned rows are:

| Case | Tensor prefix | Source | Pinned weight / partner shape | Quantization |
| --- | --- | --- | --- | --- |
| Routed expert 0, inner row 0 | `language_model.model.layers.2.mlp.switch_mlp.gate_proj` | recovered `model-00006.safetensors` | `[512,640,320]` / `[512,640,40]` | 4-bit, group 64 |
| Text row 0 | `language_model.model.layers.0.linear_attn.in_proj_qkv` | resident `model-00001.safetensors` | `[10240,640]` / `[10240,40]` | 8-bit, group 64 |

For each case, the script reads one packed U32 row and one BF16 scales/biases
row through `VerifiedFiles.readinto` on the live `BoundCheckpoint`. The three
spans must match their pinned filenames, dtypes, shapes and affine group
equation. `readinto` checks root and file identity and authenticates every
touched 1 MiB chunk before copying bytes. Its identity checks run before and
after each chunk. The selected raw tensor payload is exactly **4,160 bytes**
(1,440 + 2,720). Six selected spans can induce at most **12 authenticated
1 MiB chunk reads**, including repeated chunks. Strict bound admission first
rehashes the **entire 106,218,444,193-byte checkpoint** as its existing
integrity prerequisite; that work is not counted as the 4,160-byte slice.

The scalar reference converts BF16 bit patterns to finite float32 values,
extracts each 4- or 8-bit code with integer shift/mask in little-endian U32
words, then evaluates `scale[group] * code + bias[group]`. The candidate
backend calls MLX CPU `dequantize` with explicit `bits`, `group_size=64`,
`mode="affine"` and float32 output. It compares **all 2,560 values in each
case** elementwise using `abs(actual-reference) <= 1e-5 +
1e-5*abs(reference)`. Wrong shape/count, nonfinite values, changed identity,
digest mismatch, any element failure or resource stop fails the entire probe.
The tolerances and cases are frozen before observing real numerical output;
do not retune them after a failure. Only counts, error maxima and pass status
are printed, with no weight or decoded-value dump.

The selected payload totals 4,160 bytes; converting each bounded `bytearray`
to retained `bytes` can temporarily hold up to 8,320 logical raw-buffer bytes.
Each case produces exactly 2,560 float32 values, with additional Python and
MLX object overhead accounted for by the process-level check. The code checks
macOS peak RSS against **512 MiB**
before admission, after file reads, after each comparison and at exit. Peak
RSS is an observed stop, not a hard OS reservation; reviewers should assess
this limit and the small MLX allocation path before execution. The proposal
does not change the existing 48/40/8/16 GiB future full-runtime gates.

## Generated-only validation and reviewer questions

`python3 -B -m unittest discover -s scripts/research/tests -p
'test_qwen38_affine_slice_review.py' -v` passed **7 tests** on generated data.
They cover both packed widths and group boundaries, pinned row geometry,
size/filename rejection, elementwise failure, BF16 validation, peak-RSS
rejection, and a tiny `VerifiedFiles` read that rejects an on-disk mutation.
They do not import MLX or open any checkpoint payload. Prior
[CPU affine fixture evidence](evidence/affine-probe-macbook-2026-10-15.md)
covered generated 4-bit/group-32 and 8-bit/group-64 arrays; it is not a
4-bit/group-64 real-checkpoint or full-model result.

Review the exact source for: selected-row offset and endian arithmetic;
whether MLX CPU `dequantize` accepts these shapes and BF16 partners in the
resolved pinned environment; live descriptor/file-identity behavior;
read/allocation and 512 MiB RSS bounds; independence of the scalar oracle;
the frozen tolerance; and any accidental payload or model execution path.
Return concrete file/line findings and the smallest correction. If the
environment, source, or memory boundary is not ready, reject execution.

**Remaining boundary:** independent review of this exact five-file snapshot,
then the separate approved numerical execution gate. Source preparation and
generated tests provide no real tensor numerical evidence and no complete
model correctness claim.
