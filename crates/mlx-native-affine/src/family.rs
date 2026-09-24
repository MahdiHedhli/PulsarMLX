//! Transcription of the MLX 0.31.2 quantized_matmul kernel selection
//! (contract operations.OP-QMM.kernel_selection_0_31_2), used only to record
//! the family that ran and to select the N-QMM-BOUND exponent.
//!
//! Sources (MLX312 = ml-explore/mlx 68cf2fdd):
//! * architecture generation: `mlx/backend/metal/device.cpp:485-497`
//!   (the two characters before the last, each 0 if not a digit);
//! * batch limit: `get_qmv_batch_limit(K, N, d)` at
//!   `mlx/backend/metal/quantized.cpp:83-126`;
//! * dispatch: `QuantizedMatmul::eval_gpu` (`quantized.cpp:1386-1454`), quad
//!   branch (`K in {64, 128}`, `quantized.cpp:1380`), qmv_fast predicate
//!   (`N % 8 == 0 && K % 512 == 0`, `quantized.cpp:259`), split-K choice
//!   (`quantized.cpp:793-805`).
//!
//! No kernel-reporting API exists; the family is derived, not observed.

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Family {
    QmvQuad,
    QmvFast,
    Qmv,
    QmmT,
    QmmTSplitK,
}

impl Family {
    pub fn as_str(self) -> &'static str {
        match self {
            Family::QmvQuad => "qmv_quad",
            Family::QmvFast => "qmv_fast",
            Family::Qmv => "qmv",
            Family::QmmT => "qmm_t",
            Family::QmmTSplitK => "qmm_t_splitk",
        }
    }
    pub fn parse(s: &str) -> Option<Family> {
        Some(match s {
            "qmv_quad" => Family::QmvQuad,
            "qmv_fast" => Family::QmvFast,
            "qmv" => Family::Qmv,
            "qmm_t" => Family::QmmT,
            "qmm_t_splitk" => Family::QmmTSplitK,
            _ => return None,
        })
    }
}

/// Parsed architecture string (e.g. `applegpu_g14s`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Architecture {
    pub name: String,
    pub generation: u32,
    pub size_class: char,
}

pub fn parse_architecture(arch: &str) -> Architecture {
    let b = arch.as_bytes();
    let digit = |c: u8| -> u32 {
        let v = c as i32 - b'0' as i32;
        if (0..10).contains(&v) {
            v as u32
        } else {
            0
        }
    };
    let generation = if b.len() >= 3 {
        digit(b[b.len() - 3]) * 10 + digit(b[b.len() - 2])
    } else {
        0
    };
    Architecture {
        name: arch.to_string(),
        generation,
        size_class: arch.chars().last().unwrap_or('\0'),
    }
}

/// `get_qmv_batch_limit(D = K, O = N, arch)`.
pub fn qmv_batch_limit(k: usize, n: usize, arch: &Architecture) -> usize {
    let small = k <= 2048 && n <= 2048;
    let medium = k <= 4096 && n <= 4096;
    let pick = |a: usize, b: usize, c: usize| {
        if small {
            a
        } else if medium {
            b
        } else {
            c
        }
    };
    let g1314 = arch.generation == 13 || arch.generation == 14;
    match (g1314, arch.size_class) {
        (_, 'd') => pick(32, 18, 12),
        (true, _) => pick(14, 10, 6),
        (false, _) => pick(18, 12, 10),
    }
}

/// `qmm_splitk`'s split factor (architecture independent).
pub fn split_k(m: usize, n: usize, k: usize, group_size: usize) -> usize {
    let tiles = n.div_ceil(32) * m.div_ceil(32);
    let mut sk = (512 / tiles).max(1);
    sk = sk.min(k / group_size);
    while sk > 1 && !k.is_multiple_of(sk * group_size) {
        sk -= 1;
    }
    sk
}

/// The vector family for transpose=true.
pub fn vector_family(k: usize, n: usize) -> Family {
    if k == 64 || k == 128 {
        Family::QmvQuad
    } else if n.is_multiple_of(8) && k.is_multiple_of(512) {
        Family::QmvFast
    } else {
        Family::Qmv
    }
}

/// The matrix family and its split factor.
pub fn matrix_family(m: usize, n: usize, k: usize, group_size: usize) -> (Family, usize) {
    let sk = split_k(m, n, k, group_size);
    if sk > 1 {
        (Family::QmmTSplitK, sk)
    } else {
        (Family::QmmT, 1)
    }
}

/// N-QMM-BOUND per-family gamma exponent (T = float32).
pub fn gamma_exponent(f: Family, k: usize, bits: u32, sk: usize) -> usize {
    match f {
        Family::QmvQuad => k / 4 + 5,
        Family::QmvFast => {
            if bits == 4 {
                k / 16 + 17
            } else {
                k / 8 + 9
            }
        }
        Family::Qmv => {
            if bits == 4 {
                k / 8 + 9
            } else {
                k / 4 + 5
            }
        }
        Family::QmmT => k + 3,
        Family::QmmTSplitK => k / sk + sk + 3,
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Candidate {
    pub family: Family,
    pub split_k: Option<usize>,
    pub gamma_n: usize,
}

/// Every family the dispatcher could select on SOME architecture: the vector
/// family for M_eff <= 31, the matrix family for M_eff >= 6 (L ranges over
/// 6..=32). For 6 <= M_eff <= 31 both are candidates and the bound is their
/// maximum (N-QMM-BOUND.ambiguous_band).
pub fn candidates(m: usize, n: usize, k: usize, group_size: usize, bits: u32) -> Vec<Candidate> {
    let mut out = Vec::new();
    if m <= 31 {
        let f = vector_family(k, n);
        out.push(Candidate {
            family: f,
            split_k: None,
            gamma_n: gamma_exponent(f, k, bits, 1),
        });
    }
    if m >= 6 {
        let (f, sk) = matrix_family(m, n, k, group_size);
        out.push(Candidate {
            family: f,
            split_k: if f == Family::QmmTSplitK {
                Some(sk)
            } else {
                None
            },
            gamma_n: gamma_exponent(f, k, bits, sk),
        });
    }
    out
}

/// The union-rule exponent: the largest candidate exponent.
pub fn bound_exponent(m: usize, n: usize, k: usize, group_size: usize, bits: u32) -> usize {
    candidates(m, n, k, group_size, bits)
        .iter()
        .map(|c| c.gamma_n)
        .max()
        .expect("M_eff >= 1 has a candidate")
}

/// What the dispatcher selects on this architecture.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Derived {
    pub batch_limit: usize,
    pub split_k: usize,
    pub family: Family,
    pub family_gamma_n: usize,
}

pub fn derive(
    m: usize,
    n: usize,
    k: usize,
    group_size: usize,
    bits: u32,
    arch: &Architecture,
) -> Derived {
    let l = qmv_batch_limit(k, n, arch);
    let sk = split_k(m, n, k, group_size);
    let (family, used_sk) = if m >= l {
        matrix_family(m, n, k, group_size)
    } else {
        (vector_family(k, n), 1)
    };
    Derived {
        batch_limit: l,
        split_k: sk,
        family,
        family_gamma_n: gamma_exponent(family, k, bits, used_sk),
    }
}

/// Whether NAX-capable hardware (device.cpp:828-847) -- recorded only; NAX is
/// unreachable with MLX_ENABLE_TF32=0 and float32 x (A-NONAX).
pub fn nax_capable_hardware(arch: &Architecture, os_at_least_26_2: bool) -> bool {
    os_at_least_26_2 && arch.generation >= if arch.size_class == 'p' { 18 } else { 17 }
}

/// R2 labelling predicate (contract version_relation.r2_labelling_predicate),
/// with `batch_limit` the qmv batch limit and `generation` the host's.
pub fn r2_different_kernel_family(m: usize, k: usize, batch_limit: usize, generation: u32) -> bool {
    m < batch_limit && k != 64 && k != 128 && m >= 2 && generation >= 15
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn architecture_generation() {
        let a = parse_architecture("applegpu_g14s");
        assert_eq!((a.generation, a.size_class), (14, 's'));
        let a = parse_architecture("applegpu_g15d");
        assert_eq!((a.generation, a.size_class), (15, 'd'));
        assert_eq!(parse_architecture("x").generation, 0);
    }

    #[test]
    fn batch_limit_range_is_6_to_32() {
        let mut seen = std::collections::BTreeSet::new();
        for arch in [
            "applegpu_g13s",
            "applegpu_g14d",
            "applegpu_g15g",
            "applegpu_g16s",
            "applegpu_g17d",
        ] {
            let a = parse_architecture(arch);
            for (k, n) in [(64, 64), (4096, 64), (8192, 64), (16384, 16384)] {
                seen.insert(qmv_batch_limit(k, n, &a));
            }
        }
        assert_eq!(*seen.iter().next().unwrap(), 6);
        assert_eq!(*seen.iter().last().unwrap(), 32);
    }

    #[test]
    fn split_k_examples() {
        // M=16, N=64, K=256, gs=64: tiles = 2*1 = 2 -> 256 -> min(256, 4) = 4.
        assert_eq!(split_k(16, 64, 256, 64), 4);
        // M=512, N=1024: tiles = 32*16 = 512 -> 1: no split.
        assert_eq!(split_k(512, 1024, 64, 64), 1);
    }
}
