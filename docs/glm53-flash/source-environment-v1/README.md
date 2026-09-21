# Source-bound MLX research slice

This addition executes a byte-exact extracted upstream expert selector, tiny real MLX Conv1d operators with explicit research state wrappers, and bounded Jinja template cases. Overall source qualification is PARTIAL. It does not load a GLM model, tokenizer, checkpoint or safetensors header. Full upstream selector-module import and GLM Conv1d construction/sanitize/cache paths are unexecuted. Every MLX claim is wheel-observed; source correspondence is RELEASE_DECLARED_NOT_BUILD_VERIFIED.

The selected artifact configuration has 288 experts, top-k 8, n_group=topk_group=1, normalized sigmoid scores, and scale 2.5. The configured test allocates only scores. Other grouping tests are generic-function evidence. The zero-mask diagnostic demonstrates a generic group-exclusion discrepancy with negative corrected scores; it cannot establish the intended exclusion property. Raw argpartition order is recorded without an ordering guarantee.

Text and string-argument tool-call-shaped template fixtures render in standard Jinja's sandbox. Tool declarations remain NOT_QUALIFIED because the pinned template requires tojson(ensure_ascii=False), which the standard filter does not support. No custom adapter is enabled. Rendering does not establish tokenization, media processing, tool execution or model behavior.

Run only on the already-bound external workspace using its independently admitted environment and retained exact metadata/source files. Supply the existing phase role as FLASH_PHASE; this command never installs or downloads anything:

```sh
python3 -I -B scripts/research/glm53_flash/source_environment/runner.py \
  --phase "$FLASH_PHASE" --run-name unique-boundaries-cpu --mode boundaries --backend cpu
```

Use a new run name and `--backend metal` for the Metal boundary. Use `--mode template --backend cpu` for the separate template child. Ambient test collection explicitly skips before importing MLX and is NOT_EXECUTED evidence. Reconstructing the source patch alone does not reconstruct the external environment; the private packet binds the official wheel lock, installation file manifest, source hashes and retained-role custody. No model paths are scanned.

New code and fixtures are MIT under the repository license. The byte-exact selector and MLX source excerpts carry the accompanying mlx-vlm and MLX MIT notices. PipeNetwork equations/call-path descriptions are attributed to its Apache-2.0 runtime without vendoring its implementation publicly. Upstream Pulsar maintainers do not maintain or endorse this independent work. Python is the reference harness, not a change to the project's native runtime strategy.

The supervisor caps tiny children at 120 seconds, sampled 2GiB RSS and supported 512MiB MLX memory/16MiB cache limits. Template capture is bounded by ten seconds and 16MiB. These are misuse/drift controls, not a hermetic or cross-user security boundary. The external volume remains unencrypted with ownership ignored (FLSH-PROTECTION-01 OPEN); no permissions or encryption are changed. Driver and supported OS credential storage remain OS-managed.

Criteria and original fixture bytes are frozen. A later static review added rejection of out-of-domain logits beyond 1000 and bias beyond 16 before FP32 conversion, closing finite-binary64-to-infinite-FP32 admission; no tolerance was relaxed. Finite normalization-underflow output is explicitly rejected after real evaluation. Changes, prior generations, raw output, deliberate mutant failures and fresh-process receipts are retained privately. Shared method acceptance and any next phase remain with the parent planner. No public push is authorized.

Independent review rejected the original missing-binding control. The corrected generation uses a real missing namespace and an eighth unexpected-global mutation; see review-repair-01.md. Normalization-off branch discrimination with top_k>1 and kernel-width-one behavior remain NOT_QUALIFIED.
