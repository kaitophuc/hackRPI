/* SPDX-License-Identifier: MIT
 * Aligned volatile MMIO for the ARM HPS. Mapping attributes are the caller's
 * responsibility: this cannot turn a cached /dev/mem mapping into Device memory.
 */
#include <errno.h>
#include <stddef.h>
#include <stdint.h>

#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "GPU1 requires a little-endian CPU"
#endif

static inline void io_barrier(void)
{
#if defined(__arm__) || defined(__aarch64__)
    __asm__ __volatile__("dmb sy" ::: "memory");
#elif defined(__i386__) || defined(__x86_64__)
    /* Useful for native normal-memory tests; the target platform is ARM. */
    __asm__ __volatile__("mfence" ::: "memory");
#else
#error "Add and verify device-memory barriers for this architecture"
#endif
}

static int validate(void *base, size_t span, size_t offset)
{
    if (base == NULL || ((uintptr_t)base & 3u) || (offset & 3u))
        return EINVAL;
    if (span < sizeof(uint32_t) || offset > span - sizeof(uint32_t))
        return ERANGE;
    if ((uintptr_t)base > UINTPTR_MAX - offset)
        return ERANGE;
    return 0;
}

int gpu_mmio_read32(void *base, size_t span, size_t offset, uint32_t *value)
{
    int error = validate(base, span, offset);
    if (error || value == NULL)
        return error ? error : EINVAL;
    volatile uint32_t *target = (volatile uint32_t *)((uintptr_t)base + offset);
    io_barrier();
    uint32_t result = *target;
    io_barrier();
    *value = result;
    return 0;
}

int gpu_mmio_write32(void *base, size_t span, size_t offset, uint32_t value)
{
    int error = validate(base, span, offset);
    if (error)
        return error;
    volatile uint32_t *target = (volatile uint32_t *)((uintptr_t)base + offset);
    io_barrier();
    *target = value;
    io_barrier();
    return 0;
}

#ifdef GPU_MMIO_SELF_TEST
#include <assert.h>
#include <stdio.h>
int main(void)
{
    uint32_t words[2] = {0x12345678u, 0u}, value = 0u;
    assert(gpu_mmio_read32(words, sizeof(words), 0, &value) == 0);
    assert(value == 0x12345678u);
    assert(gpu_mmio_write32(words, sizeof(words), 4, 0x89abcdefu) == 0);
    assert(words[1] == 0x89abcdefu);
    assert(gpu_mmio_read32(words, sizeof(words), 1, &value) == EINVAL);
    assert(gpu_mmio_read32(words, sizeof(words), 8, &value) == ERANGE);
    assert(gpu_mmio_read32(NULL, sizeof(words), 0, &value) == EINVAL);
    assert(gpu_mmio_read32(words, 0, 0, &value) == ERANGE);
    assert(gpu_mmio_read32(words, sizeof(words), 0, NULL) == EINVAL);
    assert(gpu_mmio_write32((char *)words + 1, sizeof(words), 0, 0) == EINVAL);
    puts("PASS: native accessor normal-memory/bounds tests; not hardware MMIO evidence");
    return 0;
}
#endif
