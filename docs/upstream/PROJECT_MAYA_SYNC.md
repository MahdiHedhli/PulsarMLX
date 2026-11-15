# project-maya sync log

| Date | Action | Revision | Result |
| --- | --- | --- | --- |
| 2026-11-14 | Initial source and license review | `7e68a30f2f208056195352129188661fb6b94445` (version 1.1.63) | Approved as the donor for adaptation and reimplementation of `serve/` and `serve/web/`; engines, launcher and branding excluded. See [PROJECT_MAYA.md](PROJECT_MAYA.md). |

## Pin

- Repository: <https://github.com/mw00/project-maya>
- Commit: `7e68a30f2f208056195352129188661fb6b94445`, dated 2026-11-14 17:32:50 UTC
- Version: 1.1.63 (`VERSION`)
- License: MIT, with the copyright lines of Peasant Smith and the Project Maya
  contributors, and of Niko1221 and the Strata contributors

The pin was checked from a shallow, read-only checkout kept outside this repository. Its
files were read as text and nothing from it was executed locally. The commit SHA and a
file-hash manifest of the donor files PulsarMLX relies on are what every later check
verifies; the manifest is produced by the conformance work packages.

project-maya moves quickly: its `CHANGELOG.md` at the pin lists 99 release entries
between 2026-10-07 and 2026-11-14. PulsarMLX does not follow it. All parity work is
against the one pinned commit.

## Policy

- There is no automatic sync, subtree, vendoring relationship, or promise to track
  project-maya changes.
- **Re-pinning is a separate owner decision**, recorded as a new row in this log. It is
  never a side effect of other work. Any re-pin beyond `7e68a30f` is open item OPEN-28 in
  `specs/022-console-serving-parity/checklists/analysis.md`.
- project-maya code runs only in the manual GitHub Actions reference job, checked out
  outside the workspace and verified by SHA and file hashes. It never runs on a PulsarMLX
  machine, and its engine binaries are never launched.
- A re-pin never imports vendor chat templates, fonts, vendor logos, app icons, or any
  binary file.

## Re-pin procedure

1. Record the owner's decision and the candidate commit in this log.
2. Fetch the candidate commit outside the workspace and verify its SHA. Read `LICENSE`,
   `VERSION` and the credits again. Confirm both copyright lines, and look for new or
   changed third-party components under `serve/` and `serve/web/`.
3. Re-derive the three pinned inputs:
   - **The donor test listing for the ledger**: every test method under `serve/`, found
     by parsing the files as text, not by running them. Added, removed and renamed
     methods become ledger rows to resolve in `console/parity/ledger.json`; no row may
     dangle.
   - **The reference corpus**: captured again from project-maya's own server in
     fake-engine mode by the manual reference job, then normalized and committed as text
     with a provenance header naming the new commit.
   - **The file-hash manifest**: recomputed for the donor files the manual jobs check,
     so those jobs refuse any tree other than the new pin.
4. Compare every adapted dashboard file and every translated module or test with its
   donor source at the new commit. Carry each upstream change across or record why not.
   Update the provenance headers to the new commit.
5. Review the deviation register,
   `specs/022-console-serving-parity/contracts/deviations.md`. Close entries the new
   donor no longer needs and propose new ones for owner approval.
6. Update [PROJECT_MAYA.md](PROJECT_MAYA.md) (pin, module map, third-party components),
   the project-maya section of `NOTICE.md`, and `console/LICENSES/` if the license text
   or a third-party component changed.
7. Run every blocking and manual console job on the result, and report the ledger counts
   before and after.
