/* SPDX-License-Identifier: MIT
 * Standard GPU2 bring-up only. Run the DDR audit before --enable.
 * Port mask comes from generated hps.pre.xml F2SDRAM_RESET_PORT_USED.
 * Register definition: Cyclone V HPS TRM, SDR fpgaportrst, 0xFFC25080.
 */
#define _FILE_OFFSET_BITS 64
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <unistd.h>

extern int gpu_mmio_read32(void *, size_t, size_t, uint32_t *);
extern int gpu_mmio_write32(void *, size_t, size_t, uint32_t);

int main(int argc, char **argv)
{
    int enable = argc == 2 && !strcmp(argv[1], "--enable");
    int fd = -1, lock = -1, result = 1;
    void *sdr = MAP_FAILED, *gpu = MAP_FAILED;
    uint32_t before = 0, after = 0, id = 0, abi = 0, status = 0;
    const uint32_t required = 0x1ffu;
    if (argc != 2 || (!enable && strcmp(argv[1], "--inspect"))) {
        fprintf(stderr, "Usage: %s --inspect|--enable (GPU2 + audited DDR required)\n", argv[0]);
        return 2;
    }
    lock = open("/run/lock/de10-gpu-platform.lock", O_RDWR | O_CREAT, 0600);
    if (lock < 0 || flock(lock, LOCK_EX | LOCK_NB)) {
        fprintf(stderr, "exclusive GPU lock unavailable\n"); goto done;
    }
    fd = open("/dev/mem", (enable ? O_RDWR : O_RDONLY) | O_SYNC);
    if (fd < 0) { perror("/dev/mem"); goto done; }
    sdr = mmap(NULL, 4096, PROT_READ | (enable ? PROT_WRITE : 0), MAP_SHARED, fd, 0xffc25000ULL);
    if (sdr == MAP_FAILED || gpu_mmio_read32(sdr, 4096, 0x80, &before)) {
        fprintf(stderr, "cannot read SDR port control\n"); goto done;
    }
    after = before;
    if (enable) {
        gpu = mmap(NULL, 4096, PROT_READ, MAP_SHARED, fd, 0xff240000ULL);
        if (gpu == MAP_FAILED || gpu_mmio_read32(gpu, 4096, 0, &id) ||
            gpu_mmio_read32(gpu, 4096, 4, &abi) || gpu_mmio_read32(gpu, 4096, 8, &status) ||
            id != 0x47505532u || abi != 2 || status != 0) {
            fprintf(stderr, "idle GPU2 ABI2 required; no port control written\n"); goto done;
        }
        if (gpu_mmio_write32(sdr, 4096, 0x80, before | required) ||
            gpu_mmio_read32(sdr, 4096, 0x80, &after) || after != (before | required)) {
            fprintf(stderr, "SDR port enable readback failed\n"); goto done;
        }
    }
    printf("{\"register\":\"0xffc25080\",\"before\":%u,\"after\":%u,\"required\":%u,\"enabled\":%s}\n",
           before, after, required, (after & required) == required ? "true" : "false");
    result = 0;
done:
    if (gpu != MAP_FAILED) munmap(gpu, 4096);
    if (sdr != MAP_FAILED) munmap(sdr, 4096);
    if (fd >= 0) close(fd);
    if (lock >= 0) close(lock);
    return result;
}
