/* The random module's default generator: xoshiro256**, one per thread, seeded from
   the OS on first use. random.silly's Rng runs the same algorithm in Silly. */
#include <stdio.h>
#include <time.h>
#include <unistd.h>

static _Thread_local uint64_t rnd_s[4];
static _Thread_local bool rnd_ready;

static uint64_t rnd_splitmix(uint64_t *x) {
    uint64_t z = (*x += 0x9E3779B97F4A7C15ull);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
    return z ^ (z >> 31);
}

static void rnd_seed(int64_t seed) {
    uint64_t x = (uint64_t)seed;
    for (int i = 0; i < 4; i++) rnd_s[i] = rnd_splitmix(&x);
    rnd_ready = true;
}

/* Fills buf with n bytes from the OS (/dev/urandom); false if unavailable. */
static bool rnd_os_bytes(uint8_t *buf, size_t n) {
    FILE *f = fopen("/dev/urandom", "rb");
    if (!f) return false;
    size_t got = fread(buf, 1, n, f);
    fclose(f);
    return got == n;
}

static int64_t rnd_os_u64(void) {
    uint64_t v;
    if (!rnd_os_bytes((uint8_t *)&v, sizeof v)) {
        struct timespec ts;
        clock_gettime(CLOCK_REALTIME, &ts);
        uint64_t x = (uint64_t)ts.tv_nsec ^ ((uint64_t)ts.tv_sec << 20) ^ ((uint64_t)getpid() << 40) ^ (uint64_t)(uintptr_t)&ts;
        v = rnd_splitmix(&x);
    }
    return (int64_t)v;
}

static inline uint64_t rnd_rotl(uint64_t x, int k) { return (x << k) | (x >> (64 - k)); }

static int64_t rnd_next(void) {
    if (!rnd_ready) rnd_seed(rnd_os_u64());
    uint64_t *s = rnd_s;
    uint64_t r = rnd_rotl(s[1] * 5, 7) * 9, t = s[1] << 17;
    s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3];
    s[2] ^= t; s[3] = rnd_rotl(s[3], 45);
    return (int64_t)r;
}
