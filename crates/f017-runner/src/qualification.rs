//! Deterministic qualification-only arithmetic for Feature 017.
//!
//! This module is a semantic scaffold, not a production fallback. Its matvec
//! deliberately preserves the independent oracle's strict increasing-column
//! order and forces a distinct f32 rounding boundary after every multiply and
//! add. Production execution must select its own mode explicitly.

pub const EXACT_SCAFFOLD_VERSION: &str = "f017-exact-f32-sequential-v1";

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
}
