use std::alloc::{alloc, alloc_zeroed, dealloc, Layout};
use std::fmt;
use std::ptr::{self, NonNull};
use std::sync::{Arc, Mutex};

/// Stable identity for a reusable slot in the allocator.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct SlotId(pub u64);

/// Slot zeroing strategy.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ZeroingPolicy {
    /// No automatic zeroing.
    NoZero,
    /// Zero buffers the first time a slot is allocated.
    ZeroInitialize,
    /// Zero buffer on every acquire.
    ZeroOnAcquire,
}

impl Default for ZeroingPolicy {
    fn default() -> Self {
        Self::NoZero
    }
}

/// Construction policy for the stable slab allocator.
#[derive(Debug, Clone, Copy)]
pub struct StableSlabConfig {
    pub slot_size: usize,
    pub alignment: usize,
    pub max_slots: usize,
    pub zeroing: ZeroingPolicy,
}

impl StableSlabConfig {
    pub const fn new(
        slot_size: usize,
        alignment: usize,
        max_slots: usize,
        zeroing: ZeroingPolicy,
    ) -> Self {
        Self {
            slot_size,
            alignment,
            max_slots,
            zeroing,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct StableSlabTelemetry {
    /// Requested logical bytes requested from the allocator.
    pub requested_bytes: u64,
    /// Number of allocation calls.
    pub requested_slots: u64,
    /// Reserved capacity across all allocated slots.
    pub allocated_bytes: u64,
    /// Alignment configured for slots.
    pub alignment: usize,
    /// Number of stable slots materialized so far.
    pub slot_count: usize,
    /// Times a previously released slot was reused.
    pub reuse_count: u64,
    /// Peak in-use logical residency (`slot_size * in_use_slots`).
    pub peak_logical_residency: usize,
}

#[derive(Debug)]
pub enum SlabAllocatorError {
    InvalidAlignment {
        alignment: usize,
    },
    InvalidSlotSize {
        slot_size: usize,
    },
    InvalidMaxSlots {
        max_slots: usize,
    },
    AllocationPressure {
        requested_slots: usize,
        max_slots: usize,
    },
    InternalSlotMismatch {
        id: SlotId,
        expected: usize,
        actual: usize,
    },
}

impl fmt::Display for SlabAllocatorError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidAlignment { alignment } => {
                write!(formatter, "alignment {alignment} is invalid (must be power-of-two)")
            }
            Self::InvalidSlotSize { slot_size } => {
                write!(formatter, "slot size {slot_size} must be > 0")
            }
            Self::InvalidMaxSlots { max_slots } => {
                write!(formatter, "max_slots {max_slots} must be > 0")
            }
            Self::AllocationPressure {
                requested_slots,
                max_slots,
            } => {
                write!(
                    formatter,
                    "allocation pressure: requested_slots={requested_slots}, max_slots={max_slots}",
                )
            }
            Self::InternalSlotMismatch {
                id,
                expected,
                actual,
            } => {
                write!(
                    formatter,
                    "slot id {:?} mapped to {} but allocator has {} slots",
                    id,
                    expected,
                    actual,
                )
            }
        }
    }
}

struct SlotAllocation {
    ptr: NonNull<u8>,
    cap: usize,
    align: usize,
}

impl SlotAllocation {
    fn new(size: usize, align: usize, zero: bool) -> Option<Self> {
        // Safety: alignment is validated before construction.
        let layout = Layout::from_size_align(size, align).ok()?;
        // Safety: layout was validated.
        let raw = unsafe {
            if zero {
                alloc_zeroed(layout)
            } else {
                alloc(layout)
            }
        };
        Some(Self {
            ptr: NonNull::new(raw)?,
            cap: size,
            align,
        })
    }

    fn zero(&mut self) {
        // Safety: `ptr` is valid for writes by construction.
        unsafe { ptr::write_bytes(self.ptr.as_ptr(), 0, self.cap) }
    }

}

impl Drop for SlotAllocation {
    fn drop(&mut self) {
        // Safety: pointer was allocated with this layout.
        unsafe {
            dealloc(
                self.ptr.as_ptr(),
                Layout::from_size_align(self.cap, self.align).expect("layout validated on allocation"),
            )
        }
    }
}

struct SlotEntry {
    allocation: SlotAllocation,
    in_use: bool,
}

struct StableSlabAllocatorInner {
    config: StableSlabConfig,
    slots: Vec<SlotEntry>,
    free: Vec<SlotId>,
    in_use: usize,
    requested_slots: u64,
    requested_bytes: u64,
    reuse_count: u64,
    peak_logical_residency: usize,
    allocated_bytes: usize,
}

impl StableSlabAllocatorInner {
    fn align_size(&self) -> usize {
        let align_mask = self.config.alignment - 1;
        (self.config.slot_size + align_mask) & !align_mask
    }

    fn telemetry(&self) -> StableSlabTelemetry {
        StableSlabTelemetry {
            requested_bytes: self.requested_bytes,
            requested_slots: self.requested_slots,
            allocated_bytes: self.allocated_bytes as u64,
            alignment: self.config.alignment,
            slot_count: self.slots.len(),
            reuse_count: self.reuse_count,
            peak_logical_residency: self.peak_logical_residency,
        }
    }

    fn validate_id(&self, id: SlotId) -> Result<usize, SlabAllocatorError> {
        let index = id.0.try_into().map_err(|_| SlabAllocatorError::InternalSlotMismatch {
            id,
            expected: self.slots.len(),
            actual: self.slots.len(),
        })?;
        if index >= self.slots.len() {
            return Err(SlabAllocatorError::InternalSlotMismatch {
                id,
                expected: self.slots.len(),
                actual: self.slots.len(),
            });
        }
        Ok(index)
    }

    fn release(&mut self, id: SlotId) -> Result<(), SlabAllocatorError> {
        let index = self.validate_id(id)?;
        let slot = &mut self.slots[index];
        if !slot.in_use {
            return Err(SlabAllocatorError::InternalSlotMismatch {
                id,
                expected: index,
                actual: index,
            });
        }
        slot.in_use = false;
        self.in_use -= 1;
        self.free.push(id);
        Ok(())
    }
}

/// Stable slot with deterministic ID and stable page-aligned virtual address.
pub struct StableSlab {
    id: SlotId,
    ptr: NonNull<u8>,
    len: usize,
    allocator: Arc<Mutex<StableSlabAllocatorInner>>,
}

impl StableSlab {
    pub fn id(&self) -> SlotId {
        self.id
    }

    pub fn as_ptr(&self) -> *mut u8 {
        self.ptr.as_ptr()
    }

    pub fn as_slice(&self) -> &[u8] {
        // Safety: pointer is valid and length is fixed for this slot lifecycle.
        unsafe { std::slice::from_raw_parts(self.ptr.as_ptr(), self.len) }
    }

    pub fn as_mut_slice(&mut self) -> &mut [u8] {
        // Safety: pointer is valid and unique to this borrow.
        unsafe { std::slice::from_raw_parts_mut(self.ptr.as_ptr(), self.len) }
    }

    pub fn len(&self) -> usize {
        self.len
    }
}

impl Drop for StableSlab {
    fn drop(&mut self) {
        if let Ok(mut inner) = self.allocator.lock() {
            let _ = inner.release(self.id);
        }
    }
}

/// Reusable page-aligned slot allocator with bounded capacity and deterministic reuse.
#[derive(Clone)]
pub struct StableSlabAllocator {
    inner: Arc<Mutex<StableSlabAllocatorInner>>,
}

impl StableSlabAllocator {
    pub fn new(config: StableSlabConfig) -> Result<Self, SlabAllocatorError> {
        if config.slot_size == 0 {
            return Err(SlabAllocatorError::InvalidSlotSize {
                slot_size: config.slot_size,
            });
        }
        if config.max_slots == 0 {
            return Err(SlabAllocatorError::InvalidMaxSlots {
                max_slots: config.max_slots,
            });
        }
        if config.alignment == 0 || !config.alignment.is_power_of_two() {
            return Err(SlabAllocatorError::InvalidAlignment {
                alignment: config.alignment,
            });
        }

        Ok(Self {
            inner: Arc::new(Mutex::new(StableSlabAllocatorInner {
                config,
                slots: Vec::new(),
                free: Vec::new(),
                in_use: 0,
                requested_slots: 0,
                requested_bytes: 0,
                reuse_count: 0,
                peak_logical_residency: 0,
                allocated_bytes: 0,
            })),
        })
    }

    fn with_inner<R>(
        &self,
        op: impl FnOnce(&mut StableSlabAllocatorInner) -> R,
    ) -> R {
        let mut inner = self.inner.lock().expect("stable slab allocator mutex poisoned");
        op(&mut inner)
    }

    pub fn telemetry(&self) -> StableSlabTelemetry {
        self.with_inner(|inner| inner.telemetry())
    }

    pub fn acquire(&self) -> Result<StableSlab, SlabAllocatorError> {
        self.with_inner(|inner| {
            let request_size = inner.config.slot_size;
            inner.requested_slots += 1;
            inner.requested_bytes += request_size as u64;

            let id = if let Some(reused) = inner.free.pop() {
                inner.reuse_count += 1;
                reused
            } else if inner.slots.len() < inner.config.max_slots {
                let cap = inner.align_size();
                let mut allocation = SlotAllocation::new(
                    cap,
                    inner.config.alignment,
                    inner.config.zeroing == ZeroingPolicy::ZeroInitialize,
                )
                .ok_or(SlabAllocatorError::AllocationPressure {
                    requested_slots: inner.slots.len() + 1,
                    max_slots: inner.config.max_slots,
                })?;

                if inner.config.zeroing == ZeroingPolicy::ZeroOnAcquire {
                    allocation.zero();
                }

                inner.slots.push(SlotEntry {
                    allocation,
                    in_use: false,
                });
                inner.allocated_bytes += cap;

                SlotId(inner.slots.len() as u64 - 1)
            } else {
                return Err(SlabAllocatorError::AllocationPressure {
                    requested_slots: inner.slots.len() + 1,
                    max_slots: inner.config.max_slots,
                });
            };

            let index = usize::try_from(id.0)
                .map_err(|_| SlabAllocatorError::AllocationPressure {
                    requested_slots: inner.slots.len() + 1,
                    max_slots: inner.config.max_slots,
                })?;
            if index >= inner.slots.len() {
                return Err(SlabAllocatorError::InternalSlotMismatch {
                    id,
                    expected: inner.slots.len(),
                    actual: index,
                });
            }

            let slot = &mut inner.slots[index];
            if slot.in_use {
                return Err(SlabAllocatorError::InternalSlotMismatch {
                    id,
                    expected: index,
                    actual: index,
                });
            }
            slot.in_use = true;
            inner.in_use += 1;
            if inner.config.zeroing == ZeroingPolicy::ZeroOnAcquire {
                slot.allocation.zero();
            }

            let requested_in_use = inner.in_use;
            let current_peak = requested_in_use
                .saturating_mul(inner.config.slot_size)
                .max(inner.peak_logical_residency);
            inner.peak_logical_residency = current_peak;

            Ok(StableSlab {
                id,
                ptr: slot.allocation.ptr,
                len: inner.config.slot_size,
                allocator: self.inner.clone(),
            })
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_invalid_configuration() {
        assert!(matches!(
            StableSlabAllocator::new(StableSlabConfig::new(0, 4096, 4, ZeroingPolicy::NoZero)),
            Err(SlabAllocatorError::InvalidSlotSize { .. })
        ));
        assert!(matches!(
            StableSlabAllocator::new(StableSlabConfig::new(4, 0, 4, ZeroingPolicy::NoZero)),
            Err(SlabAllocatorError::InvalidAlignment { .. })
        ));
        assert!(matches!(
            StableSlabAllocator::new(StableSlabConfig::new(4, 3, 4, ZeroingPolicy::NoZero)),
            Err(SlabAllocatorError::InvalidAlignment { .. })
        ));
        assert!(matches!(
            StableSlabAllocator::new(StableSlabConfig::new(4, 4096, 0, ZeroingPolicy::NoZero)),
            Err(SlabAllocatorError::InvalidMaxSlots { .. })
        ));
    }

    #[test]
    fn allocates_and_reuses_stable_slots() {
        let allocator = StableSlabAllocator::new(StableSlabConfig::new(
            128,
            4096,
            2,
            ZeroingPolicy::ZeroOnAcquire,
        ))
        .expect("allocator");
        let mut first = allocator.acquire().expect("first slot");
        let mut second = allocator.acquire().expect("second slot");

        assert_eq!(first.len(), 128);
        assert_eq!(second.len(), 128);
        assert_eq!(first.id().0 + 1, second.id().0);
        assert_eq!((first.as_ptr() as usize) % 4096, 0);
        assert_eq!((second.as_ptr() as usize) % 4096, 0);

        first.as_mut_slice()[0] = 7;
        second.as_mut_slice()[0] = 9;
        let first_ptr = first.as_ptr();
        drop(first);

        let third = allocator.acquire().expect("reuse first released slot");
        assert_eq!(third.len(), 128);
        // deterministic reuse: LIFO list -> most recently released slot reused
        assert_eq!(third.id(), SlotId(0));
        assert_eq!(third.as_ptr(), first_ptr);

        drop(second);
        drop(third);

        assert_eq!(allocator.telemetry().slot_count, 2);
        assert_eq!(allocator.telemetry().reuse_count, 1);
        assert_eq!(allocator.telemetry().requested_slots, 3);
        assert_eq!(allocator.telemetry().requested_bytes, 128 * 3);
        assert_eq!(allocator.telemetry().peak_logical_residency, 256);
        assert_eq!(allocator.telemetry().allocated_bytes, 2 * 4096);
    }

    #[test]
    fn zeroing_on_acquire_keeps_clean_surface_for_resused_slots() {
        let allocator = StableSlabAllocator::new(StableSlabConfig::new(
            16,
            4096,
            1,
            ZeroingPolicy::ZeroOnAcquire,
        ))
        .expect("allocator");
        {
            let mut slot = allocator.acquire().expect("slot");
            slot.as_mut_slice().fill(0xEE);
        }

        let slot = allocator.acquire().expect("reacquired slot");
        assert!(slot.as_slice().iter().all(|value| *value == 0));
    }

    #[test]
    fn errors_cleanly_on_allocation_pressure() {
        let allocator = StableSlabAllocator::new(StableSlabConfig::new(64, 4096, 1, ZeroingPolicy::NoZero))
            .expect("allocator");
        let _first = allocator.acquire().expect("bounded slot");

        match allocator.acquire() {
            Err(SlabAllocatorError::AllocationPressure { max_slots, .. }) => {
                assert_eq!(max_slots, 1);
            }
            _ => panic!("expected allocation pressure"),
        }
    }
}
