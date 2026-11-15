# Third-party license texts for PulsarMLX Console

This directory holds the full license texts that PulsarMLX Console must ship for donor and
third-party material under `console/`. The dashboard's About page is planned to serve
them. Attribution is summarized in the repository's [`NOTICE.md`](../../NOTICE.md), and
the donor review is in
[`docs/upstream/PROJECT_MAYA.md`](../../docs/upstream/PROJECT_MAYA.md).

## Files

| File | Covers |
| --- | --- |
| `project-maya-MIT.txt` | The full text of project-maya's `LICENSE` at commit `7e68a30f2f208056195352129188661fb6b94445`, copied verbatim, with both copyright lines (Peasant Smith and the Project Maya contributors; Niko1221 and the Strata contributors). It covers every file under `console/` that derives from project-maya: adapted dashboard files, Rust modules and tests translated from project-maya's server and tests, the fake engines and fake MCP server translated from its fakes, and the committed reference corpus captured from its server. Each such file carries a provenance header. |
| `llama.cpp-MIT.txt` | The MIT license of llama.cpp (Copyright (c) 2023-2026 The ggml authors), copied verbatim from `third_party/ggml/LICENSE` of project-maya at commit `7e68a30f2f208056195352129188661fb6b94445`, which names it as the license of its vendored llama.cpp reference. It covers the pre-tokenizer patterns that the donor transcribed from llama.cpp's `src/llama-vocab.cpp` and that PRM-04 carries in `console/crates/console-tokenizer/src/pretok/mod.rs`. |
| `README.md` | This index. |

The project-maya text was added with the donor qualification record, so that it was in
place before the first translated file arrived. Since 2026-11-14 the M1 packages commit
Rust tests and test doubles translated from the donor; each such file carries the
provenance comment that `docs/upstream/PROJECT_MAYA.md` prescribes.

## Rule

A component is never imported without its license text: the text is in this directory
no later than the change that imports the component. That change adds a row to the table
above and updates `NOTICE.md` where the component needs a notice there. The project-maya
text is already present, ahead of any donor-derived file, because it arrives with the
donor qualification record (ADR 0004).

The texts expected under this rule are:

| Component | License | Arrives with |
| --- | --- | --- |
| Preact 10.29.8, inside the vendored `preact.js` bundle | MIT | Work package WEB-01 (dashboard asset import) |
| htm 3.1.1, inside the same bundle | Apache License 2.0 (full text; project-maya ships only a notice) | WEB-01 |
| Lucide v1.50.0 icons in `sprite.svg` | ISC, with Feather-derived portions under MIT | WEB-01 |
| llama.cpp pre-tokenizer patterns, transcribed into `console-tokenizer` | MIT | PRM-04 (byte-level BPE tokenizer); present since PRM-04 as `llama.cpp-MIT.txt` |
| DeepSeek's reference prompt encoder, translated to Rust, and the five DeepSeek encoder fixture pairs | MIT, Copyright (c) 2023 DeepSeek | PRM-07 (DeepSeek encoder port), which commits the five fixture pairs together with DeepSeek's notice |

Of these texts, the llama.cpp one is present: `llama.cpp-MIT.txt` arrived with PRM-04. It
is the MIT text that project-maya names as the license of its vendored llama.cpp reference
(`ggml-org/llama.cpp` at `272aad8b984a4470d26f14bea8d958be68ac7c0c`), copied verbatim from
`third_party/ggml/LICENSE` of the pinned donor checkout. It covers the pre-tokenizer
patterns in `console/crates/console-tokenizer/src/pretok/mod.rs`, which the donor
transcribed from llama.cpp's `src/llama-vocab.cpp`. The others are not present yet. The lead
decided on 2026-11-14 that each third-party text is added in the same change that imports
its component, as the table shows; the plan the owner approved listed the Preact, htm and
Lucide texts among the M0 contents of this directory, and this timing was reported to the
owner at checkpoint 1 on 2026-11-14, whose reply raised no objection.

Some donor material has no license text here because it is excluded and never
committed: the Outfit font (OFL-1.1), the vendor logo files, project-maya's app icons, and
model vendors' chat templates, which are loaded from the model directory at run time and
remain under their vendors' licenses. If any of these is ever imported, its license text
comes with it under the rule above.

## Conventions

- File names take the form `<component>-<license identifier>.txt`, as in
  `project-maya-MIT.txt`.
- Texts are copied verbatim from the component's own license file at the imported
  version. They are never reflowed or edited.
- Only plain-text files belong here. No binary file is committed.
