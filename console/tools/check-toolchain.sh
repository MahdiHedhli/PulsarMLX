#!/usr/bin/env bash
# Toolchain check for the PulsarMLX Console work (spec 022).
#
# Reads the pinned channel from console/rust-toolchain.toml and fails unless
# `rustc -V`, run from console/, reports exactly that version. rustup applies
# the pin file by itself; a host without rustup ignores it, so local gates run
# this script. CI keeps its own assertion in .github/workflows/console.yml.
#
# Usage:
#   console/tools/check-toolchain.sh
#
# It can be run from any directory. It prints one line, "ok" or "FAIL". Exit
# status: 0 when the versions match, 1 when they differ or rustc is missing or
# fails, 2 when the pin cannot be read.
#
# Requires bash (3.2 or later) and rustc, nothing else. Read-only.

set -u
export LC_ALL=C

case "$0" in
    */*) tools_dir=${0%/*} ;;
    *) tools_dir=. ;;
esac
console_dir=$(cd "$tools_dir/.." && pwd) || {
    echo "FAIL toolchain  cannot find the console directory" >&2
    exit 2
}
pin_file="$console_dir/rust-toolchain.toml"

pinned=""
channel_re='^[[:space:]]*channel[[:space:]]*=[[:space:]]*"([^"]+)"[[:space:]]*(#.*)?$'
if [ -f "$pin_file" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        if [[ $line =~ $channel_re ]]; then
            pinned=${BASH_REMATCH[1]}
            break
        fi
    done <"$pin_file"
fi
if [ -z "$pinned" ]; then
    echo "FAIL toolchain  no channel = \"...\" line in console/rust-toolchain.toml"
    exit 2
fi

if ! command -v rustc >/dev/null 2>&1; then
    echo "FAIL toolchain  rustc not found; console/rust-toolchain.toml pins $pinned"
    exit 1
fi

# Run from console/ so that rustup, where present, applies the pin file.
if ! reported=$(cd "$console_dir" && rustc -V 2>/dev/null); then
    echo "FAIL toolchain  rustc -V failed; console/rust-toolchain.toml pins $pinned"
    exit 1
fi
version=""
set -f
# shellcheck disable=SC2086
set -- $reported
set +f
[ "$#" -ge 2 ] && version=$2

if [ "$version" = "$pinned" ]; then
    echo "ok   toolchain  rustc $version matches console/rust-toolchain.toml"
    exit 0
fi
printf 'FAIL toolchain  rustc reports %s; console/rust-toolchain.toml pins %s\n' \
    "${version:-nothing}" "$pinned"
exit 1
