#!/usr/bin/env bash
# CPU-only checks: use the production storage module sources and an equivalent
# local Read type, without stream/build.rs and its Apple native linkage.
# This isolates storage regressions; it does not qualify the stream package.
# engine/tests/host_step_package.rs supplements it with real public package types
# and must be compiled/linked separately with --no-run on native-linked hosts.
# Preserve all logs/targets in the printed private temporary directory.
set -euo pipefail
rust_host_repo="$(cd "$(dirname "$0")/.." && pwd)"
rust_host_checks="$(mktemp -d "${TMPDIR:-/tmp}/pulsar-rust-host.XXXXXX")"
export CARGO_BUILD_JOBS=2
export CARGO_TARGET_DIR="$rust_host_checks/target"
export RUST_HOST_REPO="$rust_host_repo"
export RUST_HOST_CHECKS="$rust_host_checks"
python3 - <<'PY'
from pathlib import Path
import os,json
repo=Path(os.environ['RUST_HOST_REPO'])
checks=Path(os.environ['RUST_HOST_CHECKS'])
(checks/'Cargo.toml').write_text('''[package]
name="pulsar-stream-host-tests"
version="0.0.0"
edition="2021"
[workspace]
[lib]
name="stream"
path="host.rs"
[[test]]
name="positional_source"
path='''+json.dumps(str(repo/'crates/stream/tests/positional_source.rs'))+'\n')
(checks/'host.rs').write_text('''#[derive(Debug,Clone,Copy,PartialEq,Eq)]
pub struct Read { pub offset:u64, pub len:u64 }
#[path='''+json.dumps(str(repo/'crates/stream/src/stable_slab.rs'))+''']
mod stable_slab;
pub use stable_slab::*;
#[path='''+json.dumps(str(repo/'crates/stream/src/positional.rs'))+''']
mod positional;
pub use positional::*;
''')
PY
printf 'Private CPU check output: %s\n' "$rust_host_checks"
python3 "$rust_host_repo/crates/backend/fixtures/routed_cpu_v1/reference.py" --check
cargo generate-lockfile --offline --manifest-path "$rust_host_checks/Cargo.toml"
for rust_host_profile in debug release; do
    rust_host_flags=(--profile dev)
    if [ "$rust_host_profile" = release ]; then rust_host_flags=(--release); fi
    cargo test --locked --offline --manifest-path "$rust_host_repo/Cargo.toml" -p backend "${rust_host_flags[@]}" -- --test-threads=1 2>&1 | tee "$rust_host_checks/backend-$rust_host_profile.log"
    cargo test --locked --offline --manifest-path "$rust_host_checks/Cargo.toml" --lib --test positional_source "${rust_host_flags[@]}" -- --test-threads=1 2>&1 | tee "$rust_host_checks/storage-$rust_host_profile.log"
    cargo run --locked --offline --manifest-path "$rust_host_repo/Cargo.toml" -p backend --example host_lifecycle "${rust_host_flags[@]}" 2>&1 | tee "$rust_host_checks/example-$rust_host_profile.log"
    cargo run --locked --offline --manifest-path "$rust_host_repo/Cargo.toml" -p backend --example routed_host_lifecycle "${rust_host_flags[@]}" 2>&1 | tee "$rust_host_checks/routed-example-$rust_host_profile.log"
done
