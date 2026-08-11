//! Deterministic qualification-only arithmetic for Feature 017.
//!
//! This module is a semantic scaffold, not a production fallback. Its matvec
//! deliberately preserves the independent oracle's strict increasing-column
//! order and forces a distinct f32 rounding boundary after every multiply and
//! add. Production execution must select its own mode explicitly.

pub const EXACT_SCAFFOLD_VERSION: &str = "f017-exact-f32-sequential-v1";
pub const TIER_B_CONTRACT_VERSION: &str = "f017-production-expert-tier-b-v1";
const F32_UNIT_ROUNDOFF: f64 = 5.960_464_477_539_063e-8;
const F32_SMALLEST_SUBNORMAL: f64 = 1.401_298_464_324_817e-45;

#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct FirstDivergence {
    pub index: usize,
    pub expected: f32,
    pub expected_bits_hex: String,
    pub actual: f32,
    pub actual_bits_hex: String,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct NumericalMetrics {
    pub element_count: usize,
    pub bit_mismatch_count: usize,
    pub signed_zero_mismatch_count: usize,
    pub non_finite_count: usize,
    pub max_abs_error: f64,
    pub max_relative_error: Option<f64>,
    pub rmse: f64,
    pub cosine_similarity: Option<f64>,
    pub first_divergence: Option<FirstDivergence>,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct TierBRowQualification {
    pub index: usize,
    pub l1_products: f64,
    pub absolute_bound: f64,
    pub absolute_error: f64,
    pub relative_bound: Option<f64>,
    pub relative_error: Option<f64>,
    pub passes: bool,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct TierBQualification {
    pub contract_version: &'static str,
    pub metrics: NumericalMetrics,
    pub rows: Vec<TierBRowQualification>,
    pub rmse_bound: f64,
    pub cosine_minimum: Option<f64>,
    pub passes: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum QualificationError {
    EmptyShape,
    ShapeOverflow,
    MatrixLength,
    VectorLength,
    OutputLength,
    ActivationLength,
}

impl std::fmt::Display for QualificationError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let message = match self {
            Self::EmptyShape => "qualification matvec dimensions must be nonzero",
            Self::ShapeOverflow => "qualification matvec dimensions overflow",
            Self::MatrixLength => "qualification matrix length differs from rows * columns",
            Self::VectorLength => "qualification vector length differs from columns",
            Self::OutputLength => "qualification output length differs from rows",
            Self::ActivationLength => "qualification gate/up/hidden lengths differ",
        };
        formatter.write_str(message)
    }
}

impl std::error::Error for QualificationError {}

/// Compute one f32 matrix-vector product in strict increasing-column order.
///
/// The caller owns every buffer. The scaffold performs no allocation, uses no
/// MLX operation, has no fallback, and never changes the reduction order.
pub fn exact_matvec_f32(
    matrix: &[f32],
    rows: usize,
    columns: usize,
    vector: &[f32],
    output: &mut [f32],
) -> Result<(), QualificationError> {
    if rows == 0 || columns == 0 {
        return Err(QualificationError::EmptyShape);
    }
    let elements = rows
        .checked_mul(columns)
        .ok_or(QualificationError::ShapeOverflow)?;
    if matrix.len() != elements {
        return Err(QualificationError::MatrixLength);
    }
    if vector.len() != columns {
        return Err(QualificationError::VectorLength);
    }
    if output.len() != rows {
        return Err(QualificationError::OutputLength);
    }

    for row in 0..rows {
        let mut total = 0.0_f32;
        for column in 0..columns {
            let product = rounded_mul(matrix[row * columns + column], vector[column]);
            total = rounded_add(total, product);
        }
        output[row] = total;
    }
    Ok(())
}

/// Apply the independent oracle's f32 SiLU(gate) * up semantics elementwise.
pub fn exact_swiglu_f32(
    gate: &[f32],
    up: &[f32],
    hidden: &mut [f32],
) -> Result<(), QualificationError> {
    if gate.len() != up.len() || gate.len() != hidden.len() {
        return Err(QualificationError::ActivationLength);
    }
    for index in 0..gate.len() {
        let negative_gate = rounded_neg(gate[index]);
        let exponential = rounded_exp(negative_gate);
        let denominator = rounded_add(1.0, exponential);
        let silu = rounded_div(gate[index], denominator);
        hidden[index] = rounded_mul(silu, up[index]);
    }
    Ok(())
}

/// Measure a candidate against the exact scaffold without applying a pass
/// threshold. Contract policy is intentionally separate from observation.
pub fn measure_f32(
    expected: &[f32],
    actual: &[f32],
) -> Result<NumericalMetrics, QualificationError> {
    if expected.len() != actual.len() {
        return Err(QualificationError::OutputLength);
    }
    let mut bit_mismatch_count = 0;
    let mut signed_zero_mismatch_count = 0;
    let mut non_finite_count = 0;
    let mut max_abs_error = 0.0_f64;
    let mut max_relative_error: Option<f64> = None;
    let mut sum_squared_error = 0.0_f64;
    let mut dot = 0.0_f64;
    let mut expected_norm_squared = 0.0_f64;
    let mut actual_norm_squared = 0.0_f64;
    let mut first_divergence = None;

    for (index, (&expected_value, &actual_value)) in expected.iter().zip(actual.iter()).enumerate()
    {
        let expected_bits = expected_value.to_bits();
        let actual_bits = actual_value.to_bits();
        if expected_bits != actual_bits {
            bit_mismatch_count += 1;
            first_divergence.get_or_insert_with(|| FirstDivergence {
                index,
                expected: expected_value,
                expected_bits_hex: format!("0x{expected_bits:08x}"),
                actual: actual_value,
                actual_bits_hex: format!("0x{actual_bits:08x}"),
            });
        }
        if expected_value == 0.0
            && actual_value == 0.0
            && expected_value.is_sign_negative() != actual_value.is_sign_negative()
        {
            signed_zero_mismatch_count += 1;
        }
        if !expected_value.is_finite() || !actual_value.is_finite() {
            non_finite_count += 1;
            continue;
        }
        let expected_f64 = f64::from(expected_value);
        let actual_f64 = f64::from(actual_value);
        let error = actual_f64 - expected_f64;
        let absolute_error = error.abs();
        max_abs_error = max_abs_error.max(absolute_error);
        sum_squared_error += error * error;
        if expected_f64 != 0.0 {
            let relative = absolute_error / expected_f64.abs();
            max_relative_error = Some(max_relative_error.unwrap_or(0.0).max(relative));
        }
        dot += expected_f64 * actual_f64;
        expected_norm_squared += expected_f64 * expected_f64;
        actual_norm_squared += actual_f64 * actual_f64;
    }

    let rmse = if expected.is_empty() {
        0.0
    } else {
        (sum_squared_error / expected.len() as f64).sqrt()
    };
    let cosine_similarity = if expected_norm_squared > 0.0 && actual_norm_squared > 0.0 {
        Some(dot / (expected_norm_squared.sqrt() * actual_norm_squared.sqrt()))
    } else {
        None
    };

    Ok(NumericalMetrics {
        element_count: expected.len(),
        bit_mismatch_count,
        signed_zero_mismatch_count,
        non_finite_count,
        max_abs_error,
        max_relative_error,
        rmse,
        cosine_similarity,
        first_divergence,
    })
}

/// Apply the frozen Tier-B v1 down-projection contract.
///
/// This evaluator does not execute a candidate or provide a fallback. The
/// matrix and input must be the exact scaffold operands so the condition-aware
/// forward-error budget is independent of candidate output.
pub fn qualify_tier_b_down(
    matrix: &[f32],
    rows: usize,
    columns: usize,
    vector: &[f32],
    expected: &[f32],
    actual: &[f32],
) -> Result<TierBQualification, QualificationError> {
    if rows == 0 || columns == 0 {
        return Err(QualificationError::EmptyShape);
    }
    let elements = rows
        .checked_mul(columns)
        .ok_or(QualificationError::ShapeOverflow)?;
    if matrix.len() != elements {
        return Err(QualificationError::MatrixLength);
    }
    if vector.len() != columns {
        return Err(QualificationError::VectorLength);
    }
    if expected.len() != rows || actual.len() != rows {
        return Err(QualificationError::OutputLength);
    }
    let operation_count = columns
        .checked_mul(2)
        .ok_or(QualificationError::ShapeOverflow)?;
    let ku = operation_count as f64 * F32_UNIT_ROUNDOFF;
    if ku >= 1.0 {
        return Err(QualificationError::ShapeOverflow);
    }
    let bound_factor = 2.0 * ku / (1.0 - ku);
    let subnormal_floor = 4.0 * columns as f64 * F32_SMALLEST_SUBNORMAL;
    let metrics = measure_f32(expected, actual)?;
    let mut qualifications = Vec::with_capacity(rows);
    let mut squared_bounds = 0.0_f64;

    for row in 0..rows {
        let mut products = Vec::with_capacity(columns);
        for column in 0..columns {
            products.push(
                (f64::from(matrix[row * columns + column]) * f64::from(vector[column])).abs(),
            );
        }
        let l1_products = compensated_sum(&products);
        let absolute_bound = bound_factor * l1_products + subnormal_floor;
        let absolute_error = (f64::from(actual[row]) - f64::from(expected[row])).abs();
        let (relative_bound, relative_error) = if expected[row] == 0.0 {
            (None, None)
        } else {
            (
                Some(absolute_bound / f64::from(expected[row]).abs()),
                Some(absolute_error / f64::from(expected[row]).abs()),
            )
        };
        let finite = expected[row].is_finite() && actual[row].is_finite();
        let signed_zero_matches = !(expected[row] == 0.0
            && actual[row] == 0.0
            && expected[row].is_sign_negative() != actual[row].is_sign_negative());
        let passes = finite && signed_zero_matches && absolute_error <= absolute_bound;
        squared_bounds += absolute_bound * absolute_bound;
        qualifications.push(TierBRowQualification {
            index: row,
            l1_products,
            absolute_bound,
            absolute_error,
            relative_bound,
            relative_error,
            passes,
        });
    }

    let rmse_bound = (squared_bounds / rows as f64).sqrt();
    let expected_norm = expected
        .iter()
        .map(|value| f64::from(*value).powi(2))
        .sum::<f64>()
        .sqrt();
    let bounds_norm = squared_bounds.sqrt();
    let cosine_minimum = if expected_norm > bounds_norm {
        Some((expected_norm - bounds_norm) / (expected_norm + bounds_norm))
    } else {
        None
    };
    let cosine_passes = match (cosine_minimum, metrics.cosine_similarity) {
        (Some(minimum), Some(actual_cosine)) => actual_cosine >= minimum,
        (Some(_), None) => false,
        (None, _) => true,
    };
    let passes = metrics.non_finite_count == 0
        && metrics.signed_zero_mismatch_count == 0
        && qualifications.iter().all(|row| row.passes)
        && metrics.rmse <= rmse_bound
        && cosine_passes;

    Ok(TierBQualification {
        contract_version: TIER_B_CONTRACT_VERSION,
        metrics,
        rows: qualifications,
        rmse_bound,
        cosine_minimum,
        passes,
    })
}

fn compensated_sum(values: &[f64]) -> f64 {
    let mut sum = 0.0_f64;
    let mut compensation = 0.0_f64;
    for value in values {
        let next = sum + value;
        if sum.abs() >= value.abs() {
            compensation += (sum - next) + value;
        } else {
            compensation += (value - next) + sum;
        }
        sum = next;
    }
    sum + compensation
}

// Keeping each operation behind a non-inlined call makes the semantic
// rounding boundaries independently auditable and prevents multiply-add
// contraction across scaffold steps. `to_bits`/`from_bits` also materializes
// the operation's f32 representation without changing it.
#[inline(never)]
fn rounded_mul(left: f32, right: f32) -> f32 {
    f32::from_bits((left * right).to_bits())
}

#[inline(never)]
fn rounded_add(left: f32, right: f32) -> f32 {
    f32::from_bits((left + right).to_bits())
}

#[inline(never)]
fn rounded_div(left: f32, right: f32) -> f32 {
    f32::from_bits((left / right).to_bits())
}

#[inline(never)]
fn rounded_neg(value: f32) -> f32 {
    f32::from_bits((-value).to_bits())
}

#[inline(never)]
fn rounded_exp(value: f32) -> f32 {
    f32::from_bits(value.exp().to_bits())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_malformed_shapes_without_partial_output() {
        let mut output = [17.0_f32; 2];
        assert_eq!(
            exact_matvec_f32(&[], 0, 1, &[1.0], &mut output),
            Err(QualificationError::EmptyShape)
        );
        assert_eq!(
            exact_matvec_f32(&[1.0; 3], 2, 2, &[1.0, 1.0], &mut output),
            Err(QualificationError::MatrixLength)
        );
        assert_eq!(output, [17.0, 17.0]);
        assert_eq!(
            exact_swiglu_f32(&[1.0], &[], &mut [19.0]),
            Err(QualificationError::ActivationLength)
        );
    }

    #[test]
    fn column_order_is_observable_and_deterministic() {
        let matrix = [16_777_216.0_f32, 1.0, -16_777_216.0];
        let vector = [1.0_f32; 3];
        let mut output = [0.0_f32];
        for _ in 0..100 {
            exact_matvec_f32(&matrix, 1, 3, &vector, &mut output).unwrap();
            assert_eq!(output[0].to_bits(), 0.0_f32.to_bits());
        }
    }

    #[test]
    fn metrics_preserve_bits_signed_zero_and_first_divergence() {
        let expected = [0.0_f32, 2.0, -4.0];
        let actual = [-0.0_f32, 2.5, -4.0];
        let metrics = measure_f32(&expected, &actual).unwrap();
        assert_eq!(metrics.bit_mismatch_count, 2);
        assert_eq!(metrics.signed_zero_mismatch_count, 1);
        assert_eq!(metrics.non_finite_count, 0);
        assert_eq!(metrics.max_abs_error, 0.5);
        assert_eq!(metrics.max_relative_error, Some(0.25));
        assert_eq!(metrics.first_divergence.unwrap().index, 0);
    }

    #[test]
    fn tier_b_uses_operand_conditioning_not_observed_candidate_error() {
        let matrix = [16_777_216.0_f32, 1.0, -16_777_216.0];
        let vector = [1.0_f32; 3];
        let expected = [0.0_f32];
        let within = [1.0_f32];
        let qualification =
            qualify_tier_b_down(&matrix, 1, 3, &vector, &expected, &within).unwrap();
        assert!(qualification.passes);
        assert!(qualification.rows[0].absolute_bound > 1.0);

        let beyond = [(qualification.rows[0].absolute_bound * 2.0) as f32];
        let rejected = qualify_tier_b_down(&matrix, 1, 3, &vector, &expected, &beyond).unwrap();
        assert!(!rejected.passes);
    }
}
