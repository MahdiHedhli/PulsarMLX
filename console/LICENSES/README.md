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
| `README.md` | This index. |

As of 2026-11-14 no donor-derived file has been committed yet. The project-maya text is
added with the donor qualification record, so that it is in place before the first adapted
or translated file arrives.

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
| llama.cpp pre-tokenizer patterns, transcribed into `console-tokenizer` | MIT | PRM-04 (byte-level BPE tokenizer) |
| DeepSeek's reference prompt encoder, translated to Rust, and the five DeepSeek encoder fixture pairs | MIT, Copyright (c) 2023 DeepSeek | PRM-07 (DeepSeek encoder port), which commits the five fixture pairs together with DeepSeek's notice |

None of these texts is present yet: M0 ships the project-maya MIT text only. The lead
decided on 2026-11-14 that each third-party text is added in the same change that imports
its component, as the table shows; the plan the owner approved listed the Preact, htm and
Lucide texts among the M0 contents of this directory, and the owner is informed of this
timing at checkpoint 1.

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
