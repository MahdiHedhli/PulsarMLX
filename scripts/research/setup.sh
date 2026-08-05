#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
state_dir="$repository_root/.pulsarmlx-local/research-work"

if ! git -C "$repository_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "research setup: repository root is unavailable" >&2
    exit 1
fi

for required_file in Cargo.lock uv.lock .specify/feature.json; do
    if [ ! -f "$repository_root/$required_file" ]; then
        echo "research setup: required committed lock or feature metadata is missing" >&2
        exit 1
    fi
done

if ! git -C "$repository_root" check-ignore -q .pulsarmlx-local/research-work/; then
    echo "research setup: local state directory is not ignored" >&2
    exit 1
fi

mkdir -p \
    "$state_dir/cache" \
    "$state_dir/candidates" \
    "$state_dir/logs" \
    "$state_dir/oracle-build" \
    "$state_dir/tmp"

echo "research setup: ready (offline, local state only, no model access)"
