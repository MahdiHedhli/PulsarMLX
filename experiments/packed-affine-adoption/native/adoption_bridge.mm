// Platform queries only. Production ABI/accounting are shared with host tests.
#import <Metal/Metal.h>
#include "adoption_bridge_core.h"
extern "C" size_t pa_page() { return static_cast<size_t>(sysconf(_SC_PAGESIZE)); }
extern "C" size_t pa_max_buffer() { @autoreleasepool { id<MTLDevice> d=MTLCreateSystemDefaultDevice();return d ? d.maxBufferLength : 0; } }
