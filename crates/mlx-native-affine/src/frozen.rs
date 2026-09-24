//! Frozen identities of the governing package (owner GO 2026-09-23).
//!
//! Every value here is quoted from the contract
//! `specs/020-mlx-safetensors-affine/contracts/native-primitives-v1.json`
//! (sha256 `76959ccb...`) or from the owner GO record. Changing one is a
//! contract revision, never an implementation fix (correction_policy).

pub const CONTRACT_PATH: &str =
    "specs/020-mlx-safetensors-affine/contracts/native-primitives-v1.json";
pub const CONTRACT_SHA256: &str =
    "76959ccb13046c664db67469fd8186b7fb668910072060400b38b682e92fec72";
pub const CONTRACT_SCHEMA: &str = "pulsarmlx.f020.native-primitives-contract/1.0.0-draft.6";
pub const PLAN_PATH: &str = "specs/020-mlx-safetensors-affine/slice2b-plan.md";
pub const PLAN_SHA256: &str = "24a06db0a34ee4ec8ca9af8728d3d27e26cfe3c4a6c22dcba06011c8ab2796df";
pub const SOURCE_PINS_PATH: &str = "specs/020-mlx-safetensors-affine/source-pins-slice2.json";
pub const SOURCE_PINS_SHA256: &str =
    "02e963a02cf1d63168c57cff316c1d3471313498396b2abd7b3e5ec432267bb4";
pub const GENERATOR_PATH: &str = "scripts/research/f020_native_primitives_fixtures_v1.py";
pub const GENERATOR_SHA256: &str =
    "28078a6d0a6de859c1a1ac557fef3f683d8ecd75a780198b4c0bc7c15c267999";
pub const FIXTURE_DIR: &str = "fixtures/native-primitives";
pub const MANIFEST_PATH: &str = "fixtures/native-primitives/manifest.json";
pub const MANIFEST_SHA256: &str =
    "472b5b64aaddfe7ecbfd05930ba2f4d261023a9a829f957b5b23b110fcf37d04";
/// sha256 of `LC_ALL=C shasum -a 256 cases/*.bin` run inside the fixture dir.
pub const CASES_LISTING_SHA256: &str =
    "ed0c2e73420213a1ae316ea90a20100fcefee87bade32dec36ff7dac25461f82";
pub const CASE_COUNT: usize = 363;
pub const CASE_FILE_COUNT: usize = 361;

/// Parent watchdog (contract error_handling.child_process.watchdog). Frozen.
pub const CHILD_TIMEOUT_SECONDS: u64 = 1800;

/// Dedicated exit status of a child that refuses its start environment
/// (process-level refusal R-NAX, contract refusals.process_level).
pub const R_NAX_EXIT_STATUS: i32 = 78;
/// Exit status of a `qualify` binary built without the pinned native prefix.
pub const NATIVE_UNAVAILABLE_EXIT_STATUS: i32 = 69;
/// Exit status of a child whose setup failed after the environment check
/// (ABI mismatch, handle construction, provenance, library identity).
pub const SETUP_FAILURE_EXIT_STATUS: i32 = 70;

/// The N-DQ-CODES execution canary (E4), run before and after every case:
/// 8-bit codes 0..255 at group 64 with bfloat16 unit metadata.
pub const CANARY_CASE_ID: &str = "dq-codes-b8-g64-bf16";

pub const MLX_COMMIT: &str = "68cf2fddd8de5edd8ab3d926391772b2e2cedad8";
pub const MLX_C_COMMIT: &str = "0726ca922fc902c4c61ef9c27d94132be418e945";
pub const MLX_VERSION: &str = "0.31.2";

/// The contract's refusal order (refusals.order), verbatim.
pub const REFUSAL_ORDER: [&str; 18] = [
    "R-DEVICE",
    "R-TRANSPOSE",
    "R-BITS",
    "R-GROUP",
    "R-WDTYPE",
    "R-EMPTY-DIM",
    "R-META",
    "R-XDTYPE",
    "R-XSHAPE",
    "R-GEOMETRY",
    "R-NONFINITE",
    "R-SUBNORMAL",
    "R-DOMAIN-X-RANGE",
    "R-DOMAIN-META-RANGE",
    "R-DOMAIN-ROWSUM",
    "R-DOMAIN-WMAX",
    "R-DQ-RANGE",
    "R-DQ-NORMAL",
];

/// Environment the child requires at start (A-NONAX.runtime_assertion).
pub const REQUIRED_ENV: [(&str, &str); 1] = [("MLX_ENABLE_TF32", "0")];
pub const FORBIDDEN_ENV: [&str; 3] = [
    "MLX_METAL_GPU_ARCH",
    "MLX_MAX_OPS_PER_BUFFER",
    "MLX_MAX_MB_PER_BUFFER",
];

/// Report schema written by the child.
pub const CHILD_REPORT_SCHEMA: &str = "pulsarmlx.f020.slice2b-child-report/1.0.0";
/// Summary schema written by the parent.
pub const PARENT_SUMMARY_SCHEMA: &str = "pulsarmlx.f020.slice2b-qualification/1.0.0";
