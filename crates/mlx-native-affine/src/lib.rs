//! F020 Slice 2B -- native MLX affine primitives, qualified in a child process.
//!
//! Governing package (frozen; see [`frozen`]): contract
//! `specs/020-mlx-safetensors-affine/contracts/native-primitives-v1.json`,
//! plan `specs/020-mlx-safetensors-affine/slice2b-plan.md`, fixture population
//! `fixtures/native-primitives/`.
//!
//! # Split
//!
//! * This **library** is pure Rust and never links MLX. It holds everything
//!   that must be decided without trusting the native library: the refusals
//!   in their frozen order ([`refusal`]), the 0.31.2 kernel-family transcription
//!   ([`family`]), the binary64 and bit-exact acceptance algorithms
//!   ([`gates`]), the frozen-population validation ([`fixture`]) and the
//!   parent harness with its watchdog ([`harness`]).
//! * The **`qualify` binary** (`src/bin/qualify/`) is the only artifact linked
//!   against the pinned MLX / MLX-C prefix. It owns the FFI, `NativeContext`,
//!   `NativeArray`, the `Evaluated` typestate, the process-wide error handler
//!   and the bridge operations, and runs every manifest case in one child
//!   process with a fixed environment.
//!
//! # References
//!
//! R1 (`mlx_affine::reference_qmm` and the exact Python reference) is consumed
//! by the parent test only. R3 is the `qualify` child. R2 (the 0.32.0 wheel)
//! is a cross-version observation in `scripts/ci/` and gates nothing.

//!
//! # Slice 2C
//!
//! [`compose`] selects ONE expert plane of a synthetic stacked affine tensor
//! through the Slice 1 catalog, module resolution and checked selection, and
//! stages it for the unchanged Slice 2B bridge; [`frozen_compose`] holds the
//! frozen Slice 2C identities. Both stay MLX-free: the compose child mode of
//! the `qualify` binary is the only place the staged plane meets MLX-C.

#![forbid(unsafe_code)]

pub mod compose;
pub mod dtype;
pub mod family;
pub mod fixture;
pub mod frozen;
pub mod frozen_compose;
pub mod gates;
pub mod harness;
pub mod refusal;
