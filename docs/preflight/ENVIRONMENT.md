# Environment preflight

Captured on 2026-08-05 at 00:21 EDT, before installing or changing any host
tooling. The diagnostics in this report were read-only. Hardware serials,
device identifiers, authentication tokens, credentials, and private keys are
intentionally omitted.

## Host and workspace

| Item | Observed value | Evidence |
| --- | --- | --- |
| Working directory | `/Users/mhedhli/Documents/Coding/PulsarMLX` | `pwd` |
| Operating system | macOS 26.0, build 25A354 | `sw_vers` |
| Machine | Mac Studio, Apple M1 Ultra | filtered `system_profiler SPHardwareDataType` |
| Shell architecture | native `arm64`; not translated by Rosetta | `uname -m`, `arch`, `sysctl -in sysctl.proc_translated` |
| Shell | `/bin/zsh`, zsh 5.9 arm64 | `$SHELL`, `zsh --version` |
| Unified memory | 128 GiB (137,438,953,472 bytes) | filtered `system_profiler`, `sysctl -n hw.memsize` |
| Workspace filesystem | 1.8 TiB total, 1.6 TiB used, 210 GiB available, 89% full | `df -h .` |

The available-space value is a point-in-time filesystem reading. Giant-model
checkpoints and converted copies can consume it quickly, so storage headroom
must be checked again before downloading or converting model weights.

## Apple developer tools

| Tool | Status |
| --- | --- |
| Xcode Command Line Tools | Installed, selected, and functional at `/Library/Developer/CommandLineTools` |
| CLT package | `CLTools_Executables` version `26.2.0.0.1.1764812424` |
| macOS SDK | SDK 26.2 at `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk` |
| `xcrun` compiler | `/Library/Developer/CommandLineTools/usr/bin/clang` |
| C compiler | Apple clang 17.0.0 (`clang-1700.6.3.2`), target `arm64-apple-darwin25.0.0` |
| C++ compiler | `/usr/bin/c++`, backed by the selected Apple Clang toolchain |
| Full Xcode | Not selected: `xcodebuild -version` exits because the active developer directory is the standalone CLT instance |

The `xcodebuild` result does not prove that an unselected Xcode application is
absent elsewhere. The selected Command Line Tools are sufficient for the
current Rust workspace baseline.

## Source-control tools

| Tool | Status |
| --- | --- |
| Git | `git version 2.50.1 (Apple Git-155)` |
| GitHub CLI | `gh` 2.92.0 (2026-04-28) |
| GitHub authentication | Authenticated to `github.com` as active public account `MahdiHedhli`; HTTPS Git operations configured |

Authentication was checked without recording token values or token scopes.

## Rust toolchain

| Item | Observed value |
| --- | --- |
| `rustc` | 1.97.1 (8bab26f4f, 2026-07-14), installed by Homebrew |
| Compiler path | `/opt/homebrew/bin/rustc` |
| Host target | `aarch64-apple-darwin` |
| LLVM | 22.1.8 |
| Sysroot | `/opt/homebrew/Cellar/rust/1.97.1` |
| Host target library | `/opt/homebrew/Cellar/rust/1.97.1/lib/rustlib/aarch64-apple-darwin/lib` |
| `cargo` | 1.97.1 (`c980f4866`, 2026-06-30), installed by Homebrew |
| Cargo path | `/opt/homebrew/bin/cargo` |
| `rustup` | Not installed |

The native host target is available. Because this is a Homebrew toolchain and
`rustup` is absent, `rustup target list --installed` cannot enumerate managed
cross-targets. The macOS workflow records the Rust and Cargo versions provided
by the `macos-15` runner. It does not install or pin a Rust toolchain, so local
and CI compiler revisions may differ.

## Python and MLX

| Item | Observed value |
| --- | --- |
| Python | 3.14.6 |
| Executable | `/opt/homebrew/opt/python@3.14/bin/python3.14` |
| Virtual environment | None active: `sys.prefix == sys.base_prefix`; `VIRTUAL_ENV` and `CONDA_PREFIX` are unset |
| MLX module | Not importable by the active Python interpreter |
| MLX distribution metadata | Not present for the active Python interpreter |

This only establishes that MLX is absent from the active Python 3.14
environment. It does not rule out an installation in an inactive environment.
At the initial read-only snapshot, no project virtual environment existed and
MLX was not installed. The later isolated Spec Kit installation is recorded
below.

## Native build utilities

| Tool | Availability |
| --- | --- |
| CMake | Available at `/opt/homebrew/bin/cmake`, version 4.3.2 |
| Ninja | Not found on `PATH` |
| pkg-config | Available at `/opt/homebrew/bin/pkg-config`, version 3.0.5 |
| `cc` / `clang` | Available; Apple clang 17.0.0, native arm64 target |
| `c++` | Available through the Apple Command Line Tools |

## Authorized post-inspection tooling change

The initial read-only audit confirmed that `specify` was absent and that
`uv` 0.11.17 for `aarch64-apple-darwin` was already available. Phase 6 then
installed the pinned official GitHub Spec Kit release:

```sh
uv tool install specify-cli \
  --from git+https://github.com/github/spec-kit.git@v0.15.2
```

Actual result: installation succeeded. `specify --version` reports 0.15.2.
`specify version` reports an isolated Python 3.12.13 runtime on Darwin arm64;
this does not replace the active system-facing Python 3.14.6 recorded above.
`specify check` found the Codex CLI and reported that the Specify CLI was ready.

The installer emitted one warning while deleting an invalid stale `uv`
interpreter-cache entry, then completed normally. No MLX package, Ninja,
`rustup` toolchain, or model data was installed.

## Readiness summary

The host is a native Apple Silicon machine with enough unified memory for
backend bring-up and a functional compiler/Rust baseline. The current Rust
workspace compiles and its portable tests run on this machine, as recorded in
`BASELINE_VALIDATION.md`.

Items intentionally left unchanged during preflight:

- MLX is not installed for the active Python interpreter.
- Ninja is not installed.
- `rustup` is not installed; Rust and Cargo come from Homebrew.
- Full Xcode is not selected.
- Disk utilization is already 89%, despite 210 GiB remaining.

These are environment facts, not installation requests. Backend dependency
selection should be made explicitly in a later implementation phase.

## Diagnostic commands

The inspection used the following command families:

```sh
pwd
sw_vers
system_profiler SPHardwareDataType  # filtered to Model Name, Chip, and Memory
uname -m
arch
sysctl -in sysctl.proc_translated
sysctl -n hw.memsize
df -h .
xcode-select -p
pkgutil --pkg-info=com.apple.pkg.CLTools_Executables
xcrun --find clang
xcrun clang --version
xcrun --sdk macosx --show-sdk-path
xcrun --sdk macosx --show-sdk-version
xcodebuild -version
git --version
gh --version
gh auth status --hostname github.com  # credential-bearing lines redacted
command -v rustc cargo rustup
rustc -vV
rustc --print sysroot
rustc --print target-libdir
cargo --version
python3 --version
python3 -c 'import os, sys; ...'        # prefixes and environment status only
python3 -c 'import importlib.util; ...' # MLX module discovery only
python3 -m pip show mlx
command -v cmake ninja pkg-config cc clang c++
cmake --version
pkg-config --version
cc --version
clang --version
```
