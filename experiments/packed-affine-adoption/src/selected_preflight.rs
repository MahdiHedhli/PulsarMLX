// Extracted without semantic changes from selected_adapter.rs at 98440154.
use mlx_native_affine::{
    family,
    fixture::HostTensor,
    refusal::{check_qmm, DeviceFacts},
};
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
