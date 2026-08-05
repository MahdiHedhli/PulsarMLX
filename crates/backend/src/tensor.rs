//! Checked backend-neutral tensor and comparison contracts.

use crate::error::{ContractError, ErrorCategory};

const Q8_ZERO_BLOCK_ELEMENTS: u64 = 32;
const Q8_ZERO_BLOCK_BYTES: u64 = 34;
const MAX_ID_CHARS: usize = 256;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DType {
    F16,
    F32,
    I8,
    I32,
    U32,
    Unsupported(String),
}

impl DType {
    fn encoded_width(&self) -> Option<u64> {
        match self {
            Self::F16 => Some(2),
            Self::F32 | Self::I32 | Self::U32 => Some(4),
            Self::I8 => Some(1),
            Self::Unsupported(_) => None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TensorLayout {
    RowMajor,
    GgufFastestFirst,
    Unsupported(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QuantizationId {
    Q8Zero,
    Unsupported(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BroadcastRule {
    None,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SynchronizationRule {
    QueuedOnly,
    EvaluatedOnly,
    EvaluatedAndDeviceSynchronized,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ComparisonMode {
    Exact,
    AbsoluteAndRelative,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NonFinitePolicy {
    Reject,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ComparisonPolicy {
    oracle_id: String,
    mode: ComparisonMode,
    absolute_tolerance: Option<f64>,
    relative_tolerance: Option<f64>,
    non_finite_policy: NonFinitePolicy,
    max_compared_count: u64,
}

impl ComparisonPolicy {
    pub fn exact(
        oracle_id: impl Into<String>,
        non_finite_policy: NonFinitePolicy,
        max_compared_count: u64,
    ) -> Result<Self, ContractError> {
        Self::try_new(
            oracle_id.into(),
            ComparisonMode::Exact,
            None,
            None,
            non_finite_policy,
            max_compared_count,
        )
    }

    pub fn abs_rel(
        oracle_id: impl Into<String>,
        absolute_tolerance: f64,
        relative_tolerance: f64,
        non_finite_policy: NonFinitePolicy,
        max_compared_count: u64,
    ) -> Result<Self, ContractError> {
        Self::try_new(
            oracle_id.into(),
            ComparisonMode::AbsoluteAndRelative,
            Some(absolute_tolerance),
            Some(relative_tolerance),
            non_finite_policy,
            max_compared_count,
        )
    }

    fn try_new(
        oracle_id: String,
        mode: ComparisonMode,
        absolute_tolerance: Option<f64>,
        relative_tolerance: Option<f64>,
        non_finite_policy: NonFinitePolicy,
        max_compared_count: u64,
    ) -> Result<Self, ContractError> {
        validate_id(
            &oracle_id,
            ErrorCategory::InvalidComparison,
            "invalid_oracle_id",
            "comparison oracle identity",
        )?;
        if max_compared_count == 0 {
            return Err(comparison_error(
                "invalid_comparison_bound",
                "comparison element bound must be greater than zero",
            ));
        }

        match mode {
            ComparisonMode::Exact => {
                if absolute_tolerance.is_some() || relative_tolerance.is_some() {
                    return Err(comparison_error(
                        "unexpected_exact_tolerance",
                        "exact comparison cannot declare numeric tolerances",
                    ));
                }
            }
            ComparisonMode::AbsoluteAndRelative => {
                validate_tolerance(absolute_tolerance, "absolute")?;
                validate_tolerance(relative_tolerance, "relative")?;
            }
        }

        Ok(Self {
            oracle_id,
            mode,
            absolute_tolerance,
            relative_tolerance,
            non_finite_policy,
            max_compared_count,
        })
    }

    pub fn oracle_id(&self) -> &str {
        &self.oracle_id
    }

    pub fn mode(&self) -> ComparisonMode {
        self.mode
    }

    pub fn absolute_tolerance(&self) -> Option<f64> {
        self.absolute_tolerance
    }

    pub fn relative_tolerance(&self) -> Option<f64> {
        self.relative_tolerance
    }

    pub fn non_finite_policy(&self) -> NonFinitePolicy {
        self.non_finite_policy
    }

    pub fn max_compared_count(&self) -> u64 {
        self.max_compared_count
    }

    pub fn compare(
        &self,
        expected: &[f64],
        actual: &[f64],
    ) -> Result<ComparisonResult, ContractError> {
        if expected.len() != actual.len() {
            return Err(comparison_error(
                "comparison_cardinality_mismatch",
                "expected and actual comparison cardinalities differ",
            ));
        }
        if expected.is_empty() {
            return Err(comparison_error(
                "empty_comparison",
                "comparison must contain at least one value",
            ));
        }

        let compared_count = u64::try_from(expected.len()).map_err(|_| {
            ContractError::new(
                ErrorCategory::ArithmeticOverflow,
                "comparison_count_overflow",
                "comparison cardinality cannot be represented as u64",
            )
        })?;
        if compared_count > self.max_compared_count {
            return Err(ContractError::new(
                ErrorCategory::ResourceLimit,
                "comparison_bound_exceeded",
                "comparison cardinality exceeds its declared bound",
            ));
        }

        let mut max_absolute_error = 0.0_f64;
        let mut max_relative_error = 0.0_f64;
        let mut first_mismatch = None;

        for (index, (&expected_value, &actual_value)) in
            expected.iter().zip(actual.iter()).enumerate()
        {
            if matches!(self.non_finite_policy, NonFinitePolicy::Reject)
                && (!expected_value.is_finite() || !actual_value.is_finite())
            {
                return Err(comparison_error(
                    "non_finite_comparison_value",
                    "comparison values must be finite under the declared policy",
                ));
            }

            let absolute_error = (actual_value - expected_value).abs();
            let relative_error = if expected_value == 0.0 {
                if absolute_error == 0.0 {
                    0.0
                } else {
                    f64::INFINITY
                }
            } else {
                absolute_error / expected_value.abs()
            };

            max_absolute_error = max_absolute_error.max(absolute_error);
            max_relative_error = max_relative_error.max(relative_error);

            let matched = match self.mode {
                ComparisonMode::Exact => expected_value == actual_value,
                ComparisonMode::AbsoluteAndRelative => {
                    absolute_error <= self.absolute_tolerance.expect("validated policy")
                        || relative_error <= self.relative_tolerance.expect("validated policy")
                }
            };

            if !matched && first_mismatch.is_none() {
                let index = u64::try_from(index).map_err(|_| {
                    ContractError::new(
                        ErrorCategory::ArithmeticOverflow,
                        "comparison_index_overflow",
                        "comparison mismatch index cannot be represented as u64",
                    )
                })?;
                first_mismatch = Some(FirstMismatch {
                    index,
                    expected: expected_value,
                    actual: actual_value,
                    absolute_error,
                    relative_error,
                });
            }
        }

        Ok(ComparisonResult {
            compared_count,
            max_absolute_error: Some(max_absolute_error),
            max_relative_error: Some(max_relative_error),
            passed: first_mismatch.is_none(),
            first_mismatch,
        })
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct FirstMismatch {
    index: u64,
    expected: f64,
    actual: f64,
    absolute_error: f64,
    relative_error: f64,
}

impl FirstMismatch {
    pub fn index(&self) -> u64 {
        self.index
    }

    pub fn expected(&self) -> f64 {
        self.expected
    }

    pub fn actual(&self) -> f64 {
        self.actual
    }

    pub fn absolute_error(&self) -> f64 {
        self.absolute_error
    }

    pub fn relative_error(&self) -> f64 {
        self.relative_error
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct ComparisonResult {
    compared_count: u64,
    max_absolute_error: Option<f64>,
    max_relative_error: Option<f64>,
    passed: bool,
    first_mismatch: Option<FirstMismatch>,
}

impl ComparisonResult {
    pub fn compared_count(&self) -> u64 {
        self.compared_count
    }

    pub fn max_absolute_error(&self) -> Option<f64> {
        self.max_absolute_error
    }

    pub fn max_relative_error(&self) -> Option<f64> {
        self.max_relative_error
    }

    pub fn passed(&self) -> bool {
        self.passed
    }

    pub fn first_mismatch(&self) -> Option<&FirstMismatch> {
        self.first_mismatch.as_ref()
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct TensorDescriptor {
    pub operation_id: String,
    pub logical_shape: Vec<u64>,
    pub storage_shape: Vec<u64>,
    pub layout: TensorLayout,
    pub input_dtype: DType,
    pub accumulation_dtype: DType,
    pub output_dtype: DType,
    pub encoded_byte_count: Option<u64>,
    pub quantization: Option<QuantizationId>,
    pub broadcast_rule: BroadcastRule,
    pub synchronization: SynchronizationRule,
    pub comparison_policy: ComparisonPolicy,
}

#[derive(Debug, Clone, PartialEq)]
pub struct TensorContract {
    descriptor: TensorDescriptor,
    element_count: u64,
}

impl TensorContract {
    pub fn try_new(descriptor: TensorDescriptor) -> Result<Self, ContractError> {
        validate_id(
            &descriptor.operation_id,
            ErrorCategory::InvalidTensor,
            "invalid_operation_id",
            "tensor operation identity",
        )?;
        validate_layout(&descriptor.layout)?;
        validate_dtype(&descriptor.input_dtype, "input")?;
        validate_dtype(&descriptor.accumulation_dtype, "accumulation")?;
        validate_dtype(&descriptor.output_dtype, "output")?;

        let logical_count = checked_shape_product(&descriptor.logical_shape, "logical")?;
        let storage_count = checked_shape_product(&descriptor.storage_shape, "storage")?;
        if logical_count != storage_count {
            return Err(tensor_error(
                "tensor_element_count_mismatch",
                "logical and storage shapes must have the same element count",
            ));
        }

        if descriptor.synchronization != SynchronizationRule::EvaluatedAndDeviceSynchronized {
            return Err(tensor_error(
                "incomplete_synchronization_rule",
                "tensor results require evaluation and device synchronization",
            ));
        }
        if descriptor.comparison_policy.max_compared_count() < logical_count {
            return Err(ContractError::new(
                ErrorCategory::ResourceLimit,
                "tensor_comparison_bound_too_small",
                "comparison bound is smaller than the tensor cardinality",
            ));
        }

        validate_encoded_bytes(&descriptor, logical_count)?;

        Ok(Self {
            descriptor,
            element_count: logical_count,
        })
    }

    pub fn descriptor(&self) -> &TensorDescriptor {
        &self.descriptor
    }

    pub fn operation_id(&self) -> &str {
        &self.descriptor.operation_id
    }

    pub fn logical_shape(&self) -> &[u64] {
        &self.descriptor.logical_shape
    }

    pub fn storage_shape(&self) -> &[u64] {
        &self.descriptor.storage_shape
    }

    pub fn element_count(&self) -> u64 {
        self.element_count
    }

    pub fn layout(&self) -> &TensorLayout {
        &self.descriptor.layout
    }

    pub fn input_dtype(&self) -> &DType {
        &self.descriptor.input_dtype
    }

    pub fn accumulation_dtype(&self) -> &DType {
        &self.descriptor.accumulation_dtype
    }

    pub fn output_dtype(&self) -> &DType {
        &self.descriptor.output_dtype
    }

    pub fn encoded_byte_count(&self) -> Option<u64> {
        self.descriptor.encoded_byte_count
    }

    pub fn quantization(&self) -> Option<&QuantizationId> {
        self.descriptor.quantization.as_ref()
    }

    pub fn broadcast_rule(&self) -> &BroadcastRule {
        &self.descriptor.broadcast_rule
    }

    pub fn synchronization(&self) -> &SynchronizationRule {
        &self.descriptor.synchronization
    }

    pub fn comparison_policy(&self) -> &ComparisonPolicy {
        &self.descriptor.comparison_policy
    }
}

fn checked_shape_product(shape: &[u64], shape_name: &str) -> Result<u64, ContractError> {
    if shape.is_empty() {
        return Err(tensor_error(
            "empty_tensor_shape",
            format!("{shape_name} tensor shape must not be empty"),
        ));
    }

    shape.iter().try_fold(1_u64, |product, &dimension| {
        if dimension == 0 {
            return Err(tensor_error(
                "zero_tensor_dimension",
                format!("{shape_name} tensor dimensions must be nonzero"),
            ));
        }
        product.checked_mul(dimension).ok_or_else(|| {
            ContractError::new(
                ErrorCategory::ArithmeticOverflow,
                "tensor_shape_product_overflow",
                format!("{shape_name} tensor element-count product overflowed"),
            )
        })
    })
}

fn validate_layout(layout: &TensorLayout) -> Result<(), ContractError> {
    match layout {
        TensorLayout::RowMajor | TensorLayout::GgufFastestFirst => Ok(()),
        TensorLayout::Unsupported(_) => Err(tensor_error(
            "unsupported_tensor_layout",
            "tensor layout is not admitted by this contract",
        )),
    }
}

fn validate_dtype(dtype: &DType, role: &str) -> Result<(), ContractError> {
    if matches!(dtype, DType::Unsupported(_)) {
        return Err(tensor_error(
            "unsupported_tensor_dtype",
            format!("{role} tensor dtype is not admitted by this contract"),
        ));
    }
    Ok(())
}

fn validate_encoded_bytes(
    descriptor: &TensorDescriptor,
    element_count: u64,
) -> Result<(), ContractError> {
    let expected = match descriptor.quantization.as_ref() {
        None => {
            let Some(actual) = descriptor.encoded_byte_count else {
                return Ok(());
            };
            let width = descriptor
                .input_dtype
                .encoded_width()
                .expect("unsupported dtypes were rejected");
            let expected = element_count.checked_mul(width).ok_or_else(|| {
                ContractError::new(
                    ErrorCategory::ArithmeticOverflow,
                    "encoded_byte_count_overflow",
                    "dense tensor encoded byte-count calculation overflowed",
                )
            })?;
            return require_exact_byte_count(expected, actual);
        }
        Some(QuantizationId::Q8Zero) => {
            if descriptor.input_dtype != DType::I8 {
                return Err(quantization_error(
                    "invalid_q8_zero_dtype",
                    "Q8_0 encoded tensors must declare signed int8 quant values",
                ));
            }
            let row_width = match descriptor.layout {
                TensorLayout::RowMajor => descriptor.logical_shape.last().copied(),
                TensorLayout::GgufFastestFirst => descriptor.storage_shape.first().copied(),
                TensorLayout::Unsupported(_) => None,
            }
            .expect("validated nonempty shape and supported layout");
            if row_width % Q8_ZERO_BLOCK_ELEMENTS != 0 {
                return Err(quantization_error(
                    "invalid_q8_zero_row_width",
                    "Q8_0 row width must be divisible by 32",
                ));
            }
            let blocks = element_count / Q8_ZERO_BLOCK_ELEMENTS;
            blocks.checked_mul(Q8_ZERO_BLOCK_BYTES).ok_or_else(|| {
                ContractError::new(
                    ErrorCategory::ArithmeticOverflow,
                    "encoded_byte_count_overflow",
                    "Q8_0 tensor encoded byte-count calculation overflowed",
                )
            })?
        }
        Some(QuantizationId::Unsupported(_)) => {
            return Err(quantization_error(
                "unsupported_quantization",
                "tensor quantization is not admitted by this contract",
            ));
        }
    };

    let actual = descriptor.encoded_byte_count.ok_or_else(|| {
        quantization_error(
            "encoded_byte_count_required",
            "quantized tensors require an exact encoded byte count",
        )
    })?;
    require_exact_byte_count(expected, actual)
}

fn require_exact_byte_count(expected: u64, actual: u64) -> Result<(), ContractError> {
    if actual != expected {
        return Err(tensor_error(
            "encoded_byte_count_mismatch",
            "tensor encoded byte count does not match its dtype and shape contract",
        ));
    }
    Ok(())
}

fn validate_id(
    value: &str,
    category: ErrorCategory,
    code: &'static str,
    label: &str,
) -> Result<(), ContractError> {
    let char_count = value.chars().count();
    if value.is_empty()
        || value.trim() != value
        || char_count > MAX_ID_CHARS
        || value.chars().any(char::is_control)
    {
        return Err(ContractError::new(
            category,
            code,
            format!("{label} must be nonempty, bounded, and unambiguous"),
        ));
    }
    Ok(())
}

fn validate_tolerance(value: Option<f64>, name: &str) -> Result<(), ContractError> {
    match value {
        Some(tolerance) if tolerance.is_finite() && tolerance >= 0.0 => Ok(()),
        _ => Err(comparison_error(
            "invalid_comparison_tolerance",
            format!("{name} comparison tolerance must be finite and nonnegative"),
        )),
    }
}

fn tensor_error(code: &'static str, message: impl AsRef<str>) -> ContractError {
    ContractError::new(ErrorCategory::InvalidTensor, code, message)
}

fn quantization_error(code: &'static str, message: impl AsRef<str>) -> ContractError {
    ContractError::new(ErrorCategory::InvalidQuantization, code, message)
}

fn comparison_error(code: &'static str, message: impl AsRef<str>) -> ContractError {
    ContractError::new(ErrorCategory::InvalidComparison, code, message)
}
