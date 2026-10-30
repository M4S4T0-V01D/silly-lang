/* Silly runtime. Included once into every generated C file.
 *
 * Memory model: there is no heap. All dynamic data (strings, list buffers)
 * lives on the *data stack*, a large reserved-but-lazily-committed mapping.
 * Allocation bumps `sl_ds.top`; the compiler saves and restores `top` at
 * function and loop boundaries so storage is released when its scope ends.
 * A second arena, the *transfer stack*, is used to relocate results of
 * @compact functions below the frame they were built in.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <math.h>
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define SL_LIKELY(x) __builtin_expect(!!(x), 1)
#define SL_UNLIKELY(x) __builtin_expect(!!(x), 0)
#define SL_NORETURN __attribute__((noreturn, cold, noinline))
#define SL_INLINE static inline __attribute__((always_inline))

typedef struct { const uint8_t *p; int64_t n; } sl_str;
typedef struct { void *p; int64_t n, cap; } sl_list;
/* Insertion-ordered hash map: `cap` entries {u64 h; K k; V v;} followed by a u32 index table
   of 2*cap slots (0 = empty, else entry number + 1). Live entries have the top bit of h set;
   removal clears h, so probes step over dead entries without tombstones. */
typedef struct { uint8_t *p; int64_t n, live, cap; } sl_map;
typedef struct { uint8_t *top, *end, *base; } sl_arena;

/* Each thread owns its data stack and transfer stack, so all of these are thread-local. */
static __thread sl_arena sl_ds, sl_xs;
static size_t sl_stack_mb;
static int sl_argc;
static char **sl_argv;

#define SL_ALIGN 8
#define SL_ROUND(n) (((size_t)(n) + (SL_ALIGN - 1)) & ~(size_t)(SL_ALIGN - 1))
#define SL_STR(lit, len) ((sl_str){(const uint8_t *)(lit), (len)})
#define sl_cmp3(a, b) ({ __typeof__(a) _ca = (a); __typeof__(b) _cb = (b); (_ca > _cb) - (_ca < _cb); })

/* ---------- panics ---------- */

SL_NORETURN static void sl_panic_str(const char *loc, sl_str msg) {
    fflush(stdout);
    fprintf(stderr, "panic at %s: %.*s\n", loc, (int)msg.n, (const char *)msg.p);
    exit(101);
}

SL_NORETURN __attribute__((format(printf, 2, 3))) static void sl_panic(const char *loc, const char *fmt, ...) {
    char buf[512];
    __builtin_va_list ap;
    __builtin_va_start(ap, fmt);
    vsnprintf(buf, sizeof buf, fmt, ap);
    __builtin_va_end(ap);
    fflush(stdout);
    fprintf(stderr, "panic at %s: %s\n", loc, buf);
    exit(101);
}

SL_NORETURN static void sl_overflow(void) {
    fflush(stdout);
    fprintf(stderr, "panic: data stack overflow (set SILLY_STACK_MB to reserve more)\n");
    exit(101);
}

/* ---------- arenas ---------- */

static void sl_arena_init(sl_arena *a, size_t want) {
    void *m = MAP_FAILED;
    while (want >= ((size_t)1 << 24)) {
        m = mmap(NULL, want, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
        if (m != MAP_FAILED) break;
        want /= 2;
    }
    if (m == MAP_FAILED) {
        fprintf(stderr, "silly: cannot reserve the data stack\n");
        exit(101);
    }
    a->base = a->top = (uint8_t *)m;
    a->end = a->base + want;
}

static void sl_init(int argc, char **argv) {
    sl_argc = argc;
    sl_argv = argv;
    size_t mb = 32768;
    const char *env = getenv("SILLY_STACK_MB");
    if (env && atol(env) > 0) mb = (size_t)atol(env);
    sl_stack_mb = mb;
    sl_arena_init(&sl_ds, mb << 20);
    sl_arena_init(&sl_xs, (mb / 2) << 20);
    if (!isatty(1)) setvbuf(stdout, NULL, _IOFBF, 1 << 16);
}

/* Scope exit: free everything above p. Debug builds fill the freed bytes with
   0xA5 so that any read of reclaimed storage shows up as garbage. */
#ifdef SL_POISON
#define SL_RESET(p) sl_reset_poison(p)
static void sl_reset_poison(uint8_t *p) {
    if (p < sl_ds.top) memset(p, 0xA5, (size_t)(sl_ds.top - p));
    sl_ds.top = p;
}
#else
#define SL_RESET(p) (sl_ds.top = (p))
#endif

SL_INLINE void *sl_alloc(size_t n) {
    uint8_t *p = sl_ds.top;
    uint8_t *t = p + SL_ROUND(n);
    if (SL_UNLIKELY(t > sl_ds.end)) sl_overflow();
    sl_ds.top = t;
    return p;
}

/* Bytes a loop that carries state may allocate before its first compaction. */
#ifndef SL_CARRY_SLACK
#define SL_CARRY_SLACK ((size_t)256 << 10)
#endif

SL_INLINE void sl_swap_arenas(void) {
    sl_arena t = sl_ds;
    sl_ds = sl_xs;
    sl_xs = t;
}

/* Floored float remainder: the sign follows the divisor, matching `//`. */
SL_INLINE double sl_fmod(double a, double b) {
    double r = fmod(a, b);
    if (r != 0 && ((r < 0) != (b < 0))) r += b;
    return r;
}
SL_INLINE float sl_fmodf(float a, float b) {
    float r = fmodf(a, b);
    if (r != 0 && ((r < 0) != (b < 0))) r += b;
    return r;
}

/* Does storage [p, p+n) overlap the live range [lo, hi)? */
SL_INLINE bool sl_in(const void *p, size_t n, const uint8_t *lo, const uint8_t *hi) {
    const uint8_t *q = (const uint8_t *)p;
    return q < hi && q + n > lo;
}

/* ---------- function values ---------- */
/* A function value is a code pointer plus an optional closure environment on
   the data stack. Environments are immutable once built, so copies of one
   closure share it. The code takes the environment as its first argument. */
typedef struct sl_env {
    uint32_t size;
    void (*reloc)(struct sl_env *env, const uint8_t *lo, const uint8_t *hi);
} sl_env;
typedef struct { void *code; sl_env *env; } sl_fn;

SL_INLINE bool sl_fn_eq(sl_fn a, sl_fn b) { return a.code == b.code && a.env == b.env; }

static void sl_fn_reloc(sl_fn *f, const uint8_t *lo, const uint8_t *hi) {
    sl_env *e = f->env;
    if (!e || !sl_in(e, e->size, lo, hi)) return;
    sl_env *q = (sl_env *)sl_alloc(e->size);
    memcpy(q, e, e->size);
    f->env = q;
    if (q->reloc) q->reloc(q, lo, hi);
}

/* ---------- integers ---------- */

SL_NORETURN static void sl_div_zero(const char *loc) { sl_panic(loc, "division by zero"); }

#define SL_DIV_DEF(T, NAME, MIN)                                                         \
    SL_INLINE T sl_div_##NAME(T a, T b, const char *loc) {                               \
        if (SL_UNLIKELY(b == 0)) sl_div_zero(loc);                                       \
        if (MIN && SL_UNLIKELY(b == (T)-1)) return (T)(0 - (uint64_t)a);                 \
        return a / b;                                                                    \
    }                                                                                    \
    SL_INLINE T sl_mod_##NAME(T a, T b, const char *loc) {                               \
        if (SL_UNLIKELY(b == 0)) sl_div_zero(loc);                                       \
        if (MIN && SL_UNLIKELY(b == (T)-1)) return 0;                                    \
        T r = a % b;                                                                     \
        if (MIN && r != 0 && ((r < 0) != (b < 0))) r += b;                               \
        return r;                                                                        \
    }                                                                                    \
    SL_INLINE T sl_fdiv_##NAME(T a, T b, const char *loc) {                              \
        T q = sl_div_##NAME(a, b, loc);                                                  \
        if (MIN && (a % b != 0) && ((a < 0) != (b < 0))) q--;                            \
        return q;                                                                        \
    }                                                                                    \
    SL_INLINE T sl_pow_##NAME(T a, T e, const char *loc) {                               \
        if (MIN && e < 0) sl_panic(loc, "negative exponent in integer power");           \
        T r = 1;                                                                         \
        while (e) {                                                                      \
            if (e & 1) r = (T)(r * a);                                                   \
            e >>= 1;                                                                     \
            a = (T)(a * a);                                                              \
        }                                                                                \
        return r;                                                                        \
    }
SL_DIV_DEF(int8_t, i8, 1)
SL_DIV_DEF(int16_t, i16, 1)
SL_DIV_DEF(int32_t, i32, 1)
SL_DIV_DEF(int64_t, i64, 1)
SL_DIV_DEF(uint8_t, u8, 0)
SL_DIV_DEF(uint16_t, u16, 0)
SL_DIV_DEF(uint32_t, u32, 0)
SL_DIV_DEF(uint64_t, u64, 0)

/* Saturating float -> int conversion (no undefined behaviour). */
#define SL_F2I_DEF(T, NAME, LO, HI)                                                      \
    SL_INLINE T sl_f2i_##NAME(double x) {                                                \
        if (x != x) return 0;                                                            \
        if (x <= (double)(LO)) return (T)(LO);                                           \
        if (x >= (double)(HI)) return (T)(HI);                                           \
        return (T)x;                                                                     \
    }
SL_F2I_DEF(int8_t, i8, INT8_MIN, INT8_MAX)
SL_F2I_DEF(int16_t, i16, INT16_MIN, INT16_MAX)
SL_F2I_DEF(int32_t, i32, INT32_MIN, INT32_MAX)
SL_F2I_DEF(int64_t, i64, INT64_MIN, INT64_MAX)
SL_F2I_DEF(uint8_t, u8, 0, UINT8_MAX)
SL_F2I_DEF(uint16_t, u16, 0, UINT16_MAX)
SL_F2I_DEF(uint32_t, u32, 0, UINT32_MAX)
SL_F2I_DEF(uint64_t, u64, 0, UINT64_MAX)

/* ---------- indexing ---------- */

SL_NORETURN static void sl_oob(int64_t i, int64_t n, const char *loc) {
    sl_panic(loc, "index %lld is out of range for length %lld", (long long)i, (long long)n);
}

/* Python-style index: negative counts from the end. */
SL_INLINE int64_t sl_idx(int64_t i, int64_t n, const char *loc) {
    if (SL_LIKELY((uint64_t)i < (uint64_t)n)) return i;
    if (i < 0 && i + n >= 0) return i + n;
    sl_oob(i, n, loc);
}

/* Clamp slice bounds like Python does. */
SL_INLINE void sl_slice_bounds(int64_t *lo, int64_t *hi, int64_t n) {
    if (*lo < 0) *lo += n;
    if (*hi < 0) *hi += n;
    if (*lo < 0) *lo = 0;
    if (*hi > n) *hi = n;
    if (*hi < *lo) *hi = *lo;
}

/* ---------- lists ---------- */

static void sl_list_grow_to(sl_list *l, int64_t need, size_t esz) {
    int64_t cap = l->cap < 4 ? 4 : l->cap * 2;
    if (cap < need) cap = need;
    uint8_t *p = (uint8_t *)l->p;
    /* The buffer sits at the top of the data stack: grow it in place. */
    if (p && p + SL_ROUND((size_t)l->cap * esz) == sl_ds.top) {
        uint8_t *t = p + SL_ROUND((size_t)cap * esz);
        if (SL_UNLIKELY(t > sl_ds.end)) sl_overflow();
        sl_ds.top = t;
    } else {
        uint8_t *q = (uint8_t *)sl_alloc((size_t)cap * esz);
        if (l->n) memcpy(q, p, (size_t)l->n * esz);
        l->p = q;
    }
    l->cap = cap;
}

SL_INLINE void sl_list_reserve(sl_list *l, int64_t need, size_t esz) {
    if (SL_UNLIKELY(need > l->cap)) sl_list_grow_to(l, need, esz);
}

SL_INLINE sl_list sl_list_new(int64_t n, size_t esz) {
    sl_list l = {n ? sl_alloc((size_t)n * esz) : NULL, n, n};
    return l;
}

/* Copy the bytes of a list buffer into a fresh exact-size buffer. */
SL_INLINE sl_list sl_list_copy(sl_list l, size_t esz) {
    sl_list r = sl_list_new(l.n, esz);
    if (l.n) memcpy(r.p, l.p, (size_t)l.n * esz);
    return r;
}

/* The copy a loop's compaction makes: it keeps the spare capacity, so a list
   that is still growing doesn't regrow (and trigger another compaction) on its
   next push. */
SL_INLINE sl_list sl_list_relocated(sl_list l, size_t esz) {
    sl_list r = sl_list_new(l.cap, esz);
    if (l.n) memcpy(r.p, l.p, (size_t)l.n * esz);
    r.n = l.n;
    return r;
}

SL_NORETURN static void sl_empty(const char *what, const char *loc) { sl_panic(loc, "%s from an empty list", what); }

static void sl_list_insert_gap(sl_list *l, int64_t i, size_t esz, const char *loc) {
    if (i < 0) i += l->n;
    if (i < 0 || i > l->n) sl_oob(i, l->n, loc);
    sl_list_reserve(l, l->n + 1, esz);
    uint8_t *p = (uint8_t *)l->p;
    memmove(p + (size_t)(i + 1) * esz, p + (size_t)i * esz, (size_t)(l->n - i) * esz);
    l->n++;
}

/* ---------- maps ---------- */

#define SL_LIVE ((uint64_t)1 << 63)
#define SL_MAP_IDX(m, esz) ((uint32_t *)((m)->p + (size_t)(m)->cap * (esz)))

SL_INLINE uint64_t sl_mix(uint64_t x) {
    x ^= x >> 32;
    x *= 0xd6e8feb86659fd93ull;
    x ^= x >> 32;
    x *= 0xd6e8feb86659fd93ull;
    x ^= x >> 32;
    return x;
}

static uint64_t sl_hash_bytes(const uint8_t *p, int64_t n) {
    uint64_t h = 0x9e3779b97f4a7c15ull ^ (uint64_t)n;
    while (n >= 8) {
        uint64_t w;
        memcpy(&w, p, 8);
        h = (h ^ w) * 0xff51afd7ed558ccdull;
        h ^= h >> 29;
        p += 8;
        n -= 8;
    }
    uint64_t w = 0;
    memcpy(&w, p, (size_t)n);
    return sl_mix(h ^ w);
}

/* Bytes used by a map buffer with room for cap entries. */
SL_INLINE size_t sl_map_bytes(int64_t cap, size_t esz) { return (size_t)cap * esz + (size_t)cap * 8; }

/* Move the live entries into a fresh buffer of cap entries and rebuild the index. */
static void sl_map_rehash(sl_map *m, int64_t cap, size_t esz) {
    uint8_t *q = (uint8_t *)sl_alloc(sl_map_bytes(cap, esz));
    uint32_t *idx = (uint32_t *)(q + (size_t)cap * esz);
    memset(idx, 0, (size_t)cap * 8);
    uint64_t mask = (uint64_t)cap * 2 - 1;
    int64_t j = 0;
    for (int64_t i = 0; i < m->n; i++) {
        const uint8_t *e = m->p + (size_t)i * esz;
        uint64_t h;
        memcpy(&h, e, 8);
        if (!h) continue;
        memcpy(q + (size_t)j * esz, e, esz);
        uint64_t s = h & mask;
        while (idx[s]) s = (s + 1) & mask;
        idx[s] = (uint32_t)(j + 1);
        j++;
    }
    m->p = q;
    m->n = m->live = j;
    m->cap = cap;
}

/* Make room for one more entry. */
SL_INLINE void sl_map_room(sl_map *m, size_t esz) {
    if (SL_UNLIKELY(m->n == m->cap)) {
        int64_t cap = m->cap < 8 ? 8 : (m->live * 2 <= m->cap ? m->cap : m->cap * 2);
        if (SL_UNLIKELY(cap > ((int64_t)1 << 30))) sl_panic("<runtime>", "map is too large");
        sl_map_rehash(m, cap, esz);
    }
}

SL_INLINE sl_map sl_map_with(int64_t n, size_t esz) {
    sl_map m = {0};
    if (n > 0) {
        int64_t cap = 8;
        while (cap < n) cap *= 2;
        sl_map_rehash(&m, cap, esz);
    }
    return m;
}

/* Shallow copy into an exact-size buffer (dead entries dropped). */
SL_INLINE sl_map sl_map_copy(sl_map m, size_t esz) {
    sl_map r = m;
    if (m.cap) sl_map_rehash(&r, m.live < 8 ? 8 : m.cap, esz);
    return r;
}

SL_INLINE void sl_map_clear(sl_map *m, size_t esz) {
    if (m->cap) memset(SL_MAP_IDX(m, esz), 0, (size_t)m->cap * 8);
    m->n = m->live = 0;
}

SL_NORETURN static void sl_no_key(const char *loc) { sl_panic(loc, "key not found in map"); }

/* ---------- strings ---------- */

SL_INLINE bool sl_str_eq(sl_str a, sl_str b) {
    return a.n == b.n && (a.p == b.p || memcmp(a.p, b.p, (size_t)a.n) == 0);
}

SL_INLINE int sl_str_cmp(sl_str a, sl_str b) {
    int64_t n = a.n < b.n ? a.n : b.n;
    int c = n ? memcmp(a.p, b.p, (size_t)n) : 0;
    if (c) return c < 0 ? -1 : 1;
    return (a.n > b.n) - (a.n < b.n);
}

/* End of the bytes of the most recent string allocation. When it is also the
 * top of the data stack (up to alignment padding), nothing lives after that
 * string, so appending to any view ending there can grow it in place. */
static __thread const uint8_t *sl_str_end;

SL_INLINE uint8_t *sl_str_alloc(int64_t n) {
    uint8_t *p = (uint8_t *)sl_alloc((size_t)n);
    sl_str_end = p + n;
    return p;
}

SL_INLINE bool sl_str_at_top(sl_str a) {
    return a.n && a.p + a.n == sl_str_end && (uint8_t *)SL_ROUND((uintptr_t)sl_str_end) == sl_ds.top;
}

static sl_str sl_str_concat(sl_str a, sl_str b) {
    if (b.n == 0) return a;
    if (a.n == 0) return b;
    if (sl_str_at_top(a)) {
        uint8_t *t = (uint8_t *)SL_ROUND((uintptr_t)(a.p + a.n + b.n));
        if (SL_UNLIKELY(t > sl_ds.end)) sl_overflow();
        memcpy((uint8_t *)a.p + a.n, b.p, (size_t)b.n);
        sl_ds.top = t;
        sl_str_end = a.p + a.n + b.n;
        return (sl_str){a.p, a.n + b.n};
    }
    uint8_t *p = sl_str_alloc(a.n + b.n);
    if (a.n) memcpy(p, a.p, (size_t)a.n);
    if (b.n) memcpy(p + a.n, b.p, (size_t)b.n);
    return (sl_str){p, a.n + b.n};
}

static sl_str sl_str_repeat(sl_str s, int64_t k) {
    if (k <= 0 || s.n == 0) return (sl_str){(const uint8_t *)"", 0};
    uint8_t *p = sl_str_alloc((int64_t)(s.n * k));
    for (int64_t i = 0; i < k; i++) memcpy(p + i * s.n, s.p, (size_t)s.n);
    return (sl_str){p, s.n * k};
}

SL_INLINE sl_str sl_str_slice(sl_str s, int64_t lo, int64_t hi) {
    sl_slice_bounds(&lo, &hi, s.n);
    return (sl_str){s.p + lo, hi - lo};
}

SL_INLINE uint8_t sl_str_at(sl_str s, int64_t i, const char *loc) { return s.p[sl_idx(i, s.n, loc)]; }

static int64_t sl_str_find_from(sl_str s, sl_str t, int64_t from) {
    if (t.n == 0) return from <= s.n ? from : -1;
    if (t.n > s.n) return -1;
    const uint8_t *end = s.p + s.n - t.n;
    for (const uint8_t *q = s.p + from; q <= end; q++) {
        q = (const uint8_t *)memchr(q, t.p[0], (size_t)(end - q + 1));
        if (!q) return -1;
        if (memcmp(q, t.p, (size_t)t.n) == 0) return q - s.p;
    }
    return -1;
}

SL_INLINE int64_t sl_str_find(sl_str s, sl_str t) { return sl_str_find_from(s, t, 0); }
SL_INLINE bool sl_str_contains(sl_str s, sl_str t) { return sl_str_find(s, t) >= 0; }
SL_INLINE bool sl_str_starts(sl_str s, sl_str t) { return t.n <= s.n && memcmp(s.p, t.p, (size_t)t.n) == 0; }
SL_INLINE bool sl_str_ends(sl_str s, sl_str t) {
    return t.n <= s.n && memcmp(s.p + s.n - t.n, t.p, (size_t)t.n) == 0;
}

static int64_t sl_str_count(sl_str s, sl_str t) {
    if (t.n == 0) return s.n + 1;
    int64_t c = 0, i = 0;
    while ((i = sl_str_find_from(s, t, i)) >= 0) {
        c++;
        i += t.n;
    }
    return c;
}

SL_INLINE bool sl_isspace(uint8_t c) { return c == ' ' || (c >= '\t' && c <= '\r'); }

static sl_str sl_str_trim_start(sl_str s) {
    while (s.n && sl_isspace(s.p[0])) s.p++, s.n--;
    return s;
}

static sl_str sl_str_trim_end(sl_str s) {
    while (s.n && sl_isspace(s.p[s.n - 1])) s.n--;
    return s;
}

static sl_str sl_str_trim(sl_str s) { return sl_str_trim_end(sl_str_trim_start(s)); }

static sl_str sl_str_map_case(sl_str s, int upper) {
    uint8_t *p = sl_str_alloc((int64_t)s.n);
    for (int64_t i = 0; i < s.n; i++) {
        uint8_t c = s.p[i];
        if (upper && c >= 'a' && c <= 'z') c -= 32;
        else if (!upper && c >= 'A' && c <= 'Z') c += 32;
        p[i] = c;
    }
    return (sl_str){p, s.n};
}

static sl_str sl_str_clone(sl_str s) {
    uint8_t *p = sl_str_alloc((int64_t)s.n);
    if (s.n) memcpy(p, s.p, (size_t)s.n);
    return (sl_str){p, s.n};
}

/* split(sep) keeps empty fields; split() splits on runs of whitespace. */
static sl_list sl_str_split(sl_str s, sl_str sep, bool ws) {
    sl_list out = {0};
    if (ws) {
        int64_t i = 0;
        while (1) {
            while (i < s.n && sl_isspace(s.p[i])) i++;
            if (i >= s.n) break;
            int64_t j = i;
            while (j < s.n && !sl_isspace(s.p[j])) j++;
            sl_list_reserve(&out, out.n + 1, sizeof(sl_str));
            ((sl_str *)out.p)[out.n++] = (sl_str){s.p + i, j - i};
            i = j;
        }
        return out;
    }
    if (sep.n == 0) sl_panic("split", "empty separator");
    int64_t i = 0;
    while (1) {
        int64_t j = sl_str_find_from(s, sep, i);
        int64_t e = j < 0 ? s.n : j;
        sl_list_reserve(&out, out.n + 1, sizeof(sl_str));
        ((sl_str *)out.p)[out.n++] = (sl_str){s.p + i, e - i};
        if (j < 0) break;
        i = j + sep.n;
    }
    return out;
}

static sl_list sl_str_lines(sl_str s) {
    sl_list out = {0};
    int64_t i = 0;
    while (i < s.n) {
        const uint8_t *nl = (const uint8_t *)memchr(s.p + i, '\n', (size_t)(s.n - i));
        int64_t e = nl ? nl - s.p : s.n;
        int64_t ee = (e > i && s.p[e - 1] == '\r') ? e - 1 : e;
        sl_list_reserve(&out, out.n + 1, sizeof(sl_str));
        ((sl_str *)out.p)[out.n++] = (sl_str){s.p + i, ee - i};
        i = e + 1;
    }
    return out;
}

static sl_str sl_str_replace(sl_str s, sl_str a, sl_str b) {
    if (a.n == 0) return s;
    int64_t first = sl_str_find(s, a);
    if (first < 0) return s;
    int64_t cnt = sl_str_count(s, a);
    int64_t n = s.n + cnt * (b.n - a.n);
    uint8_t *p = sl_str_alloc((int64_t)n), *w = p;
    int64_t i = 0, j = first;
    while (j >= 0) {
        memcpy(w, s.p + i, (size_t)(j - i)), w += j - i;
        memcpy(w, b.p, (size_t)b.n), w += b.n;
        i = j + a.n;
        j = sl_str_find_from(s, a, i);
    }
    memcpy(w, s.p + i, (size_t)(s.n - i));
    return (sl_str){p, n};
}

static sl_str sl_str_join(sl_str sep, const sl_str *xs, int64_t k) {
    int64_t n = 0;
    for (int64_t i = 0; i < k; i++) n += xs[i].n + (i ? sep.n : 0);
    uint8_t *p = sl_str_alloc((int64_t)n), *w = p;
    for (int64_t i = 0; i < k; i++) {
        if (i) memcpy(w, sep.p, (size_t)sep.n), w += sep.n;
        memcpy(w, xs[i].p, (size_t)xs[i].n), w += xs[i].n;
    }
    return (sl_str){p, n};
}

/* ---------- UTF-8 ---------- */

SL_INLINE uint32_t sl_utf8_next(const uint8_t *p, int64_t n, int64_t *i) {
    uint8_t c = p[*i];
    if (c < 0x80) {
        (*i)++;
        return c;
    }
    int len = c >= 0xF0 ? 4 : c >= 0xE0 ? 3 : c >= 0xC0 ? 2 : 1;
    if (*i + len > n) len = 1;
    uint32_t cp = len == 1 ? 0xFFFD : len == 2 ? (c & 0x1F) : len == 3 ? (c & 0x0F) : (c & 0x07);
    for (int k = 1; k < len; k++) cp = (cp << 6) | (p[*i + k] & 0x3F);
    *i += len;
    return cp;
}

SL_INLINE int sl_utf8_encode(uint32_t c, uint8_t *o) {
    if (c < 0x80) return o[0] = (uint8_t)c, 1;
    if (c < 0x800) return o[0] = 0xC0 | (c >> 6), o[1] = 0x80 | (c & 0x3F), 2;
    if (c < 0x10000) return o[0] = 0xE0 | (c >> 12), o[1] = 0x80 | ((c >> 6) & 0x3F), o[2] = 0x80 | (c & 0x3F), 3;
    o[0] = 0xF0 | (c >> 18), o[1] = 0x80 | ((c >> 12) & 0x3F), o[2] = 0x80 | ((c >> 6) & 0x3F);
    o[3] = 0x80 | (c & 0x3F);
    return 4;
}

static sl_str sl_char_str(uint32_t c) {
    uint8_t *p = (uint8_t *)sl_alloc(4);
    int k = sl_utf8_encode(c, p);
    sl_str_end = p + k;
    return (sl_str){p, k};
}

static sl_list sl_str_chars(sl_str s) {
    sl_list out = sl_list_new(s.n, sizeof(uint32_t));
    int64_t i = 0, k = 0;
    while (i < s.n) ((uint32_t *)out.p)[k++] = sl_utf8_next(s.p, s.n, &i);
    out.n = k;
    return out;
}

static sl_list sl_str_bytes(sl_str s) {
    sl_list out = sl_list_new(s.n, 1);
    if (s.n) memcpy(out.p, s.p, (size_t)s.n);
    return out;
}

SL_INLINE bool sl_char_is_space(uint32_t c) { return c == ' ' || (c >= '\t' && c <= '\r') || c == 0x85 || c == 0xA0; }
SL_INLINE bool sl_char_is_digit(uint32_t c) { return c >= '0' && c <= '9'; }
SL_INLINE bool sl_char_is_upper(uint32_t c) { return c >= 'A' && c <= 'Z'; }
SL_INLINE bool sl_char_is_lower(uint32_t c) { return c >= 'a' && c <= 'z'; }
SL_INLINE bool sl_char_is_alpha(uint32_t c) { return sl_char_is_upper(c) || sl_char_is_lower(c) || c >= 0xC0; }
SL_INLINE bool sl_char_is_alnum(uint32_t c) { return sl_char_is_alpha(c) || sl_char_is_digit(c); }
SL_INLINE uint32_t sl_char_upper(uint32_t c) { return sl_char_is_lower(c) ? c - 32 : c; }
SL_INLINE uint32_t sl_char_lower(uint32_t c) { return sl_char_is_upper(c) ? c + 32 : c; }

/* int -> char: only Unicode scalar values are chars. */
SL_INLINE uint32_t sl_chr(int64_t x, const char *loc) {
    if (SL_UNLIKELY((uint64_t)x > 0x10FFFF || (x >= 0xD800 && x <= 0xDFFF)))
        sl_panic(loc, "%lld is not a valid char", (long long)x);
    return (uint32_t)x;
}

/* ---------- parsing ---------- */

static bool sl_parse_int(sl_str s, int64_t *out) {
    s = sl_str_trim(s);
    int64_t i = 0;
    bool neg = false;
    if (i < s.n && (s.p[i] == '-' || s.p[i] == '+')) neg = s.p[i++] == '-';
    if (i >= s.n) return false;
    uint64_t v = 0;
    for (; i < s.n; i++) {
        uint8_t c = s.p[i];
        if (c == '_' && i > 0) continue;
        if (c < '0' || c > '9') return false;
        if (v > (UINT64_MAX - 9) / 10) return false;
        v = v * 10 + (c - '0');
    }
    if (v > (uint64_t)INT64_MAX + neg) return false;
    *out = neg ? (int64_t)(0 - v) : (int64_t)v;
    return true;
}

static bool sl_parse_float(sl_str s, double *out) {
    s = sl_str_trim(s);
    if (s.n == 0 || s.n > 400) return false;
    char buf[401];
    memcpy(buf, s.p, (size_t)s.n);
    buf[s.n] = 0;
    char *end;
    errno = 0;
    double v = strtod(buf, &end);
    if (end != buf + s.n) return false;
    *out = v;
    return true;
}

/* ---------- string builder ----------
 * Formatting writes bytes straight onto the top of the data stack; nothing
 * else allocates while a builder is open. */

typedef struct { uint8_t *start; } sl_sb;

SL_INLINE sl_sb sl_sb_begin(void) { return (sl_sb){sl_ds.top}; }

SL_INLINE uint8_t *sl_room(size_t n) {
    if (SL_UNLIKELY(sl_ds.top + n > sl_ds.end)) sl_overflow();
    return sl_ds.top;
}

SL_INLINE void sl_w(const void *p, size_t n) {
    uint8_t *t = sl_room(n);
    memcpy(t, p, n);
    sl_ds.top = t + n;
}

SL_INLINE void sl_wc(uint8_t c) {
    uint8_t *t = sl_room(1);
    *t = c;
    sl_ds.top = t + 1;
}

#define SL_WLIT(s) sl_w((s), sizeof(s) - 1)

SL_INLINE void sl_w_str(sl_str s) { sl_w(s.p, (size_t)s.n); }

SL_INLINE sl_str sl_sb_end(sl_sb b) {
    sl_str s = {b.start, sl_ds.top - b.start};
    sl_str_end = sl_ds.top;
    sl_ds.top = (uint8_t *)SL_ROUND((uintptr_t)sl_ds.top);
    return s;
}

static void sl_w_u64(uint64_t v) {
    char buf[24];
    int i = 24;
    do buf[--i] = (char)('0' + v % 10); while (v /= 10);
    sl_w(buf + i, (size_t)(24 - i));
}

static void sl_w_i64(int64_t v) {
    if (v < 0) {
        sl_wc('-');
        sl_w_u64(0 - (uint64_t)v);
    } else {
        sl_w_u64((uint64_t)v);
    }
}

SL_INLINE void sl_w_bool(bool b) {
    if (b) SL_WLIT("true");
    else SL_WLIT("false");
}

SL_INLINE void sl_w_char(uint32_t c) {
    uint8_t *t = sl_room(4);
    sl_ds.top = t + sl_utf8_encode(c, t);
}

/* Shortest representation that reads back to the same double, Python-style. */
static int sl_fmt_shortest(char *buf, double x, int is32) {
    if (x != x) return (int)(strcpy(buf, "nan"), 3);
    if (isinf(x)) return x > 0 ? (int)(strcpy(buf, "inf"), 3) : (int)(strcpy(buf, "-inf"), 4);
    int n = 0;
    for (int prec = is32 ? 6 : 15; prec <= 17; prec++) {
        n = snprintf(buf, 40, "%.*g", prec, x);
        if (is32 ? (strtof(buf, NULL) == (float)x) : (strtod(buf, NULL) == x)) break;
    }
    bool frac = false;
    for (int i = 0; i < n; i++)
        if (buf[i] == '.' || buf[i] == 'e' || buf[i] == 'n') frac = true;
    if (!frac) buf[n++] = '.', buf[n++] = '0', buf[n] = 0;
    return n;
}

static void sl_w_f64(double x) {
    char buf[48];
    sl_w(buf, (size_t)sl_fmt_shortest(buf, x, 0));
}

static void sl_w_f32(float x) {
    char buf[48];
    sl_w(buf, (size_t)sl_fmt_shortest(buf, x, 1));
}

static void sl_w_escaped(uint32_t c, uint8_t quote) {
    switch (c) {
    case '\n': SL_WLIT("\\n"); return;
    case '\t': SL_WLIT("\\t"); return;
    case '\r': SL_WLIT("\\r"); return;
    case '\\': SL_WLIT("\\\\"); return;
    case 0: SL_WLIT("\\0"); return;
    }
    if (c == quote) {
        sl_wc('\\');
        sl_wc(quote);
        return;
    }
    if (c < 0x20 || c == 0x7F) {
        char buf[8];
        snprintf(buf, sizeof buf, "\\x%02x", c);
        sl_w(buf, 4);
        return;
    }
    sl_w_char(c);
}

static void sl_w_repr_str(sl_str s) {
    sl_wc('"');
    int64_t i = 0;
    while (i < s.n) {
        int64_t j = i;
        while (j < s.n && s.p[j] >= 0x20 && s.p[j] != '"' && s.p[j] != '\\' && s.p[j] != 0x7F) j++;
        if (j > i) sl_w(s.p + i, (size_t)(j - i)), i = j;
        if (i < s.n) sl_w_escaped(sl_utf8_next(s.p, s.n, &i), '"');
    }
    sl_wc('"');
}

static void sl_w_repr_char(uint32_t c) {
    sl_wc('\'');
    sl_w_escaped(c, '\'');
    sl_wc('\'');
}

/* ---------- format specs: {x:<fill><align><sign><0><width><,><.prec><kind>} ---------- */

typedef struct {
    uint32_t fill;
    char align;   /* 0, '<', '>', '^', '=' */
    char sign;    /* 0, '+', '-', ' ' */
    char kind;    /* 0 or one of bcdeEfFgGosxX% */
    bool comma;
    int width;
    int prec;     /* -1 when absent */
} sl_spec;

static int64_t sl_count_chars(const uint8_t *p, const uint8_t *e) {
    int64_t n = 0;
    for (; p < e; p++) n += (*p & 0xC0) != 0x80;
    return n;
}

static void sl_w_fill(uint32_t fill, int64_t k) {
    if (fill < 0x80) {
        uint8_t *t = sl_room((size_t)k);
        memset(t, (int)fill, (size_t)k);
        sl_ds.top = t + k;
    } else {
        for (int64_t i = 0; i < k; i++) sl_w_char(fill);
    }
}

/* Pad the bytes written since `from` to the spec width. `split` bytes at the
 * front (a sign) stay in front of '=' padding. */
static void sl_pad(const sl_spec *sp, uint8_t *from, char dflt, int64_t split) {
    int64_t have = sl_count_chars(from, sl_ds.top);
    if (sp->width <= have) return;
    int64_t pad = sp->width - have;
    char al = sp->align ? sp->align : dflt;
    int64_t len = sl_ds.top - from;
    /* Move the content to scratch space past the top, then rewrite in place. */
    uint8_t *tmp = sl_room((size_t)(len * 2 + pad * 4 + 8)) + pad * 4 + len;
    memcpy(tmp, from, (size_t)len);
    sl_ds.top = from;
    int64_t left = al == '<' ? 0 : al == '^' ? pad / 2 : pad;
    if (al == '=') {
        sl_w(tmp, (size_t)split);
        sl_w_fill(sp->fill, pad);
        sl_w(tmp + split, (size_t)(len - split));
        return;
    }
    sl_w_fill(sp->fill, left);
    sl_w(tmp, (size_t)len);
    sl_w_fill(sp->fill, pad - left);
}

static void sl_w_grouped(const char *digits, int n) {
    for (int i = 0; i < n; i++) {
        if (i && (n - i) % 3 == 0) sl_wc(',');
        sl_wc((uint8_t)digits[i]);
    }
}

static void sl_fmt_int(const sl_spec *sp, uint64_t mag, bool neg) {
    uint8_t *from = sl_ds.top;
    char buf[80];
    int n = 0;
    char k = sp->kind ? sp->kind : 'd';
    if (k == 'c') {
        sl_w_char((uint32_t)mag);
        sl_pad(sp, from, '<', 0);
        return;
    }
    int base = k == 'b' ? 2 : k == 'o' ? 8 : (k == 'x' || k == 'X') ? 16 : 10;
    const char *dig = k == 'X' ? "0123456789ABCDEF" : "0123456789abcdef";
    char rev[72];
    int r = 0;
    do rev[r++] = dig[mag % (uint64_t)base]; while (mag /= (uint64_t)base);
    while (r) buf[n++] = rev[--r];
    int64_t split = 0;
    if (neg) sl_wc('-'), split = 1;
    else if (sp->sign == '+' || sp->sign == ' ') sl_wc((uint8_t)sp->sign), split = 1;
    if (sp->comma) sl_w_grouped(buf, n);
    else sl_w(buf, (size_t)n);
    sl_pad(sp, from, '>', split);
}

static void sl_fmt_float(const sl_spec *sp, double x) {
    uint8_t *from = sl_ds.top;
    char buf[400];
    int n;
    char k = sp->kind;
    bool pct = k == '%';
    if (pct) x *= 100, k = 'f';
    bool neg = signbit(x) && x == x;
    double a = neg ? -x : x;
    if (!k && sp->prec < 0) n = sl_fmt_shortest(buf, a, 0);
    else if (!k) n = snprintf(buf, sizeof buf, "%.*g", sp->prec, a);
    else {
        char f[8] = {'%', '.', '*', k, 0};
        n = snprintf(buf, sizeof buf, f, sp->prec < 0 ? 6 : sp->prec, a);
    }
    if (n >= (int)sizeof buf) n = (int)sizeof buf - 1;
    int64_t split = 0;
    if (neg) sl_wc('-'), split = 1;
    else if (sp->sign == '+' || sp->sign == ' ') sl_wc((uint8_t)sp->sign), split = 1;
    if (sp->comma) {
        int ip = 0;
        while (ip < n && buf[ip] >= '0' && buf[ip] <= '9') ip++;
        sl_w_grouped(buf, ip);
        sl_w(buf + ip, (size_t)(n - ip));
    } else {
        sl_w(buf, (size_t)n);
    }
    if (pct) sl_wc('%');
    sl_pad(sp, from, '>', split);
}

/* Strings honour precision as a maximum length, like Python. */
static void sl_fmt_str(const sl_spec *sp, sl_str s) {
    uint8_t *from = sl_ds.top;
    if (sp->prec >= 0) {
        int64_t i = 0, c = 0;
        while (i < s.n && c < sp->prec) {
            sl_utf8_next(s.p, s.n, &i);
            c++;
        }
        s.n = i;
    }
    sl_w_str(s);
    sl_pad(sp, from, '<', 0);
}

/* ---------- I/O ---------- */

SL_INLINE void sl_out(FILE *f, sl_str s) { fwrite(s.p, 1, (size_t)s.n, f); }

static const char *sl_cstr(sl_str s) {
    char *p = (char *)sl_alloc((size_t)s.n + 1);
    memcpy(p, s.p, (size_t)s.n);
    p[s.n] = 0;
    return p;
}

static bool sl_input(bool has_prompt, sl_str prompt, sl_str *out) {
    if (has_prompt) sl_out(stdout, prompt);
    fflush(stdout);
    sl_sb b = sl_sb_begin();
    int c;
    bool any = false;
    while ((c = getchar()) != EOF) {
        any = true;
        if (c == '\n') break;
        sl_wc((uint8_t)c);
    }
    sl_str s = sl_sb_end(b);
    if (s.n && s.p[s.n - 1] == '\r') s.n--;
    *out = s;
    return any;
}

static sl_str sl_errno_str(void) {
    const char *m = strerror(errno);
    return (sl_str){(const uint8_t *)m, (int64_t)strlen(m)};
}

static bool sl_read_file(sl_str path, sl_str *out) {
    FILE *f = fopen(sl_cstr(path), "rb");
    if (!f) return *out = sl_errno_str(), false;
    sl_sb b = sl_sb_begin();
    size_t got;
    while (1) {
        uint8_t *t = sl_room(1 << 16);
        got = fread(t, 1, 1 << 16, f);
        sl_ds.top = t + got;
        if (got < (1 << 16)) break;
    }
    bool err = ferror(f);
    fclose(f);
    *out = sl_sb_end(b);
    if (err) return *out = sl_errno_str(), false;
    return true;
}

static bool sl_write_file(sl_str path, sl_str data) {
    FILE *f = fopen(sl_cstr(path), "wb");
    if (!f) return false;
    bool ok = fwrite(data.p, 1, (size_t)data.n, f) == (size_t)data.n;
    return fclose(f) == 0 && ok;
}

static sl_list sl_args(void) {
    sl_list l = sl_list_new(sl_argc, sizeof(sl_str));
    for (int i = 0; i < sl_argc; i++) ((sl_str *)l.p)[i] = (sl_str){(const uint8_t *)sl_argv[i], (int64_t)strlen(sl_argv[i])};
    return l;
}

static double sl_clock(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

/* ---------- sorting ----------
 * SL_DEF_SORT: stable merge sort (scratch space on the data stack).
 * SL_DEF_QSORT: introsort for scalars, where stability is unobservable. */

#define SL_DEF_SORT(NAME, T, LT)                                                         \
    static void NAME(T *a, int64_t n) {                                                  \
        if (n < 2) return;                                                               \
        for (int64_t lo = 0; lo < n; lo += 32) {                                         \
            int64_t hi = lo + 32 < n ? lo + 32 : n;                                      \
            for (int64_t i = lo + 1; i < hi; i++) {                                      \
                T x = a[i];                                                              \
                int64_t j = i;                                                           \
                while (j > lo && LT(&x, &a[j - 1])) a[j] = a[j - 1], j--;                \
                a[j] = x;                                                                \
            }                                                                            \
        }                                                                                \
        if (n <= 32) return;                                                             \
        uint8_t *mark = sl_ds.top;                                                       \
        T *src = a, *dst = (T *)sl_alloc((size_t)n * sizeof(T));                         \
        for (int64_t w = 32; w < n; w *= 2) {                                            \
            for (int64_t lo = 0; lo < n; lo += 2 * w) {                                  \
                int64_t mid = lo + w < n ? lo + w : n, hi = lo + 2 * w < n ? lo + 2 * w : n; \
                int64_t i = lo, j = mid, k = lo;                                         \
                if (mid >= hi || !LT(&src[mid], &src[mid - 1])) {                        \
                    memcpy(dst + lo, src + lo, (size_t)(hi - lo) * sizeof(T));           \
                    continue;                                                            \
                }                                                                        \
                while (i < mid && j < hi) dst[k++] = LT(&src[j], &src[i]) ? src[j++] : src[i++]; \
                while (i < mid) dst[k++] = src[i++];                                     \
                while (j < hi) dst[k++] = src[j++];                                      \
            }                                                                            \
            T *t = src;                                                                  \
            src = dst;                                                                   \
            dst = t;                                                                     \
        }                                                                                \
        if (src != a) memcpy(a, src, (size_t)n * sizeof(T));                             \
        sl_ds.top = mark;                                                                \
    }

#define SL_DEF_QSORT(NAME, T)                                                            \
    static void NAME##_heap(T *a, int64_t n) {                                           \
        for (int64_t s = n / 2 - 1;; s--) {                                              \
            for (int64_t r = s;;) {                                                      \
                int64_t c = 2 * r + 1;                                                   \
                if (c >= n) break;                                                       \
                if (c + 1 < n && a[c] < a[c + 1]) c++;                                   \
                if (!(a[r] < a[c])) break;                                               \
                T t = a[r]; a[r] = a[c]; a[c] = t;                                       \
                r = c;                                                                   \
            }                                                                            \
            if (s == 0) break;                                                           \
        }                                                                                \
        for (int64_t e = n - 1; e > 0; e--) {                                            \
            T t = a[0]; a[0] = a[e]; a[e] = t;                                           \
            for (int64_t r = 0;;) {                                                      \
                int64_t c = 2 * r + 1;                                                   \
                if (c >= e) break;                                                       \
                if (c + 1 < e && a[c] < a[c + 1]) c++;                                   \
                if (!(a[r] < a[c])) break;                                               \
                T u = a[r]; a[r] = a[c]; a[c] = u;                                       \
                r = c;                                                                   \
            }                                                                            \
        }                                                                                \
    }                                                                                    \
    static void NAME##_rec(T *a, int64_t n, int depth) {                                 \
        while (n > 24) {                                                                 \
            if (depth-- == 0) { NAME##_heap(a, n); return; }                             \
            T x = a[0], y = a[n / 2], z = a[n - 1];                                      \
            T p = x < y ? (y < z ? y : (x < z ? z : x)) : (x < z ? x : (y < z ? z : y)); \
            int64_t i = -1, j = n;                                                       \
            while (1) {                                                                  \
                do i++; while (a[i] < p);                                                \
                do j--; while (p < a[j]);                                                \
                if (i >= j) break;                                                       \
                T t = a[i]; a[i] = a[j]; a[j] = t;                                       \
            }                                                                            \
            NAME##_rec(a, j + 1, depth);                                                 \
            a += j + 1;                                                                  \
            n -= j + 1;                                                                  \
        }                                                                                \
        for (int64_t i = 1; i < n; i++) {                                                \
            T x = a[i];                                                                  \
            int64_t j = i;                                                               \
            while (j > 0 && x < a[j - 1]) a[j] = a[j - 1], j--;                          \
            a[j] = x;                                                                    \
        }                                                                                \
    }                                                                                    \
    static void NAME(T *a, int64_t n) {                                                  \
        int d = 0;                                                                       \
        for (int64_t m = n; m > 1; m >>= 1) d += 2;                                      \
        NAME##_rec(a, n, d);                                                             \
    }

/* ---------- tasks (threads) ----------
 * A task runs a closure on a new thread with its own data stack. Nothing is
 * shared: spawning deep-copies the closure's environment into the task's
 * stack, and joining deep-copies the result back into the joiner's stack and
 * unmaps the task's stacks. The task header and its result slot sit at the
 * bottom of the task's own data stack. */
typedef struct sl_task {
    pthread_t th;
    sl_arena ds, xs;
    sl_fn f;
    void (*run)(struct sl_task *t);
    void *out;
    volatile int finished;
} sl_task;

static void *sl_task_main(void *arg) {
    sl_task *t = (sl_task *)arg;
    sl_ds = t->ds;
    sl_xs = t->xs;
    sl_str_end = NULL;
    t->run(t);
    t->ds = sl_ds;
    __atomic_store_n(&t->finished, 1, __ATOMIC_RELEASE);
    return NULL;
}

/* Reserve the task's stacks and copy f (and everything it captured) into them. */
static sl_task *sl_task_new(sl_fn f, size_t out_size, void (*run)(sl_task *)) {
    size_t mb = 4096;
    const char *env = getenv("SILLY_TASK_STACK_MB");
    if (env && atol(env) > 0) mb = (size_t)atol(env);
    if (mb > sl_stack_mb) mb = sl_stack_mb;
    sl_arena ds, xs;
    sl_arena_init(&ds, mb << 20);
    sl_arena_init(&xs, (mb / 2) << 20);
    sl_arena save = sl_ds;
    sl_ds = ds;
    sl_task *t = (sl_task *)sl_alloc(sizeof(sl_task));
    t->out = out_size ? sl_alloc(out_size) : NULL;
    sl_fn_reloc(&f, save.base, save.top);
    t->ds = sl_ds;
    sl_ds = save;
    t->xs = xs;
    t->f = f;
    t->run = run;
    t->finished = 0;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, (size_t)64 << 20);
    int rc = pthread_create(&t->th, &attr, sl_task_main, t);
    pthread_attr_destroy(&attr);
    if (rc) {
        fflush(stdout);
        fprintf(stderr, "panic: cannot start a thread: %s\n", strerror(rc));
        exit(101);
    }
    return t;
}

SL_INLINE void sl_task_wait(sl_task *t) { pthread_join(t->th, NULL); }

SL_INLINE bool sl_task_done(sl_task *t) { return __atomic_load_n(&t->finished, __ATOMIC_ACQUIRE); }

/* After the result has been copied out: release the task's stacks. */
static void sl_task_free(sl_task *t) {
    sl_arena ds = t->ds, xs = t->xs;
    munmap(xs.base, (size_t)(xs.end - xs.base));
    munmap(ds.base, (size_t)(ds.end - ds.base));
}

static int64_t sl_cpu_count(void) {
    long n = sysconf(_SC_NPROCESSORS_ONLN);
    return n > 0 ? n : 1;
}
