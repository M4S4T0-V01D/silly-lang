/* Float bit casts for binary.silly. */
#include <string.h>

static int64_t bn_f64_bits(double x) { int64_t b; memcpy(&b, &x, 8); return b; }
static double bn_f64_from_bits(int64_t b) { double x; memcpy(&x, &b, 8); return x; }
static int64_t bn_f32_bits(double x) { float f = (float)x; uint32_t b; memcpy(&b, &f, 4); return (int64_t)b; }
static double bn_f32_from_bits(int64_t b) { uint32_t u = (uint32_t)b; float f; memcpy(&f, &u, 4); return (double)f; }
