/* SPDX-License-Identifier: MIT
 * Native Linux/HPS framebuffer capture, C99. See docs/interface.md.
 * Build with mmio_access.c; /dev/mem must be mapped Device/uncached by the kernel.
 */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

extern int gpu_mmio_read32(void *, size_t, size_t, uint32_t *);
extern int gpu_mmio_write32(void *, size_t, size_t, uint32_t);

#define FRAME_OFFSET 0x1000u
#define DEFAULT_SPAN 0x27000u

static int parse_u64(const char *text, uint64_t *value)
{
    char *end;
    unsigned long long parsed;
    if (!text[0] || text[0] == '-') return -1;
    errno = 0;
    parsed = strtoull(text, &end, 0);
    if (errno || *end) return -1;
    *value = (uint64_t)parsed;
    return 0;
}

static double monotonic_now(void)
{
    struct timespec stamp;
    if (clock_gettime(CLOCK_MONOTONIC, &stamp) != 0) return -1.0;
    return (double)stamp.tv_sec + (double)stamp.tv_nsec / 1000000000.0;
}

static int read32(void *mapping, size_t span, size_t offset, uint32_t *value)
{
    int error = gpu_mmio_read32(mapping, span, offset, value);
    if (error) {
        fprintf(stderr, "MMIO read rejected offset=0x%zx: %s\n", offset, strerror(error));
        return -1;
    }
    return 0;
}

static int write32(void *mapping, size_t span, size_t offset, uint32_t value)
{
    int error = gpu_mmio_write32(mapping, span, offset, value);
    if (error) {
        fprintf(stderr, "MMIO write rejected offset=0x%zx: %s\n", offset, strerror(error));
        return -1;
    }
    return 0;
}

static void usage(const char *program)
{
    fprintf(stderr,
        "Usage: %s --base PHYSICAL_ADDR [--span BYTES] [--timeout SECONDS]\n"
        "       [--check-pattern] [--stdout | --output FILE] [--lock FILE]\n"
        "Base must match generated hardware; default span0x27000, output frame.rgb565.\n"
        "--stdout emits only raw little-endian RGB565; success JSON goes to stderr.\n",
        program);
}

int main(int argc, char **argv)
{
    uint64_t physical = 0, span64 = DEFAULT_SPAN;
    size_t span, bytes = 0, offset;
    int have_base = 0, to_stdout = 0, explicit_output = 0, check = 0;
    int memory_fd = -1, lock_fd = -1, result = 1, owned_ready = 0;
    void *mapping = MAP_FAILED;
    unsigned char *pixels = NULL;
    FILE *output = NULL;
    const char *output_path = "frame.rgb565";
    const char *lock_path = "/run/lock/de10-gpu-platform.lock";
    uint32_t identity, abi, width, height, stride, format, status;
    uint32_t sequence = 0, cycles = 0, clock_hz = 0, after_sequence, after_status;
    double timeout = 2.0, started, deadline, copy_start, copy_seconds, capture_seconds;
    long page_size;
    int argument;

    for (argument = 1; argument < argc; ++argument) {
        const char *option = argv[argument];
        if (!strcmp(option, "--stdout")) { to_stdout = 1; continue; }
        if (!strcmp(option, "--check-pattern")) { check = 1; continue; }
        if (!strcmp(option, "--help")) { usage(argv[0]); return 0; }
        if (argument + 1 >= argc) { usage(argv[0]); return 2; }
        if (!strcmp(option, "--base")) {
            if (parse_u64(argv[++argument], &physical)) goto invalid_arguments;
            have_base = 1;
        } else if (!strcmp(option, "--span")) {
            if (parse_u64(argv[++argument], &span64)) goto invalid_arguments;
        } else if (!strcmp(option, "--timeout")) {
            char *end;
            errno = 0;
            timeout = strtod(argv[++argument], &end);
            if (errno || *end || !isfinite(timeout) || timeout <= 0) goto invalid_arguments;
        } else if (!strcmp(option, "--output")) {
            output_path = argv[++argument];
            explicit_output = 1;
        } else if (!strcmp(option, "--lock")) {
            lock_path = argv[++argument];
        } else goto invalid_arguments;
    }
    page_size = sysconf(_SC_PAGESIZE);
    if (!have_base || (to_stdout && explicit_output) || page_size <= 0 ||
        physical > UINT32_MAX || physical % (uint64_t)page_size ||
        span64 < FRAME_OFFSET + 4u || span64 > SIZE_MAX ||
        span64 > UINT64_C(0x100000000) || span64 % (uint64_t)page_size ||
        physical > UINT64_C(0x100000000) - span64)
        goto invalid_arguments;
    span = (size_t)span64;

    lock_fd = open(lock_path, O_RDWR | O_CREAT, 0600);
    if (lock_fd < 0) { perror("open advisory lock"); goto done; }
    if (flock(lock_fd, LOCK_EX | LOCK_NB) != 0) { perror("exclusive framebuffer ownership"); goto done; }
    memory_fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (memory_fd < 0) { perror("open /dev/mem"); goto done; }
    mapping = mmap(NULL, span, PROT_READ | PROT_WRITE, MAP_SHARED, memory_fd, (off_t)physical);
    if (mapping == MAP_FAILED) { perror("mmap /dev/mem"); goto done; }

    if (read32(mapping, span, 0, &identity) || read32(mapping, span, 4, &abi)) goto done;
    if (identity != UINT32_C(0x47505531) || abi != 1) {
        fprintf(stderr, "FPGA identity mismatch ID=0x%08" PRIx32 " ABI=%" PRIu32 "\n", identity, abi);
        goto done;
    }
    if (read32(mapping, span, 0x10, &width) || read32(mapping, span, 0x14, &height) ||
        read32(mapping, span, 0x18, &stride) || read32(mapping, span, 0x1c, &format)) goto done;
    if (!width || width > 2048 || (width & 1) || !height || height > 2048 ||
        stride != width * 2 || format != 1 || (uint64_t)stride * height > span - FRAME_OFFSET) {
        fprintf(stderr, "invalid geometry/format or frame exceeds mapped span\n");
        goto done;
    }
    bytes = (size_t)stride * height;
    pixels = malloc(bytes);
    if (!pixels) { perror("allocate private framebuffer"); goto done; }
    started = monotonic_now();
    if (started < 0) { perror("clock_gettime"); goto done; }
    deadline = started + timeout;
    if (read32(mapping, span, 8, &status)) goto done;
    if (status > 2) { fprintf(stderr, "invalid FPGA status=0x%08" PRIx32 "\n", status); goto done; }
    if (!status && write32(mapping, span, 0x0c, 1)) goto done;
    for (;;) {
        double now;
        struct timespec nap = {0, 1000000};
        if (read32(mapping, span, 8, &status)) goto done;
        if (status > 2) { fprintf(stderr, "invalid FPGA status=0x%08" PRIx32 "\n", status); goto done; }
        if (status == 2) { owned_ready = 1; break; }
        now = monotonic_now();
        if (now < 0) { perror("clock_gettime"); goto done; }
        if (now >= deadline) { fprintf(stderr, "FPGA frame timeout status=0x%08" PRIx32 "\n", status); goto done; }
        nanosleep(&nap, NULL);
    }
    if (read32(mapping, span, 0x20, &sequence) || read32(mapping, span, 0x24, &cycles) ||
        read32(mapping, span, 0x28, &clock_hz)) goto done;
    if (!clock_hz) { fprintf(stderr, "invalid zero FPGA clock frequency\n"); goto done; }
    copy_start = monotonic_now();
    if (copy_start < 0) { perror("clock_gettime"); goto done; }
    for (offset = 0; offset < bytes; offset += 4) {
        uint32_t word;
        if (read32(mapping, span, FRAME_OFFSET + offset, &word)) goto done;
        pixels[offset] = (unsigned char)word;
        pixels[offset + 1] = (unsigned char)(word >> 8);
        pixels[offset + 2] = (unsigned char)(word >> 16);
        pixels[offset + 3] = (unsigned char)(word >> 24);
    }
    if (read32(mapping, span, 0x20, &after_sequence) || read32(mapping, span, 8, &after_status)) goto done;
    if (after_sequence != sequence || after_status != 2) {
        fprintf(stderr, "framebuffer ownership violation during copy\n"); goto done;
    }
    copy_seconds = monotonic_now();
    if (copy_seconds < 0) { perror("clock_gettime"); goto done; }
    copy_seconds -= copy_start;
    if (write32(mapping, span, 0x0c, 2)) goto done;
    owned_ready = 0;
    /* Same-device readback orders release before file/pipe/network output. */
    if (read32(mapping, span, 8, &after_status)) goto done;
    if (after_status != 0) { fprintf(stderr, "framebuffer release not acknowledged\n"); goto done; }
    capture_seconds = monotonic_now();
    if (capture_seconds < 0) { perror("clock_gettime"); goto done; }
    capture_seconds -= started;

    /* The framebuffer is already released. Nothing below accesses frame MMIO. */
    if (check) {
        uint32_t x, y;
        for (y = 0; y < height; ++y) for (x = 0; x < width; ++x) {
            size_t pixel_offset = ((size_t)y * width + x) * 2;
            uint32_t expected = ((x & 31) << 11) | ((y & 63) << 5) | ((x ^ y) & 31);
            uint32_t actual = pixels[pixel_offset] | ((uint32_t)pixels[pixel_offset + 1] << 8);
            if (actual != expected) {
                fprintf(stderr, "pattern mismatch (%" PRIu32 ",%" PRIu32 "):0x%04" PRIx32 " expected0x%04" PRIx32 "\n", x, y, actual, expected);
                goto done;
            }
        }
    }
    /* Release process ownership too; slow stdout must not block other producers. */
    if (mapping != MAP_FAILED) { munmap(mapping, span); mapping = MAP_FAILED; }
    if (memory_fd >= 0) { close(memory_fd); memory_fd = -1; }
    if (lock_fd >= 0) { close(lock_fd); lock_fd = -1; }
    output = to_stdout ? stdout : fopen(output_path, "wb");
    if (!output) { perror("open output"); goto done; }
    if (fwrite(pixels, 1, bytes, output) != bytes || fflush(output) != 0) {
        perror("write frame output"); goto done;
    }
    if (!to_stdout) {
        if (fclose(output) != 0) { output = NULL; perror("close output"); goto done; }
        output = NULL;
    }
    fprintf(stderr,
        "{\"source\":\"hardware\",\"sequence\":%" PRIu32 ",\"width\":%" PRIu32
        ",\"height\":%" PRIu32 ",\"bytes\":%zu,\"render_cycles\":%" PRIu32
        ",\"clock_hz\":%" PRIu32 ",\"render_seconds\":%.9f,\"copy_seconds\":%.9f,"
        "\"capture_seconds\":%.9f,\"pattern_checked\":%s}\n",
        sequence, width, height, bytes, cycles, clock_hz,
        (double)cycles / clock_hz, copy_seconds, capture_seconds, check ? "true" : "false");
    result = 0;
done:
    if (owned_ready && mapping != MAP_FAILED) write32(mapping, span, 0x0c, 2);
    if (output && output != stdout) fclose(output);
    free(pixels);
    if (mapping != MAP_FAILED) munmap(mapping, span);
    if (memory_fd >= 0) close(memory_fd);
    if (lock_fd >= 0) close(lock_fd);
    return result;
invalid_arguments:
    usage(argv[0]);
    return 2;
}
