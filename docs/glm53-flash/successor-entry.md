# Current tiny successor entry

`scripts/research/glm53_flash/router_caller/successor.py` is the explicit-root successor to the historical [router contract](router-caller-v1/contract.md). The historical `rc_guard.py` and `runner.py` retain their original bytes and stale phase/source pin. This command does not import, replace, repin or claim qualification of that historical guard.

Provide a deliberately bound workspace, an already admitted tiny CPython/MLX environment, the frozen router fixtures and eight retained upstream source/config/license/capsule files. No installation, download, model construction or inference command is provided. The observed platform is macOS on Apple Silicon with the existing Homebrew CPython 3.14 environment; the OS fence is not a portable Linux implementation.

The environment identity directory contains the independently admitted `environment-manifest.json` and `wheel-lock.json`. The upstream directory contains `config.json`, `capsules/{Glm5NextMoEGate,MoEGate,group_expert_select}.py`, both upstream license files, and the two original source paths enumerated by `successor_guard.UPSTREAM_FILES`. Preserve their exact prior identities. Manifest generation checks the materialized inputs; it does not authenticate an arbitrary replacement environment on the operator's behalf.

Using caller-defined absolute paths, construct the manifest separately from source commits:

```sh
"$FLASH_PYTHON" -I -B "$FLASH_SOURCE/scripts/research/glm53_flash/router_caller/successor.py" manifest \
  --source "$FLASH_SOURCE" --environment "$FLASH_ENVIRONMENT" \
  --fixtures "$FLASH_FIXTURES" --upstream "$FLASH_UPSTREAM" \
  --environment-identity "$FLASH_ENV_IDENTITY" --output "$FLASH_MANIFEST"
```

Record the printed manifest SHA-256 as `FLASH_MANIFEST_SHA`. Use those same explicit input arguments for `doctor`, `case` or `matrix`, adding `--manifest "$FLASH_MANIFEST" --manifest-sha "$FLASH_MANIFEST_SHA" --backend cpu` (or `metal`) and a fresh `--output` directory. Every case/matrix invocation first executes the source-free doctor controls and repeats capability denials in the numerical child. The parent establishes the read/write/network/fork fence before approved-library startup and mathematical definition execution. The separate permitted-fork control always refuses admission after exact cleanup; it cannot authorize a numerical run. Captures are limited to 16 MiB, direct child RSS to 1 GiB, runtime to 180 seconds and cleanup to 30 seconds. An unresolved stop leaves a latch in the output parent and blocks later numerical commands there.

The parent supervisor runs outside the child fence so it can observe, terminate and reap its children. A denied process-group observation is an unresolved stop, never a successful cleanup. Its failure receipt and latch preserve that distinction. Supervisor regressions execute at this parent boundary; they do not require weakening the numerical child's permissions.

The successor composes the unchanged `rc_source`, `rc_runtime`, `rc_oracle` and `rc_checks` definitions into explicit namespaces. It omits only the enumerated historical dependency imports, injects the verified context, and preserves the logical exception names required by the frozen controls. It reuses the exact numerical test classes with a new explicit-root fixture setup. These are declared successor seams, not ordinary imports of the historical runner. Whole upstream modules stay unimported.

A successful command records real prefix/request/checkpoint, stdout/stderr, stop, doctor and producer receipts, packs their exact source members, and performs a fresh readback. `archive-verify` exposes the same nonexecuting reader: use the explicit input arguments and manifest above, a fresh output directory, and `--archive "$FLASH_ARCHIVE" --archive-sha "$FLASH_ARCHIVE_SHA"`. It hashes executable inputs as data; it does not execute archived source or import a numerical backend. A failed/incomplete producer cannot be packed as success.

Only the three declared prefix path operands may be replaced by explicit role strings. Original and portable digests remain distinct; protected prefix fields have a separate commitment. Invalid UTF-8, duplicate JSON keys, oversized bodies, extra/malformed parts and unhandled private locators fail closed. This remains a scoped locator policy, not universal secret detection. The portable archive is evidence, not a standalone environment installation.

The finish line is runnable **tiny integration** with exact same-device CPU/Metal observations, separate fresh-root confirmations, real archive composition, focused refusal tests, independent source review and ordinary exact-head CI. Results and eventual commit bindings are recorded separately from the noncircular source manifest. Historical CI skips remain historical; the focused successor tests do not skip themselves. The earlier [publication correspondence table](publication-status.md#measured-file-correspondence) describes its original checkpoint, not current successor bodies.

Limits remain: BF16 operands widen to FP32; this is not native BF16 model parity. E288 selection remains bias-dominated. The two individual-cast omission controls remain nondiscriminating. Negative grouped-mask coverage and cold driver-cache qualification remain open. No full-model, quantized, cross-hardware, F017, main-merge or shared-method acceptance follows. This doctor can be nominated for later shared-method review; this change does not ratify a global skill.

The new [finite router discrimination operation](router-discrimination.md) adds prospectively declared controls and an explicitly tagged 36-file archive layout. Its finite-domain results do not retroactively change the scope of the earlier router matrix or its historical limitations.
