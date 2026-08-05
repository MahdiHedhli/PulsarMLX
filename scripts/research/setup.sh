#!/bin/sh

set -eu
umask 077

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
local_root="$repository_root/.pulsarmlx-local"
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

for state_path in \
    "$local_root" \
    "$state_dir" \
    "$state_dir/cache" \
    "$state_dir/candidates" \
    "$state_dir/logs" \
    "$state_dir/oracle-build" \
    "$state_dir/tmp"
do
    if [ -L "$state_path" ]; then
        echo "research setup: local state must not contain symbolic links" >&2
        exit 1
    fi
done

if ! mkdir -p "$local_root" "$state_dir" 2>/dev/null; then
    echo "research setup: local state directory cannot be created" >&2
    exit 1
fi

for state_leaf in cache candidates logs oracle-build tmp; do
    if ! mkdir -p "$state_dir/$state_leaf" 2>/dev/null; then
        echo "research setup: local state directory cannot be created" >&2
        exit 1
    fi
    if [ ! -d "$state_dir/$state_leaf" ] || [ -L "$state_dir/$state_leaf" ]; then
        echo "research setup: local state directory is unsafe" >&2
        exit 1
    fi
done

echo "research setup: ready (offline, local state only, no model access)"
