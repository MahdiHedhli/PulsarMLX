# Retained runtime static admission

This host-only correction preserves native code, harness, build inputs, scientific
gates and native-ci's three-argument observation. Studio readiness, freeze,
revalidation, before-child admission and sealing share `native_state`.

The `pulsarmlx.retained-runtime-static/1` record distinguishes `LC_ID_DYLIB`,
typed imports, system edges, already pinned MLX images and the retained runtime.
The unchanged harness clears inherited variables and sets `DYLD_LIBRARY_PATH`
to exactly the retained prefix's `lib` directory. The inspector itself refuses
all loader overrides. The fixed leaf-name entry selects the admitted file;
there is no filesystem search or fallback based on finding a matching hash.

Supported imports are the exact `@rpath/<known-library>` form and absolute
names identifying the fixed entry or its canonical target. Loader-relative,
executable-relative, nested rpath and unrelated absolute names refuse. Actual
LC_RPATH values are captured as unselected context. System edges need no ordinary
shared-cache file, but a competing fixed-prefix system override refuses.
System install names with parent traversal or other noncanonical spelling
refuse before classification; a system-looking prefix cannot conceal a private
dependency.

The three exact images are `libmlx.dylib`, `libmlxc.dylib`, `libjaccl.dylib`.
Only the specific fixed runtime entry may resolve outside the prefix. Its full
symlink chain, canonical target, file identity and hash are recorded and checked
again after inspection. The required runtime SHA-256 is
`36d3439033afa76443943a1a6967623cde063e435283ccf3b4e6a4e93a8755ca`.
Own IDs are not imports; duplicate import edges remain visible while one
canonical runtime is counted. Unexpected non-system dependencies refuse.
An actual import from an admitted MLX image is required; a runtime's self-import
cannot establish that dependency.

Inspection runs only `/usr/bin/otool -L <image>` or `-l <image>`: 15 seconds and
1 MiB of captured output per command, at most 512 load commands, 16,384 lines,
4,096 characters per line and 32 symlinks per fixed entry. Errors and timeouts
kill only the owned inspection process and wait at most five seconds for cleanup;
an unconfirmed reap raises an error and cannot become admission. Native-ci does not enter this
new parser. Thin-image typed output is required; unsupported framing refuses.

The policy follows Apple's [dyld manual](https://github.com/apple-oss-distributions/dyld/blob/main/doc/man/man1/dyld.1)
and [dynamic library identification](https://developer.apple.com/forums/thread/736719).
It establishes static retained-runtime evidence, **not** a libjaccl loaded-image
attestation. The existing native child attests only the two MLX images and
metallib. Actual Studio LC_RPATH and canonical/symlink observations remain
pending a separately authorized physical preflight. Test fixtures are synthetic.

Studio003's original refusal, original C executables and absent claims remain
historical evidence. No claim is renamed, moved, removed or refunded. Copying
stays the shipping default; physical/combined M1a, M1b and M2–M4 remain held.
