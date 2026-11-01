//! Fixed prospective M1b engineering screen; not statistical confidence.
pub const WARMUPS: usize = 4;
pub const FILL: usize = 128;
pub const RESIDENT: usize = 4096;
pub const FILL_RETRY: usize = 512;
pub const RESIDENT_RETRY: usize = 16384;
pub const FLOOR_SECONDS: f64 = 0.250;
pub const DEADLINE_SECONDS: u64 = 1800;
fn median(v: &[f64]) -> Result<f64, &'static str> {
    if v.is_empty() || v.iter().any(|x| !x.is_finite()) {
        return Err("invalid-sample");
    }
    let mut x = v.to_vec();
    x.sort_by(f64::total_cmp);
    Ok((x[(x.len() - 1) / 2] + x[x.len() / 2]) / 2.0)
}
pub fn noise(t: [f64; 6], duration: [f64; 6]) -> Result<f64, &'static str> {
    if t.iter().any(|x| *x <= 0.0)
        || duration
            .iter()
            .any(|x| !x.is_finite() || *x < FLOOR_SECONDS)
    {
        return Err("unsuitable-baseline");
    }
    let m = median(&t)?;
    let deviations = t.map(|x| (x - m).abs());
    let pairs = [0, 2, 4].map(|i| 2.0 * (t[i] - t[i + 1]).abs() / (t[i] + t[i + 1]));
    let e = 0.01f64
        .max(2.0 * 1.4826 * median(&deviations)? / m)
        .max(median(&pairs)?);
    if e > 0.02 {
        return Err("unsuitable-baseline");
    }
    Ok(e)
}
#[derive(Debug, PartialEq, Eq)]
pub enum Screen {
    Pass,
    Stop,
    Followup,
}
pub fn primary(g: [f64; 3], e: f64) -> Result<Screen, &'static str> {
    let m = median(&g)?;
    if !(0.01..=0.02).contains(&e) {
        return Err("unfrozen-noise");
    }
    Ok(if m >= 0.05 && g.iter().all(|x| *x > e) {
        Screen::Pass
    } else if g.iter().all(|x| *x < 0.05) || m < -e {
        Screen::Stop
    } else {
        Screen::Followup
    })
}
pub fn followup(g: [f64; 6], e: f64) -> Result<bool, &'static str> {
    if !(0.01..=0.02).contains(&e) {
        return Err("unfrozen-noise");
    }
    Ok(median(&g)? >= 0.05 && g.iter().filter(|x| **x > e).count() >= 5)
}
pub fn resident(regressions: [f64; 3], e: f64) -> Result<bool, &'static str> {
    if !(0.01..=0.02).contains(&e) {
        return Err("unfrozen-noise");
    }
    Ok(median(&regressions)? <= e)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fixed_threshold_edges() {
        assert_eq!(primary([0.05, 0.06, 0.04], 0.01).unwrap(), Screen::Pass);
        assert_eq!(primary([0.04; 3], 0.01).unwrap(), Screen::Stop);
        assert_eq!(primary([0.06, 0.0, 0.04], 0.01).unwrap(), Screen::Followup);
        assert!(!followup([0.1, 0.1, 0.1, 0.1, 0.0, 0.0], 0.01).unwrap());
        assert!(resident([0.01; 3], 0.01).unwrap());
    }
    #[test]
    fn unsuitable_baseline_never_releases_candidate() {
        assert_eq!(noise([1.0; 6], [0.25; 6]).unwrap(), 0.01);
        assert!(noise([1.0; 6], [0.24; 6]).is_err());
        assert!(noise([1.0, 1.2, 1.0, 1.2, 1.0, 1.2], [1.0; 6]).is_err());
        assert!(noise([f64::NAN; 6], [1.0; 6]).is_err());
    }
}
