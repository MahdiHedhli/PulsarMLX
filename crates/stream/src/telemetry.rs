use std::time::Duration;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TelemetryBucket {
    StorageRead,
    Decode,
    BufferMaterialization,
    BackendBuildImport,
    Compute,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct TelemetrySnapshot {
    pub storage_read_ns: u64,
    pub storage_read_requests: u64,
    pub storage_read_bytes: u64,
    pub decode_ns: u64,
    pub decode_operations: u64,
    pub buffer_materialization_ns: u64,
    pub buffer_materialization_operations: u64,
    pub backend_build_import_ns: u64,
    pub backend_build_import_operations: u64,
    pub compute_ns: u64,
    pub compute_operations: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TelemetryError {
    Uninitialized,
    DurationOverflow,
    CounterOverflow,
    Poisoned,
}

#[derive(Debug, Clone, Copy)]
enum TelemetryState {
    Uninitialized,
    Ready(TelemetrySnapshot),
    Poisoned,
}

#[derive(Debug, Clone, Copy)]
pub struct RuntimeTelemetry {
    state: TelemetryState,
}

impl Default for RuntimeTelemetry {
    fn default() -> Self {
        Self::new()
    }
}

impl RuntimeTelemetry {
    pub fn new() -> Self {
        Self {
            state: TelemetryState::Ready(TelemetrySnapshot::default()),
        }
    }

    pub fn uninitialized() -> Self {
        Self {
            state: TelemetryState::Uninitialized,
        }
    }

    pub fn snapshot(&self) -> Result<TelemetrySnapshot, TelemetryError> {
        match self.state {
            TelemetryState::Ready(snapshot) => Ok(snapshot),
            TelemetryState::Uninitialized => Err(TelemetryError::Uninitialized),
            TelemetryState::Poisoned => Err(TelemetryError::Poisoned),
        }
    }

    pub fn record_storage_read(
        &mut self,
        elapsed: Duration,
        request_count: u64,
        bytes: u64,
    ) -> Result<(), TelemetryError> {
        self.record_stage(TelemetryBucket::StorageRead, elapsed, request_count)?;
        self.add_storage_bytes(bytes)
    }

    pub fn record_stage(
        &mut self,
        bucket: TelemetryBucket,
        elapsed: Duration,
        operations: u64,
    ) -> Result<(), TelemetryError> {
        let elapsed_ns = match elapsed.as_nanos().try_into() {
            Ok(value) => value,
            Err(_) => {
                return self.poison_on_error(Err(TelemetryError::DurationOverflow));
            }
        };
        let result = self.with_snapshot(|snapshot| {
            let (duration, count) = match bucket {
                TelemetryBucket::StorageRead => (
                    &mut snapshot.storage_read_ns,
                    &mut snapshot.storage_read_requests,
                ),
                TelemetryBucket::Decode => {
                    (&mut snapshot.decode_ns, &mut snapshot.decode_operations)
                }
                TelemetryBucket::BufferMaterialization => (
                    &mut snapshot.buffer_materialization_ns,
                    &mut snapshot.buffer_materialization_operations,
                ),
                TelemetryBucket::BackendBuildImport => (
                    &mut snapshot.backend_build_import_ns,
                    &mut snapshot.backend_build_import_operations,
                ),
                TelemetryBucket::Compute => {
                    (&mut snapshot.compute_ns, &mut snapshot.compute_operations)
                }
            };
            *duration = duration
                .checked_add(elapsed_ns)
                .ok_or(TelemetryError::CounterOverflow)?;
            *count = count
                .checked_add(operations)
                .ok_or(TelemetryError::CounterOverflow)?;
            Ok(())
        });
        self.poison_on_error(result)
    }

    pub fn add_storage_bytes(&mut self, bytes: u64) -> Result<(), TelemetryError> {
        let result = self.with_snapshot(|snapshot| {
            snapshot.storage_read_bytes = snapshot
                .storage_read_bytes
                .checked_add(bytes)
                .ok_or(TelemetryError::CounterOverflow)?;
            Ok(())
        });
        self.poison_on_error(result)
    }

    pub fn merge_snapshot(&mut self, other: TelemetrySnapshot) -> Result<(), TelemetryError> {
        let result = self.with_snapshot(|snapshot| {
            macro_rules! add {
                ($field:ident) => {
                    snapshot.$field = snapshot
                        .$field
                        .checked_add(other.$field)
                        .ok_or(TelemetryError::CounterOverflow)?;
                };
            }
            add!(storage_read_ns);
            add!(storage_read_requests);
            add!(storage_read_bytes);
            add!(decode_ns);
            add!(decode_operations);
            add!(buffer_materialization_ns);
            add!(buffer_materialization_operations);
            add!(backend_build_import_ns);
            add!(backend_build_import_operations);
            add!(compute_ns);
            add!(compute_operations);
            Ok(())
        });
        self.poison_on_error(result)
    }

    fn with_snapshot<F>(&mut self, update: F) -> Result<(), TelemetryError>
    where
        F: FnOnce(&mut TelemetrySnapshot) -> Result<(), TelemetryError>,
    {
        match &mut self.state {
            TelemetryState::Ready(snapshot) => update(snapshot),
            TelemetryState::Uninitialized => Err(TelemetryError::Uninitialized),
            TelemetryState::Poisoned => Err(TelemetryError::Poisoned),
        }
    }

    fn poison_on_error(
        &mut self,
        result: Result<(), TelemetryError>,
    ) -> Result<(), TelemetryError> {
        if matches!(
            result,
            Err(TelemetryError::DurationOverflow | TelemetryError::CounterOverflow)
        ) {
            self.state = TelemetryState::Poisoned;
        }
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn buckets_and_storage_counters_are_independent() {
        let mut telemetry = RuntimeTelemetry::new();
        telemetry
            .record_storage_read(Duration::from_nanos(11), 2, 4096)
            .unwrap();
        telemetry
            .record_stage(TelemetryBucket::Decode, Duration::from_nanos(13), 3)
            .unwrap();
        telemetry
            .record_stage(
                TelemetryBucket::BufferMaterialization,
                Duration::from_nanos(17),
                5,
            )
            .unwrap();
        telemetry
            .record_stage(
                TelemetryBucket::BackendBuildImport,
                Duration::from_nanos(19),
                7,
            )
            .unwrap();
        telemetry
            .record_stage(TelemetryBucket::Compute, Duration::from_nanos(23), 11)
            .unwrap();

        assert_eq!(
            telemetry.snapshot().unwrap(),
            TelemetrySnapshot {
                storage_read_ns: 11,
                storage_read_requests: 2,
                storage_read_bytes: 4096,
                decode_ns: 13,
                decode_operations: 3,
                buffer_materialization_ns: 17,
                buffer_materialization_operations: 5,
                backend_build_import_ns: 19,
                backend_build_import_operations: 7,
                compute_ns: 23,
                compute_operations: 11,
            }
        );
    }

    #[test]
    fn layer_snapshots_merge_with_checked_accumulation() {
        let mut first = RuntimeTelemetry::new();
        first
            .record_stage(TelemetryBucket::Decode, Duration::from_nanos(2), 1)
            .unwrap();
        let mut second = RuntimeTelemetry::new();
        second
            .record_stage(TelemetryBucket::Decode, Duration::from_nanos(3), 4)
            .unwrap();
        first.merge_snapshot(second.snapshot().unwrap()).unwrap();
        assert_eq!(first.snapshot().unwrap().decode_ns, 5);
        assert_eq!(first.snapshot().unwrap().decode_operations, 5);
    }

    #[test]
    fn uninitialized_and_overflowed_telemetry_fail_closed() {
        let mut uninitialized = RuntimeTelemetry::uninitialized();
        assert_eq!(
            uninitialized.record_stage(TelemetryBucket::Compute, Duration::ZERO, 1),
            Err(TelemetryError::Uninitialized)
        );
        assert_eq!(uninitialized.snapshot(), Err(TelemetryError::Uninitialized));

        let mut overflowed = RuntimeTelemetry::new();
        overflowed
            .record_stage(
                TelemetryBucket::Compute,
                Duration::from_nanos(u64::MAX),
                u64::MAX,
            )
            .unwrap();
        assert_eq!(
            overflowed.record_stage(TelemetryBucket::Compute, Duration::from_nanos(1), 0),
            Err(TelemetryError::CounterOverflow)
        );
        assert_eq!(
            overflowed.record_stage(TelemetryBucket::Compute, Duration::ZERO, 0),
            Err(TelemetryError::Poisoned)
        );
        assert_eq!(overflowed.snapshot(), Err(TelemetryError::Poisoned));
    }

    #[test]
    fn duration_conversion_overflow_poisoned_state() {
        let mut telemetry = RuntimeTelemetry::new();
        let too_large = Duration::new(u64::MAX, 999_999_999);
        assert_eq!(
            telemetry.record_stage(TelemetryBucket::Decode, too_large, 0),
            Err(TelemetryError::DurationOverflow)
        );
        assert_eq!(telemetry.snapshot(), Err(TelemetryError::Poisoned));
    }
}
