/* SPDX-License-Identifier: MIT
 * Inspect Cyclone V SDR protection table using its documented read command.
 * Only writes are readrule|index to 0xffc2509c; writerule bit5 always zero.
 * Never modifies protection entries, port resets, memory, or FPGA commands.
 */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <unistd.h>

extern int gpu_mmio_read32(void *, size_t, size_t, uint32_t *);
extern int gpu_mmio_write32(void *, size_t, size_t, uint32_t);
#define SPAN 4096u
#define READ_RULE 0x40u
#define POOL_START 0x3f400000u
#define POOL_END 0x40000000u

struct rule { uint32_t address, id, data; };

static int read_register(void *map, unsigned offset, uint32_t *value)
{
    int status = gpu_mmio_read32(map, SPAN, offset, value);
    if (status) errno = status;
    return status ? -1 : 0;
}

static int select_rule(void *map, unsigned index)
{
    int status;
    if (index >= 20) { errno = EINVAL; return -1; }
    /* No RMW: bit5 can never be propagated from a register read. */
    status = gpu_mmio_write32(map, SPAN, 0x9c, READ_RULE | index);
    if (status) errno = status;
    return status ? -1 : 0;
}

int main(void)
{
    int lock_fd = -1, mem_fd = -1, result = EXIT_FAILURE, selected = 0;
    void *map = MAP_FAILED;
    uint32_t original_selector = 0, defaults = 0, port_reset = 0;
    struct rule rules[20];
    unsigned index;
    lock_fd = open("/run/lock/de10-gpu-platform.lock", O_RDWR | O_CREAT, 0600);
    if (lock_fd < 0 || flock(lock_fd, LOCK_EX | LOCK_NB)) {
        perror("exclusive producer lock"); goto cleanup;
    }
    mem_fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (mem_fd < 0) { perror("/dev/mem"); goto cleanup; }
    map = mmap(NULL, SPAN, PROT_READ | PROT_WRITE, MAP_SHARED, mem_fd,
               (off_t)UINT64_C(0xffc25000));
    if (map == MAP_FAILED) { perror("HPS SDR page mmap"); goto cleanup; }
    if (read_register(map, 0x9c, &original_selector) ||
        read_register(map, 0x8c, &defaults) || read_register(map, 0x80, &port_reset)) {
        perror("read SDR state"); goto cleanup;
    }
    if ((original_selector & 31u) >= 20u) {
        fprintf(stderr, "unsupported initial rule index; refusing selector writes\n");
        goto cleanup;
    }
    for (index = 0; index < 20; ++index) {
        selected = 1;
        if (select_rule(map, index) || read_register(map, 0x90, &rules[index].address) ||
            read_register(map, 0x94, &rules[index].id) || read_register(map, 0x98, &rules[index].data)) {
            perror("read protection rule"); goto cleanup;
        }
    }
    if (select_rule(map, original_selector & 31u)) {
        perror("restore initial rule selector"); goto cleanup;
    }
    selected = 0;
    printf("{\"source\":\"live-hps-sdr-protection-inspection\","
           "\"table_modified\":false,\"selector_restored\":true,"
           "\"pool_start\":%" PRIu32 ",\"pool_end_exclusive\":%" PRIu32 ","
           "\"original_selector\":%" PRIu32 ",\"port_reset\":%" PRIu32 ","
           "\"port_default\":%" PRIu32 ",\"port0_default_denies\":%s,\"rules\":[\n",
           POOL_START, POOL_END, original_selector, port_reset, defaults,
           (defaults & 1u) ? "true" : "false");
    for (index = 0; index < 20; ++index) {
        uint32_t low = (rules[index].address & 4095u) << 20;
        uint64_t end = ((uint64_t)((rules[index].address >> 12) & 4095u) + 1) << 20;
        unsigned low_id = rules[index].id & 4095u;
        unsigned high_id = (rules[index].id >> 12) & 4095u;
        unsigned valid = (rules[index].data >> 2) & 1u;
        unsigned deny = (rules[index].data >> 13) & 1u;
        unsigned ports = (rules[index].data >> 3) & 1023u;
        unsigned security = rules[index].data & 3u;
        int covers_pool = low <= POOL_START && end >= POOL_END;
        int pool_overlap = low < POOL_END && end > POOL_START;
        int candidate = valid && !deny && (ports & 1u) && covers_pool;
        printf("{\"index\":%u,\"raw_address\":%" PRIu32 ",\"raw_id\":%" PRIu32
               ",\"raw_data\":%" PRIu32 ",\"low_address\":%" PRIu32
               ",\"end_exclusive\":%" PRIu64 ",\"low_id\":%u,\"high_id\":%u,"
               "\"valid\":%s,\"deny\":%s,\"port_mask\":%u,\"security\":%u,"
               "\"port0_pool_allow_candidate\":%s,"
               "\"port0_pool_allow_all_ids_both_security\":%s,"
               "\"port0_pool_allow_id0_secure\":%s,\"port0_pool_deny_overlap\":%s}%s\n",
               index, rules[index].address, rules[index].id, rules[index].data,
               low, end, low_id, high_id, valid ? "true" : "false", deny ? "true" : "false",
               ports, security, candidate ? "true" : "false",
               candidate && low_id == 0 && high_id == 4095 && security >= 2 ? "true" : "false",
               candidate && low_id == 0 && security != 1 ? "true" : "false",
               valid && deny && (ports & 1u) && pool_overlap ? "true" : "false",
               index == 19 ? "" : ",");
    }
    puts("],\"limitation\":\"Allow candidates require review with all matching rules; no effective-access or permanent-reservation claim.\"}");
    result = ferror(stdout) ? EXIT_FAILURE : EXIT_SUCCESS;
cleanup:
    if (selected && map != MAP_FAILED && select_rule(map, original_selector & 31u)) {
        perror("failed to restore initial protection selector");
        result = EXIT_FAILURE;
    }
    if (map != MAP_FAILED) munmap(map, SPAN);
    if (mem_fd >= 0) close(mem_fd);
    if (lock_fd >= 0) close(lock_fd);
    return result;
}
