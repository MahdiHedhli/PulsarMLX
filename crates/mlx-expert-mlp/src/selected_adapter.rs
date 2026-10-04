//! Owned packed staging and host preflight for the separately reviewed scope.
//! This module cannot create a native execution capability.
use crate::selected_snapshot::SelectedSnapshot;
use mlx_native_affine::{
    dtype::Dtype,
    family,
    fixture::{sha256_hex, HostTensor},
    refusal::{check_qmm, DeviceFacts},
};

pub const INPUT_SHA256: &str = "746ed37cdd4a6a1792ec512ada02f9a2bd2cfa9c5a88d2eae2758ccbd9b2d799";

pub struct SelectedAdapter {
    snapshot: SelectedSnapshot,
    input: HostTensor,
}

impl SelectedAdapter {
    pub fn bind(snapshot: SelectedSnapshot, original_input: Vec<u8>) -> Result<Self, String> {
        if original_input.len() != 16384 || sha256_hex(&original_input) != INPUT_SHA256 {
            return Err("SELECTED-R-INPUT: prospective original input identity".into());
        }
        Ok(Self {
            snapshot,
            input: HostTensor {
                name: "original-input-v2".into(),
                dtype: Dtype::F32,
                shape: vec![1, 4096],
                bytes: original_input,
            },
        })
    }
    pub fn input(&self) -> &HostTensor {
        &self.input
    }
    /// Explicit owned copies, 4,718,592 bytes per staged role. Original bytes
    /// remain immutable. Native widening belongs to the inherited bridge.
    pub fn stage(&self, role: usize) -> Result<[HostTensor; 3], String> {
        if role >= 3 {
            return Err("SELECTED-R-ROLE".into());
        }
        let (n, k) = if role == 2 {
            (4096, 2048)
        } else {
            (2048, 4096)
        };
        Ok(std::array::from_fn(|component| HostTensor {
            name: format!("selected-{role}-{component}"),
            dtype: if component == 0 {
                Dtype::U32
            } else {
                Dtype::BF16
            },
            shape: vec![n, if component == 0 { k / 8 } else { k / 64 }],
            bytes: self.snapshot.component(role, component).unwrap().to_vec(),
        }))
    }
}

/// All inherited numerical predicates stay in their original order. This
/// additive scope check is not a change to the older qualification population.
pub fn selected_preflight(
    role: usize,
    x: &HostTensor,
    parts: &[HostTensor; 3],
) -> Result<usize, String> {
    let (n, k, exponent) = match role {
        0 | 1 => (2048, 4096, 273),
        2 => (4096, 2048, 145),
        _ => return Err("SELECTED-R-ROLE".into()),
    };
    if x.shape != [1, k]
        || x.bytes.len() != k * 4
        || parts[0].shape != [n, k / 8]
        || parts[1].shape != [n, k / 64]
        || parts[2].shape != [n, k / 64]
        || parts[0].bytes.len() != n * k / 2
        || parts[1].bytes.len() != n * k / 32
        || parts[2].bytes.len() != n * k / 32
        || n * k != 8_388_608
    {
        return Err("SELECTED-R-GEOMETRY: M1 scoped 2^23 MAC projection".into());
    }
    let g = check_qmm(
        &DeviceFacts::GPU,
        true,
        x,
        &parts[0],
        &parts[1],
        &parts[2],
        4,
        64,
    )
    .map_err(|e| e.to_string())?;
    let actual = family::bound_exponent(g.m_eff, g.n, g.k, 64, 4);
    if actual != exponent {
        return Err("SELECTED-R-BOUND: pinned family exponent".into());
    }
    Ok(actual)
}
