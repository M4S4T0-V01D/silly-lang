/* Message digests for hashlib.silly: MD5, SHA-1, SHA-256, SHA-512, CRC-32 and
   HMAC. Every digest is returned as raw bytes; hashlib.silly hex-encodes. */
#include <string.h>

static sl_str hl_bytes(const uint8_t *d, size_t n) {
    uint8_t *p = sl_alloc(n + 1);
    memcpy(p, d, n);
    p[n] = 0;
    return (sl_str){p, (int64_t)n};
}

static inline uint32_t hl_rol(uint32_t x, int k) { return (x << k) | (x >> (32 - k)); }
static inline uint32_t hl_ror(uint32_t x, int k) { return (x >> k) | (x << (32 - k)); }
static inline uint64_t hl_ror64(uint64_t x, int k) { return (x >> k) | (x << (64 - k)); }

/* Feeds msg plus Merkle-Damgard padding to `block`, `bs` bytes at a time; the
   length goes in the last 8 bytes (big- or little-endian), in a 16-byte field
   for SHA-512. */
static void hl_blocks(const uint8_t *msg, size_t n, size_t bs, bool big, void (*block)(void *, const uint8_t *), void *st) {
    size_t i = 0;
    for (; i + bs <= n; i += bs) block(st, msg + i);
    uint8_t tail[256] = {0};
    size_t r = n - i;
    memcpy(tail, msg + i, r);
    tail[r] = 0x80;
    size_t lenpos = bs == 128 ? 16 : 8;
    size_t total = (r + 1 + lenpos <= bs) ? bs : 2 * bs;
    uint64_t bits = (uint64_t)n * 8;
    for (int k = 0; k < 8; k++) {
        uint8_t byte = (uint8_t)(bits >> (8 * k));
        if (big) tail[total - 1 - k] = byte;
        else tail[total - 8 + k] = byte;
    }
    block(st, tail);
    if (total == 2 * bs) block(st, tail + bs);
}

/* ---- MD5 ---- */
static void hl_md5_block(void *sv, const uint8_t *b) {
    static const uint32_t K[64] = {
        0xd76aa478, 0xe8c7b756, 0x242070db, 0xc1bdceee, 0xf57c0faf, 0x4787c62a, 0xa8304613, 0xfd469501,
        0x698098d8, 0x8b44f7af, 0xffff5bb1, 0x895cd7be, 0x6b901122, 0xfd987193, 0xa679438e, 0x49b40821,
        0xf61e2562, 0xc040b340, 0x265e5a51, 0xe9b6c7aa, 0xd62f105d, 0x02441453, 0xd8a1e681, 0xe7d3fbc8,
        0x21e1cde6, 0xc33707d6, 0xf4d50d87, 0x455a14ed, 0xa9e3e905, 0xfcefa3f8, 0x676f02d9, 0x8d2a4c8a,
        0xfffa3942, 0x8771f681, 0x6d9d6122, 0xfde5380c, 0xa4beea44, 0x4bdecfa9, 0xf6bb4b60, 0xbebfbc70,
        0x289b7ec6, 0xeaa127fa, 0xd4ef3085, 0x04881d05, 0xd9d4d039, 0xe6db99e5, 0x1fa27cf8, 0xc4ac5665,
        0xf4292244, 0x432aff97, 0xab9423a7, 0xfc93a039, 0x655b59c3, 0x8f0ccc92, 0xffeff47d, 0x85845dd1,
        0x6fa87e4f, 0xfe2ce6e0, 0xa3014314, 0x4e0811a1, 0xf7537e82, 0xbd3af235, 0x2ad7d2bb, 0xeb86d391};
    static const int S[16] = {7, 12, 17, 22, 5, 9, 14, 20, 4, 11, 16, 23, 6, 10, 15, 21};
    uint32_t *h = sv, m[16];
    for (int i = 0; i < 16; i++)
        m[i] = (uint32_t)b[4 * i] | (uint32_t)b[4 * i + 1] << 8 | (uint32_t)b[4 * i + 2] << 16 | (uint32_t)b[4 * i + 3] << 24;
    uint32_t a = h[0], bb = h[1], c = h[2], d = h[3];
    for (int i = 0; i < 64; i++) {
        uint32_t f; int g;
        if (i < 16) { f = (bb & c) | (~bb & d); g = i; }
        else if (i < 32) { f = (d & bb) | (~d & c); g = (5 * i + 1) % 16; }
        else if (i < 48) { f = bb ^ c ^ d; g = (3 * i + 5) % 16; }
        else { f = c ^ (bb | ~d); g = (7 * i) % 16; }
        uint32_t t = d;
        d = c; c = bb;
        bb = bb + hl_rol(a + f + K[i] + m[g], S[(i / 16) * 4 + i % 4]);
        a = t;
    }
    h[0] += a; h[1] += bb; h[2] += c; h[3] += d;
}

static sl_str hl_md5(sl_str s) {
    uint32_t h[4] = {0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476};
    hl_blocks(s.p, (size_t)s.n, 64, false, hl_md5_block, h);
    uint8_t out[16];
    for (int i = 0; i < 16; i++) out[i] = (uint8_t)(h[i / 4] >> (8 * (i % 4)));
    return hl_bytes(out, 16);
}

/* ---- SHA-1 ---- */
static void hl_sha1_block(void *sv, const uint8_t *b) {
    uint32_t *h = sv, w[80];
    for (int i = 0; i < 16; i++)
        w[i] = (uint32_t)b[4 * i] << 24 | (uint32_t)b[4 * i + 1] << 16 | (uint32_t)b[4 * i + 2] << 8 | b[4 * i + 3];
    for (int i = 16; i < 80; i++) w[i] = hl_rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
    uint32_t a = h[0], bb = h[1], c = h[2], d = h[3], e = h[4];
    for (int i = 0; i < 80; i++) {
        uint32_t f, k;
        if (i < 20) { f = (bb & c) | (~bb & d); k = 0x5a827999; }
        else if (i < 40) { f = bb ^ c ^ d; k = 0x6ed9eba1; }
        else if (i < 60) { f = (bb & c) | (bb & d) | (c & d); k = 0x8f1bbcdc; }
        else { f = bb ^ c ^ d; k = 0xca62c1d6; }
        uint32_t t = hl_rol(a, 5) + f + e + k + w[i];
        e = d; d = c; c = hl_rol(bb, 30); bb = a; a = t;
    }
    h[0] += a; h[1] += bb; h[2] += c; h[3] += d; h[4] += e;
}

static sl_str hl_sha1(sl_str s) {
    uint32_t h[5] = {0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0};
    hl_blocks(s.p, (size_t)s.n, 64, true, hl_sha1_block, h);
    uint8_t out[20];
    for (int i = 0; i < 20; i++) out[i] = (uint8_t)(h[i / 4] >> (24 - 8 * (i % 4)));
    return hl_bytes(out, 20);
}

/* ---- SHA-256 ---- */
static void hl_sha256_block(void *sv, const uint8_t *b) {
    static const uint32_t K[64] = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
    uint32_t *h = sv, w[64];
    for (int i = 0; i < 16; i++)
        w[i] = (uint32_t)b[4 * i] << 24 | (uint32_t)b[4 * i + 1] << 16 | (uint32_t)b[4 * i + 2] << 8 | b[4 * i + 3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = hl_ror(w[i - 15], 7) ^ hl_ror(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = hl_ror(w[i - 2], 17) ^ hl_ror(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint32_t v[8];
    memcpy(v, h, sizeof v);
    for (int i = 0; i < 64; i++) {
        uint32_t S1 = hl_ror(v[4], 6) ^ hl_ror(v[4], 11) ^ hl_ror(v[4], 25);
        uint32_t ch = (v[4] & v[5]) ^ (~v[4] & v[6]);
        uint32_t t1 = v[7] + S1 + ch + K[i] + w[i];
        uint32_t S0 = hl_ror(v[0], 2) ^ hl_ror(v[0], 13) ^ hl_ror(v[0], 22);
        uint32_t mj = (v[0] & v[1]) ^ (v[0] & v[2]) ^ (v[1] & v[2]);
        memmove(v + 1, v, 7 * sizeof(uint32_t));
        v[4] += t1;
        v[0] = t1 + S0 + mj;
    }
    for (int i = 0; i < 8; i++) h[i] += v[i];
}

static sl_str hl_sha256(sl_str s) {
    uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    hl_blocks(s.p, (size_t)s.n, 64, true, hl_sha256_block, h);
    uint8_t out[32];
    for (int i = 0; i < 32; i++) out[i] = (uint8_t)(h[i / 4] >> (24 - 8 * (i % 4)));
    return hl_bytes(out, 32);
}

/* ---- SHA-512 ---- */
static void hl_sha512_block(void *sv, const uint8_t *b) {
    static const uint64_t K[80] = {
        0x428a2f98d728ae22ull, 0x7137449123ef65cdull, 0xb5c0fbcfec4d3b2full, 0xe9b5dba58189dbbcull, 0x3956c25bf348b538ull,
        0x59f111f1b605d019ull, 0x923f82a4af194f9bull, 0xab1c5ed5da6d8118ull, 0xd807aa98a3030242ull, 0x12835b0145706fbeull,
        0x243185be4ee4b28cull, 0x550c7dc3d5ffb4e2ull, 0x72be5d74f27b896full, 0x80deb1fe3b1696b1ull, 0x9bdc06a725c71235ull,
        0xc19bf174cf692694ull, 0xe49b69c19ef14ad2ull, 0xefbe4786384f25e3ull, 0x0fc19dc68b8cd5b5ull, 0x240ca1cc77ac9c65ull,
        0x2de92c6f592b0275ull, 0x4a7484aa6ea6e483ull, 0x5cb0a9dcbd41fbd4ull, 0x76f988da831153b5ull, 0x983e5152ee66dfabull,
        0xa831c66d2db43210ull, 0xb00327c898fb213full, 0xbf597fc7beef0ee4ull, 0xc6e00bf33da88fc2ull, 0xd5a79147930aa725ull,
        0x06ca6351e003826full, 0x142929670a0e6e70ull, 0x27b70a8546d22ffcull, 0x2e1b21385c26c926ull, 0x4d2c6dfc5ac42aedull,
        0x53380d139d95b3dfull, 0x650a73548baf63deull, 0x766a0abb3c77b2a8ull, 0x81c2c92e47edaee6ull, 0x92722c851482353bull,
        0xa2bfe8a14cf10364ull, 0xa81a664bbc423001ull, 0xc24b8b70d0f89791ull, 0xc76c51a30654be30ull, 0xd192e819d6ef5218ull,
        0xd69906245565a910ull, 0xf40e35855771202aull, 0x106aa07032bbd1b8ull, 0x19a4c116b8d2d0c8ull, 0x1e376c085141ab53ull,
        0x2748774cdf8eeb99ull, 0x34b0bcb5e19b48a8ull, 0x391c0cb3c5c95a63ull, 0x4ed8aa4ae3418acbull, 0x5b9cca4f7763e373ull,
        0x682e6ff3d6b2b8a3ull, 0x748f82ee5defb2fcull, 0x78a5636f43172f60ull, 0x84c87814a1f0ab72ull, 0x8cc702081a6439ecull,
        0x90befffa23631e28ull, 0xa4506cebde82bde9ull, 0xbef9a3f7b2c67915ull, 0xc67178f2e372532bull, 0xca273eceea26619cull,
        0xd186b8c721c0c207ull, 0xeada7dd6cde0eb1eull, 0xf57d4f7fee6ed178ull, 0x06f067aa72176fbaull, 0x0a637dc5a2c898a6ull,
        0x113f9804bef90daeull, 0x1b710b35131c471bull, 0x28db77f523047d84ull, 0x32caab7b40c72493ull, 0x3c9ebe0a15c9bebcull,
        0x431d67c49c100d4cull, 0x4cc5d4becb3e42b6ull, 0x597f299cfc657e2aull, 0x5fcb6fab3ad6faecull, 0x6c44198c4a475817ull};
    uint64_t *h = sv, w[80];
    for (int i = 0; i < 16; i++) {
        w[i] = 0;
        for (int k = 0; k < 8; k++) w[i] = w[i] << 8 | b[8 * i + k];
    }
    for (int i = 16; i < 80; i++) {
        uint64_t s0 = hl_ror64(w[i - 15], 1) ^ hl_ror64(w[i - 15], 8) ^ (w[i - 15] >> 7);
        uint64_t s1 = hl_ror64(w[i - 2], 19) ^ hl_ror64(w[i - 2], 61) ^ (w[i - 2] >> 6);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    uint64_t v[8];
    memcpy(v, h, sizeof v);
    for (int i = 0; i < 80; i++) {
        uint64_t S1 = hl_ror64(v[4], 14) ^ hl_ror64(v[4], 18) ^ hl_ror64(v[4], 41);
        uint64_t ch = (v[4] & v[5]) ^ (~v[4] & v[6]);
        uint64_t t1 = v[7] + S1 + ch + K[i] + w[i];
        uint64_t S0 = hl_ror64(v[0], 28) ^ hl_ror64(v[0], 34) ^ hl_ror64(v[0], 39);
        uint64_t mj = (v[0] & v[1]) ^ (v[0] & v[2]) ^ (v[1] & v[2]);
        memmove(v + 1, v, 7 * sizeof(uint64_t));
        v[4] += t1;
        v[0] = t1 + S0 + mj;
    }
    for (int i = 0; i < 8; i++) h[i] += v[i];
}

static sl_str hl_sha512(sl_str s) {
    uint64_t h[8] = {0x6a09e667f3bcc908ull, 0xbb67ae8584caa73bull, 0x3c6ef372fe94f82bull, 0xa54ff53a5f1d36f1ull,
                     0x510e527fade682d1ull, 0x9b05688c2b3e6c1full, 0x1f83d9abfb41bd6bull, 0x5be0cd19137e2179ull};
    hl_blocks(s.p, (size_t)s.n, 128, true, hl_sha512_block, h);
    uint8_t out[64];
    for (int i = 0; i < 64; i++) out[i] = (uint8_t)(h[i / 8] >> (56 - 8 * (i % 8)));
    return hl_bytes(out, 64);
}

/* ---- CRC-32 (the zlib/PNG polynomial) ---- */
static int64_t hl_crc32(sl_str s) {
    uint32_t c = 0xffffffffu;
    for (int64_t i = 0; i < s.n; i++) {
        c ^= s.p[i];
        for (int k = 0; k < 8; k++) c = (c >> 1) ^ (0xedb88320u & -(c & 1));
    }
    return (int64_t)(c ^ 0xffffffffu);
}

/* ---- HMAC (RFC 2104) over any of the digests above ---- */
static sl_str hl_digest(int64_t kind, sl_str s) {
    switch (kind) {
    case 0: return hl_md5(s);
    case 1: return hl_sha1(s);
    case 2: return hl_sha256(s);
    default: return hl_sha512(s);
    }
}

static sl_str hl_hmac(int64_t kind, sl_str key, sl_str msg) {
    size_t bs = kind == 3 ? 128 : 64;
    uint8_t k[128] = {0};
    if ((size_t)key.n > bs) {
        sl_str d = hl_digest(kind, key);
        memcpy(k, d.p, (size_t)d.n);
    } else {
        memcpy(k, key.p, (size_t)key.n);
    }
    uint8_t *buf = sl_alloc(bs + (size_t)msg.n + 64 + 1);
    for (size_t i = 0; i < bs; i++) buf[i] = k[i] ^ 0x36;
    memcpy(buf + bs, msg.p, (size_t)msg.n);
    sl_str inner = hl_digest(kind, (sl_str){buf, (int64_t)(bs + (size_t)msg.n)});
    for (size_t i = 0; i < bs; i++) buf[i] = k[i] ^ 0x5c;
    memcpy(buf + bs, inner.p, (size_t)inner.n);
    return hl_digest(kind, (sl_str){buf, (int64_t)(bs + (size_t)inner.n)});
}

/* A string holding exactly these bytes (they need not be valid UTF-8). */
static sl_str hl_from_bytes(sl_list *b) {
    return hl_bytes((const uint8_t *)b->p, (size_t)b->n);
}
