/* SPDX-License-Identifier: MIT
 * Read-only GPU2/full-bridge probe with durable pre-access evidence.
 * Does not enable DDR ports or submit rendering commands.
 */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <termios.h>
#include <unistd.h>
extern int gpu_mmio_read32(void *, size_t, size_t, uint32_t *);

static int stage(const char *message)
{
    int descriptor = open("/root/de10_gpu_platform/sst-probe-stage.txt", O_WRONLY|O_CREAT|O_TRUNC, 0600);
    if (descriptor < 0) return -1;
    size_t length = 0;
    while (message[length]) ++length;
    int failed = write(descriptor, message, length) != (ssize_t)length || fsync(descriptor);
    close(descriptor);
    fprintf(stderr, "SST_PROBE %s\n", message);
    fflush(stderr);
    if (isatty(STDERR_FILENO)) tcdrain(STDERR_FILENO);
    return failed ? -1 : 0;
}

int main(void)
{
    int lock = open("/run/lock/de10-gpu-platform.lock", O_RDWR|O_CREAT, 0600);
    if (lock < 0 || flock(lock, LOCK_EX|LOCK_NB)) { perror("GPU lock"); return 1; }
    int descriptor = open("/dev/mem", O_RDONLY|O_SYNC);
    if (descriptor < 0) { perror("/dev/mem"); return 1; }
    void *control = mmap(NULL, 4096, PROT_READ, MAP_SHARED, descriptor, 0xff240000ULL);
    uint32_t id = 0, abi = 0, value = 0;
    if (control == MAP_FAILED || stage("before GPU2 identity") ||
        gpu_mmio_read32(control, 4096, 0, &id) || gpu_mmio_read32(control, 4096, 4, &abi) ||
        id != 0x47505532u || abi != 2) {
        fprintf(stderr, "GPU2 identity mismatch: %08x ABI %u\n", id, abi); return 1;
    }
    void *sst = mmap(NULL, 4096, PROT_READ, MAP_SHARED, descriptor, 0xc0000000ULL);
    if (sst == MAP_FAILED) { perror("SST mmap"); return 1; }
    if (stage("before full bridge local debug read C0000254")) return 1;
    if (gpu_mmio_read32(sst, 4096, 0x254, &value)) return 1;
    fprintf(stderr, "SST_DEBUG=%08x\n", value);
    if (stage("full bridge local debug read completed")) return 1;
    printf("{\"source\":\"hardware\",\"local_debug\":%u}\n", value);
    munmap(sst, 4096); munmap(control, 4096); close(descriptor); close(lock);
    return value & 7u ? 1 : 0;
}
