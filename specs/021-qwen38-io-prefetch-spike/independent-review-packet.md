# Qwen3.8 pager independent source review packet

Status: prepared locally; no source has been sent to an external reviewer. The earlier Claude Opus attempts were rejected by automatic approval review. Send only after Mahdi explicitly authorizes this exact disclosure.

## Frozen review input

Use commit `11a4246464fd55f5ce95f287fdee598a1d6a707d` on `research/qwen38-strata-pager-m2-20261003`. The proposed payload is exactly the following 11 project-owned text files, totaling 94,785 bytes. The SHA-256 values bind the contents to that commit.

| File | SHA-256 |
| --- | --- |
| `scripts/research/admit_qwen38_static.py` | `e41f9c4d401e8a8ea348c7694d2027f54cae1298eb83aa6ea54a098d160ebfd8` |
| `scripts/research/qwen38_page_catalog.py` | `ef4d22ea362d6dbe2647d87e7b3a975a507944f7d51c28ac32818826f9fdba9f` |
| `scripts/research/qwen38_bounded_pager.py` | `1e124839f2c89cb37b90bf945b5594dae281a88290bad8ba170f2d23e796b90c` |
| `scripts/research/qwen38_fixture_io.py` | `b1793b0bcf07de0bd8533df573ab1f734cafd2725d469dbb3e1c62744b7935f8` |
| `scripts/research/qwen38_prefetch_trace_contract.py` | `919a59de98add77798ebb65ef8387ac72f74e657f2341b3db6dd48a296b40eb7` |
| `scripts/research/tests/test_qwen38_bounded_pager.py` | `ee2c49f5a3e6eba8173788579e32880792aab448ad59dc388bc0593fd47dbd60` |
| `scripts/research/tests/test_qwen38_fixture_io.py` | `b641891e8cb1fbc7183a8fa116dff8495a294abdd1ccd3a8a9b36f32fff32d3c` |
| `scripts/research/tests/test_qwen38_prefetch_trace_contract.py` | `d003613fd558b2e729968a98e206b988ce11b9a553df7baf5025d469da56ae37` |
| `specs/021-qwen38-io-prefetch-spike/spec.md` | `f4255d4cc3b2374b77b4b22c723414af380892e0d6d44d9e5bf1d402e33babd2` |
| `specs/021-qwen38-io-prefetch-spike/plan.md` | `deb1d7ec28b9c70d0874c77ee660aed5022ad926232a2196bff86a023852478d` |
| `specs/021-qwen38-io-prefetch-spike/trace-contract.md` | `ad2ef2a57391b9b15988b1c1759e697bc3fb4df4fb8c225370d549895612f173` |

The payload excludes checkpoint weights, the bundled `qwen4_exp.py`, tokenizer files, manifests, receipts, static-admission evidence, local environment files, and host data. A narrow key-pattern scan found no obvious credentials in the selected files; this is not a guarantee that the files contain no sensitive information.

## Review questions

1. Identify concrete violations of the synthetic pager's demand authority, admission bounds, eviction, cancellation, I/O completion, and GPU lease rules. Include cross-request reuse and late completion cases.
2. Check the header-derived expert and PLE span arithmetic, file identity assumptions, and fail-closed behavior. Distinguish a catalog bug from a limitation of the earlier acquisition receipt.
3. Examine the fixture adapter's actual host buffer ownership, exported `memoryview` lifetime, file-change checks, and failure cleanup. State explicitly where its byte counters can diverge from process memory.
4. Check whether the trace validator can accept a sequence that contradicts scheduler priority, buffer lifetime, route authority, or useful/late/wasted byte accounting.
5. Return ranked findings with file and line references, a reproducible trigger, and a suggested smallest correction. State which claims remain unproven without real checkpoint I/O, MLX fences, a macOS memory sampler, and numerical parity.

This is source review only. Do not execute code or suggest that synthetic tests qualify full-model loading. The local command `python3 -B -m unittest discover -s scripts/research/tests -p 'test_qwen38_*.py' -v` passed 43 focused tests at the frozen commit.
