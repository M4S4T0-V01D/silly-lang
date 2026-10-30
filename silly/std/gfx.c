/* Native half of std/gfx: canvases, anti-aliased drawing, text, PNG output, and
 * windows. Windows use SDL2, loaded with dlopen when the first one opens, so a
 * program builds without SDL headers. Without SDL or a display (or with
 * SILLY_GFX=headless) windows are headless: presented frames go nowhere, or to
 * the PNG file named by SILLY_GFX_SHOT, and the window asks to close after
 * SILLY_GFX_FRAMES frames (default 3).
 *
 * Colors are 0xAARRGGBB. Canvases are handles into a table; none of this is
 * thread-safe, so keep a GUI on one thread. */

#include <dlfcn.h>
#include <math.h>
#include <time.h>

/* ---------------- canvases ---------------- */

typedef struct { uint32_t *px; int w, h, cx0, cy0, cx1, cy1, live; } gx_canvas;
static gx_canvas *gx_cv;
static int gx_ncv;

static gx_canvas *gx_get(int64_t id) {
    if (id <= 0 || id > gx_ncv || !gx_cv[id - 1].live) sl_panic("gfx", "%s", "invalid or freed canvas");
    return &gx_cv[id - 1];
}

static int64_t gx_canvas_new(int64_t w, int64_t h) {
    if (w < 1) w = 1;
    if (h < 1) h = 1;
    if (w > 16384 || h > 16384) sl_panic("gfx", "%s", "canvas larger than 16384x16384");
    int id = 0;
    for (int i = 0; i < gx_ncv; i++)
        if (!gx_cv[i].live) { id = i + 1; break; }
    if (!id) {
        gx_cv = realloc(gx_cv, sizeof(gx_canvas) * (size_t)(gx_ncv + 1));
        id = ++gx_ncv;
    }
    gx_canvas *c = &gx_cv[id - 1];
    c->px = calloc((size_t)(w * h), 4);
    if (!c->px) sl_panic("gfx", "%s", "out of memory for a canvas");
    c->w = (int)w; c->h = (int)h; c->live = 1;
    c->cx0 = 0; c->cy0 = 0; c->cx1 = (int)w; c->cy1 = (int)h;
    return id;
}

static void gx_canvas_free(int64_t id) {
    gx_canvas *c = gx_get(id);
    free(c->px);
    c->px = NULL;
    c->live = 0;
}

static void gx_resize(int64_t id, int64_t w, int64_t h) {
    gx_canvas *c = gx_get(id);
    if (w < 1) w = 1;
    if (h < 1) h = 1;
    if (w == c->w && h == c->h) return;
    uint32_t *n = calloc((size_t)(w * h), 4);
    if (!n) sl_panic("gfx", "%s", "out of memory for a canvas");
    for (int y = 0; y < c->h && y < h; y++)
        memcpy(n + y * w, c->px + y * c->w, 4 * (size_t)(c->w < w ? c->w : w));
    free(c->px);
    c->px = n; c->w = (int)w; c->h = (int)h;
    c->cx0 = 0; c->cy0 = 0; c->cx1 = (int)w; c->cy1 = (int)h;
}

static int64_t gx_width(int64_t id) { return gx_get(id)->w; }
static int64_t gx_height(int64_t id) { return gx_get(id)->h; }

static void gx_clip(int64_t id, int64_t x, int64_t y, int64_t w, int64_t h) {
    gx_canvas *c = gx_get(id);
    int64_t x1 = x + w, y1 = y + h;
    c->cx0 = (int)(x < 0 ? 0 : x > c->w ? c->w : x);
    c->cy0 = (int)(y < 0 ? 0 : y > c->h ? c->h : y);
    c->cx1 = (int)(x1 < c->cx0 ? c->cx0 : x1 > c->w ? c->w : x1);
    c->cy1 = (int)(y1 < c->cy0 ? c->cy0 : y1 > c->h ? c->h : y1);
}

static void gx_unclip(int64_t id) {
    gx_canvas *c = gx_get(id);
    c->cx0 = 0; c->cy0 = 0; c->cx1 = c->w; c->cy1 = c->h;
}

/* Blend color `s` over pixel `d` with extra coverage `cov` (0..255). */
static inline void gx_blend(uint32_t *d, uint32_t s, unsigned cov) {
    unsigned a = ((s >> 24) * cov + 127) / 255;
    if (a >= 255) { *d = s | 0xFF000000u; return; }
    if (!a) return;
    uint32_t o = *d;
    unsigned ia = 255 - a, da = o >> 24;
    if (da == 255) {
        unsigned r = (((s >> 16) & 255) * a + ((o >> 16) & 255) * ia + 127) / 255;
        unsigned g = (((s >> 8) & 255) * a + ((o >> 8) & 255) * ia + 127) / 255;
        unsigned b = ((s & 255) * a + (o & 255) * ia + 127) / 255;
        *d = 0xFF000000u | (r << 16) | (g << 8) | b;
        return;
    }
    /* straight alpha over a translucent destination */
    unsigned dw = (da * ia + 127) / 255, oa = a + dw;
    if (!oa) { *d = 0; return; }
    unsigned r = (((s >> 16) & 255) * a + ((o >> 16) & 255) * dw + oa / 2) / oa;
    unsigned g = (((s >> 8) & 255) * a + ((o >> 8) & 255) * dw + oa / 2) / oa;
    unsigned b = ((s & 255) * a + (o & 255) * dw + oa / 2) / oa;
    *d = (oa << 24) | (r << 16) | (g << 8) | b;
}

static inline void gx_plot(gx_canvas *c, int x, int y, uint32_t s, unsigned cov) {
    if (x >= c->cx0 && x < c->cx1 && y >= c->cy0 && y < c->cy1) gx_blend(&c->px[y * c->w + x], s, cov);
}

static void gx_fill_rect(int64_t id, int64_t x, int64_t y, int64_t w, int64_t h, int64_t color) {
    gx_canvas *c = gx_get(id);
    uint32_t s = (uint32_t)color;
    int64_t x0 = x < c->cx0 ? c->cx0 : x, y0 = y < c->cy0 ? c->cy0 : y;
    int64_t x1 = x + w > c->cx1 ? c->cx1 : x + w, y1 = y + h > c->cy1 ? c->cy1 : y + h;
    if (x0 >= x1 || y0 >= y1) return;
    if ((s >> 24) == 255) {
        for (int64_t yy = y0; yy < y1; yy++) {
            uint32_t *row = c->px + yy * c->w;
            for (int64_t xx = x0; xx < x1; xx++) row[xx] = s;
        }
    } else {
        for (int64_t yy = y0; yy < y1; yy++)
            for (int64_t xx = x0; xx < x1; xx++) gx_blend(&c->px[yy * c->w + xx], s, 255);
    }
}

static void gx_clear(int64_t id, int64_t color) {
    gx_canvas *c = gx_get(id);
    uint32_t s = (uint32_t)color;
    for (int y = c->cy0; y < c->cy1; y++)
        for (int x = c->cx0; x < c->cx1; x++) c->px[y * c->w + x] = s;
}

static void gx_rect(int64_t id, int64_t x, int64_t y, int64_t w, int64_t h, int64_t t, int64_t color) {
    if (t * 2 >= w || t * 2 >= h) { gx_fill_rect(id, x, y, w, h, color); return; }
    gx_fill_rect(id, x, y, w, t, color);
    gx_fill_rect(id, x, y + h - t, w, t, color);
    gx_fill_rect(id, x, y + t, t, h - 2 * t, color);
    gx_fill_rect(id, x + w - t, y + t, t, h - 2 * t, color);
}

static void gx_set_pixel(int64_t id, int64_t x, int64_t y, int64_t color) {
    gx_canvas *c = gx_get(id);
    if (x >= c->cx0 && x < c->cx1 && y >= c->cy0 && y < c->cy1) c->px[y * c->w + x] = (uint32_t)color;
}

static int64_t gx_get_pixel(int64_t id, int64_t x, int64_t y) {
    gx_canvas *c = gx_get(id);
    if (x < 0 || y < 0 || x >= c->w || y >= c->h) return 0;
    return c->px[y * c->w + x];
}

static void gx_blend_pixel(int64_t id, int64_t x, int64_t y, int64_t color) {
    gx_plot(gx_get(id), (int)x, (int)y, (uint32_t)color, 255);
}

static inline unsigned gx_cov(double d) { /* coverage of a pixel whose centre is d inside an edge */
    if (d >= 0.5) return 255;
    if (d <= -0.5) return 0;
    return (unsigned)((d + 0.5) * 255.0 + 0.5);
}

/* Signed distance from (px,py) into a rounded rectangle; positive inside. */
static inline double gx_rr_dist(double px, double py, double x0, double y0, double x1, double y1, double r) {
    double cx = px < x0 + r ? x0 + r : px > x1 - r ? x1 - r : px;
    double cy = py < y0 + r ? y0 + r : py > y1 - r ? y1 - r : py;
    double dx = px - cx, dy = py - cy;
    if ((dx != 0 || dy != 0) && r > 0) return r - sqrt(dx * dx + dy * dy);
    double a = px - x0, b = x1 - px, cc = py - y0, d = y1 - py;
    double m = a < b ? a : b;
    if (cc < m) m = cc;
    if (d < m) m = d;
    return m;
}

static void gx_rr(int64_t id, double x, double y, double w, double h, double r, double t, uint32_t s) {
    gx_canvas *c = gx_get(id);
    if (w <= 0 || h <= 0) return;
    if (r * 2 > w) r = w / 2;
    if (r * 2 > h) r = h / 2;
    if (r < 0) r = 0;
    int ix0 = (int)floor(x), iy0 = (int)floor(y), ix1 = (int)ceil(x + w), iy1 = (int)ceil(y + h);
    if (ix0 < c->cx0) ix0 = c->cx0;
    if (iy0 < c->cy0) iy0 = c->cy0;
    if (ix1 > c->cx1) ix1 = c->cx1;
    if (iy1 > c->cy1) iy1 = c->cy1;
    for (int py = iy0; py < iy1; py++) {
        double fy = py + 0.5;
        int flat = t <= 0 && fy > y + r + 0.5 && fy < y + h - r - 0.5;
        for (int px = ix0; px < ix1; px++) {
            double fx = px + 0.5;
            unsigned cov;
            if (flat && fx > x + 0.5 && fx < x + w - 0.5) cov = 255;
            else {
                double d = gx_rr_dist(fx, fy, x, y, x + w, y + h, r);
                cov = gx_cov(d);
                if (t > 0 && cov) {
                    unsigned in = gx_cov(d - t);
                    cov = cov > in ? cov - in : 0;
                }
            }
            if (cov) gx_blend(&c->px[py * c->w + px], s, cov);
        }
    }
}

static void gx_fill_round_rect(int64_t id, int64_t x, int64_t y, int64_t w, int64_t h, int64_t r, int64_t color) {
    if (r <= 0) { gx_fill_rect(id, x, y, w, h, color); return; }
    gx_rr(id, (double)x, (double)y, (double)w, (double)h, (double)r, 0, (uint32_t)color);
}

static void gx_round_rect(int64_t id, int64_t x, int64_t y, int64_t w, int64_t h, int64_t r, int64_t t, int64_t color) {
    if (r <= 0) { gx_rect(id, x, y, w, h, t, color); return; }
    gx_rr(id, (double)x, (double)y, (double)w, (double)h, (double)r, (double)(t < 1 ? 1 : t), (uint32_t)color);
}

static void gx_fill_circle(int64_t id, double cx, double cy, double r, int64_t color) {
    gx_rr(id, cx - r, cy - r, 2 * r, 2 * r, r, 0, (uint32_t)color);
}

static void gx_circle(int64_t id, double cx, double cy, double r, double t, int64_t color) {
    gx_rr(id, cx - r, cy - r, 2 * r, 2 * r, r, t, (uint32_t)color);
}

/* A line of width `wd` with round caps: coverage from the distance to the segment. */
static void gx_line(int64_t id, double x0, double y0, double x1, double y1, double wd, int64_t color) {
    gx_canvas *c = gx_get(id);
    uint32_t s = (uint32_t)color;
    double hw = wd / 2, dx = x1 - x0, dy = y1 - y0, len2 = dx * dx + dy * dy;
    int bx0 = (int)floor((x0 < x1 ? x0 : x1) - hw - 1), bx1 = (int)ceil((x0 > x1 ? x0 : x1) + hw + 1);
    int by0 = (int)floor((y0 < y1 ? y0 : y1) - hw - 1), by1 = (int)ceil((y0 > y1 ? y0 : y1) + hw + 1);
    if (bx0 < c->cx0) bx0 = c->cx0;
    if (by0 < c->cy0) by0 = c->cy0;
    if (bx1 > c->cx1) bx1 = c->cx1;
    if (by1 > c->cy1) by1 = c->cy1;
    for (int py = by0; py < by1; py++)
        for (int px = bx0; px < bx1; px++) {
            double fx = px + 0.5 - x0, fy = py + 0.5 - y0;
            double t = len2 > 0 ? (fx * dx + fy * dy) / len2 : 0;
            if (t < 0) t = 0;
            if (t > 1) t = 1;
            double ex = fx - t * dx, ey = fy - t * dy;
            unsigned cov = gx_cov(hw - sqrt(ex * ex + ey * ey));
            if (cov) gx_blend(&c->px[py * c->w + px], s, cov);
        }
}

/* Filled polygon from a flat [x0, y0, x1, y1, ...] list, nonzero rule, 4x4 samples per pixel. */
static void gx_fill_poly(int64_t id, sl_list *pts, int64_t color) {
    gx_canvas *c = gx_get(id);
    const double *p = (const double *)pts->p;
    int n = (int)(pts->n / 2);
    if (n < 3) return;
    double mnx = p[0], mxx = p[0], mny = p[1], mxy = p[1];
    for (int i = 1; i < n; i++) {
        if (p[2 * i] < mnx) mnx = p[2 * i];
        if (p[2 * i] > mxx) mxx = p[2 * i];
        if (p[2 * i + 1] < mny) mny = p[2 * i + 1];
        if (p[2 * i + 1] > mxy) mxy = p[2 * i + 1];
    }
    int bx0 = (int)floor(mnx), bx1 = (int)ceil(mxx), by0 = (int)floor(mny), by1 = (int)ceil(mxy);
    if (bx0 < c->cx0) bx0 = c->cx0;
    if (by0 < c->cy0) by0 = c->cy0;
    if (bx1 > c->cx1) bx1 = c->cx1;
    if (by1 > c->cy1) by1 = c->cy1;
    if (bx0 >= bx1 || by0 >= by1) return;
    int bw = bx1 - bx0;
    uint8_t *acc = calloc((size_t)bw, 1);
    for (int py = by0; py < by1; py++) {
        memset(acc, 0, (size_t)bw);
        for (int sy = 0; sy < 4; sy++) {
            double fy = py + (sy + 0.5) / 4;
            double xs[64];
            int dirs[64], k = 0;
            for (int i = 0; i < n && k < 64; i++) {
                double ax = p[2 * i], ay = p[2 * i + 1];
                double bx = p[2 * ((i + 1) % n)], by = p[2 * ((i + 1) % n) + 1];
                if ((ay <= fy) == (by <= fy)) continue;
                xs[k] = ax + (fy - ay) * (bx - ax) / (by - ay);
                dirs[k++] = ay < by ? 1 : -1;
            }
            for (int a = 1; a < k; a++)       /* insertion sort crossings */
                for (int b = a; b > 0 && xs[b - 1] > xs[b]; b--) {
                    double tx = xs[b]; xs[b] = xs[b - 1]; xs[b - 1] = tx;
                    int td = dirs[b]; dirs[b] = dirs[b - 1]; dirs[b - 1] = td;
                }
            int wind = 0;
            for (int a = 0; a + 1 < k; a++) {
                wind += dirs[a];
                if (!wind) continue;
                for (int sx = 0; sx < 4; sx++) {
                    double off = (sx + 0.5) / 4;
                    int lo = (int)ceil(xs[a] - off), hi = (int)ceil(xs[a + 1] - off);
                    for (int x = lo < bx0 ? bx0 : lo; x < hi && x < bx1; x++) acc[x - bx0]++;
                }
            }
        }
        for (int x = 0; x < bw; x++)
            if (acc[x]) gx_blend(&c->px[py * c->w + bx0 + x], (uint32_t)color, acc[x] >= 16 ? 255 : acc[x] * 16);
    }
    free(acc);
}

static void gx_gradient(int64_t id, int64_t x, int64_t y, int64_t w, int64_t h, int64_t c0, int64_t c1, bool vertical) {
    gx_canvas *c = gx_get(id);
    int64_t n = vertical ? h : w;
    for (int64_t i = 0; i < n; i++) {
        double t = n > 1 ? (double)i / (double)(n - 1) : 0;
        uint32_t a = (uint32_t)c0, b = (uint32_t)c1, m = 0;
        for (int sh = 0; sh < 32; sh += 8) {
            double va = (a >> sh) & 255, vb = (b >> sh) & 255;
            m |= (uint32_t)(va + (vb - va) * t + 0.5) << sh;
        }
        if (vertical) gx_fill_rect(id, x, y + i, w, 1, m);
        else gx_fill_rect(id, x + i, y, 1, h, m);
    }
    (void)c;
}

static void gx_blit(int64_t dst, int64_t src, int64_t x, int64_t y, int64_t alpha) {
    gx_canvas *d = gx_get(dst), *s = gx_get(src);
    unsigned al = alpha < 0 ? 0 : alpha > 255 ? 255 : (unsigned)alpha;
    for (int sy = 0; sy < s->h; sy++) {
        int64_t dy = y + sy;
        if (dy < d->cy0 || dy >= d->cy1) continue;
        for (int sx = 0; sx < s->w; sx++) {
            int64_t dx = x + sx;
            if (dx < d->cx0 || dx >= d->cx1) continue;
            gx_blend(&d->px[dy * d->w + dx], s->px[sy * s->w + sx], al);
        }
    }
}

/* Nearest-neighbour scaled copy of all of `src` into the rectangle (x, y, w, h) of `dst`. */
static void gx_blit_scaled(int64_t dst, int64_t src, int64_t x, int64_t y, int64_t w, int64_t h) {
    gx_canvas *d = gx_get(dst), *s = gx_get(src);
    if (w <= 0 || h <= 0) return;
    for (int64_t yy = 0; yy < h; yy++) {
        int64_t dy = y + yy;
        if (dy < d->cy0 || dy >= d->cy1) continue;
        int sy = (int)(yy * s->h / h);
        for (int64_t xx = 0; xx < w; xx++) {
            int64_t dx = x + xx;
            if (dx < d->cx0 || dx >= d->cx1) continue;
            gx_blend(&d->px[dy * d->w + dx], s->px[sy * s->w + (int)(xx * s->w / w)], 255);
        }
    }
}

static void gx_read_pixels(int64_t id, sl_list *out) {
    gx_canvas *c = gx_get(id);
    int64_t n = (int64_t)c->w * c->h;
    for (int64_t i = 0; i < n && i < out->n; i++) ((int64_t *)out->p)[i] = c->px[i];
}

static void gx_write_pixels(int64_t id, sl_list *in) {
    gx_canvas *c = gx_get(id);
    int64_t n = (int64_t)c->w * c->h;
    for (int64_t i = 0; i < n && i < in->n; i++) c->px[i] = (uint32_t)((int64_t *)in->p)[i];
}

/* ---------------- text ---------------- */

/* the glyph tables come from gfx_font.c, included just before this file */

static int32_t *gf_offs[GF_NFONTS];   /* per glyph: its offset into the decoded bits */

static gf_font *gf_pick(int64_t font) {
    int fi = font < 0 || font >= GF_NFONTS ? 0 : (int)font;
    gf_font *f = gf_fonts[fi];
    if (!f->bits) {
        int64_t total = 0;
        for (int i = 0; i < 224; i++) total += f->g[i].w * f->g[i].h;
        f->bits = calloc((size_t)total + 1, 1);
        gf_offs[fi] = malloc(sizeof(int32_t) * 224);
        int64_t at = 0;
        for (int i = 0; i < 224; i++) {
            const char *s = f->src + f->g[i].off;
            int64_t n = f->g[i].w * f->g[i].h, k = 0;
            while (k < n) {
                char ch = *s++;
                if (ch >= 'g' && ch <= 'z') k += ch - 'f';
                else f->bits[at + k++] = (uint8_t)((ch <= '9' ? ch - '0' : ch - 'A' + 10) * 17);
            }
            gf_offs[fi][i] = (int32_t)at;
            at += n;
        }
    }
    return f;
}

static const uint8_t *gf_bits(gf_font *f, const gf_glyph *g) {
    for (int fi = 0; fi < GF_NFONTS; fi++)
        if (gf_fonts[fi] == f) return f->bits + gf_offs[fi][g - f->g];
    return f->bits;
}

/* Next code point from UTF-8; invalid bytes come out as U+FFFD. */
static uint32_t gf_next(const uint8_t **pp, const uint8_t *end) {
    const uint8_t *p = *pp;
    uint32_t c = *p++;
    int extra = c >= 0xF0 ? 3 : c >= 0xE0 ? 2 : c >= 0xC0 ? 1 : 0;
    if (c >= 0x80 && c < 0xC0) { *pp = p; return 0xFFFD; }
    if (extra) {
        c &= 0x3F >> extra;
        for (int i = 0; i < extra; i++) {
            if (p >= end || (*p & 0xC0) != 0x80) { *pp = p; return 0xFFFD; }
            c = (c << 6) | (*p++ & 0x3F);
        }
    }
    *pp = p;
    return c;
}

static const gf_glyph *gf_glyph_of(gf_font *f, uint32_t cp) {
    if (cp < 0x20 || cp > 0xFF || (cp >= 0x7F && cp < 0xA0)) cp = '?';
    return &f->g[cp - 0x20];
}

static int64_t gx_text_width(sl_str s, int64_t font) {
    gf_font *f = gf_pick(font);
    const uint8_t *p = s.p, *end = s.p + s.n;
    int64_t w = 0;
    while (p < end) {
        uint32_t cp = gf_next(&p, end);
        w += cp == '\t' ? 4 * gf_glyph_of(f, ' ')->adv : gf_glyph_of(f, cp)->adv;
    }
    return w;
}

/* Byte offset in `s` of the character boundary nearest to x pixels from its start. */
static int64_t gx_text_index(sl_str s, int64_t font, int64_t x) {
    gf_font *f = gf_pick(font);
    const uint8_t *p = s.p, *end = s.p + s.n;
    int64_t w = 0;
    while (p < end) {
        const uint8_t *at = p;
        uint32_t cp = gf_next(&p, end);
        int adv = cp == '\t' ? 4 * gf_glyph_of(f, ' ')->adv : gf_glyph_of(f, cp)->adv;
        if (x < w + adv / 2) return at - s.p;
        w += adv;
    }
    return s.n;
}

static int64_t gx_font_height(int64_t font) { return gf_pick(font)->height; }
static int64_t gx_font_ascent(int64_t font) { return gf_pick(font)->ascent; }

/* Draws `s` with its line box's top-left corner at (x, y); returns the advance. */
static int64_t gx_text(int64_t id, int64_t x, int64_t y, sl_str s, int64_t color, int64_t font) {
    gx_canvas *c = gx_get(id);
    gf_font *f = gf_pick(font);
    const uint8_t *p = s.p, *end = s.p + s.n;
    int64_t pen = x;
    while (p < end) {
        uint32_t cp = gf_next(&p, end);
        if (cp == '\t') { pen += 4 * gf_glyph_of(f, ' ')->adv; continue; }
        const gf_glyph *g = gf_glyph_of(f, cp);
        if (pen >= c->cx1) break;
        const uint8_t *bits = gf_bits(f, g);
        for (int gy = 0; gy < g->h; gy++) {
            int64_t py = y + g->y + gy;
            if (py < c->cy0 || py >= c->cy1) continue;
            for (int gx = 0; gx < g->w; gx++) {
                unsigned a = bits[gy * g->w + gx];
                int64_t px = pen + g->x + gx;
                if (a && px >= c->cx0 && px < c->cx1) gx_blend(&c->px[py * c->w + px], (uint32_t)color, a);
            }
        }
        pen += g->adv;
    }
    return pen - x;
}

/* ---------------- images ---------------- */

static uint32_t gx_crc_table[256];

static uint32_t gx_crc(uint32_t crc, const uint8_t *p, size_t n) {
    if (!gx_crc_table[1])
        for (uint32_t i = 0; i < 256; i++) {
            uint32_t c = i;
            for (int k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            gx_crc_table[i] = c;
        }
    crc = ~crc;
    while (n--) crc = gx_crc_table[(crc ^ *p++) & 255] ^ (crc >> 8);
    return ~crc;
}

static void gx_be32(uint8_t *p, uint32_t v) { p[0] = v >> 24; p[1] = v >> 16; p[2] = v >> 8; p[3] = v; }

static void gx_chunk(FILE *f, const char *type, const uint8_t *data, uint32_t n) {
    uint8_t hdr[8];
    gx_be32(hdr, n);
    memcpy(hdr + 4, type, 4);
    fwrite(hdr, 1, 8, f);
    fwrite(data, 1, n, f);
    uint32_t crc = gx_crc(gx_crc(0, (const uint8_t *)type, 4), data, n);
    gx_be32(hdr, crc);
    fwrite(hdr, 1, 4, f);
}

/* An RGBA PNG with stored (uncompressed) deflate blocks: simple, and any viewer reads it. */
static bool gx_save_png(int64_t id, sl_str path) {
    gx_canvas *c = gx_get(id);
    FILE *f = fopen(sl_cstr(path), "wb");
    if (!f) return false;
    fwrite("\x89PNG\r\n\x1a\n", 1, 8, f);
    uint8_t ihdr[13];
    gx_be32(ihdr, (uint32_t)c->w);
    gx_be32(ihdr + 4, (uint32_t)c->h);
    ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
    gx_chunk(f, "IHDR", ihdr, 13);
    size_t row = (size_t)c->w * 4 + 1, raw_n = row * (size_t)c->h;
    uint8_t *raw = malloc(raw_n);
    for (int y = 0; y < c->h; y++) {
        uint8_t *r = raw + row * (size_t)y;
        r[0] = 0;
        for (int x = 0; x < c->w; x++) {
            uint32_t v = c->px[y * c->w + x];
            r[1 + 4 * x] = v >> 16; r[2 + 4 * x] = v >> 8; r[3 + 4 * x] = v; r[4 + 4 * x] = v >> 24;
        }
    }
    size_t nblk = (raw_n + 65534) / 65535, zn = 2 + raw_n + 5 * nblk + 4;
    uint8_t *z = malloc(zn), *q = z;
    *q++ = 0x78; *q++ = 0x01;
    uint32_t s1 = 1, s2 = 0;
    for (size_t at = 0; at < raw_n || at == 0; ) {
        size_t n = raw_n - at > 65535 ? 65535 : raw_n - at;
        *q++ = at + n >= raw_n;
        *q++ = n & 255; *q++ = n >> 8; *q++ = ~n & 255; *q++ = (~n >> 8) & 255;
        memcpy(q, raw + at, n);
        for (size_t i = 0; i < n; i++) { s1 = (s1 + raw[at + i]) % 65521; s2 = (s2 + s1) % 65521; }
        q += n;
        at += n;
        if (!n) break;
    }
    gx_be32(q, (s2 << 16) | s1);
    q += 4;
    gx_chunk(f, "IDAT", z, (uint32_t)(q - z));
    gx_chunk(f, "IEND", NULL, 0);
    free(raw);
    free(z);
    return fclose(f) == 0;
}

static bool gx_save_ppm(int64_t id, sl_str path) {
    gx_canvas *c = gx_get(id);
    FILE *f = fopen(sl_cstr(path), "wb");
    if (!f) return false;
    fprintf(f, "P6\n%d %d\n255\n", c->w, c->h);
    for (int i = 0; i < c->w * c->h; i++) {
        uint8_t px[3] = {(uint8_t)(c->px[i] >> 16), (uint8_t)(c->px[i] >> 8), (uint8_t)c->px[i]};
        fwrite(px, 1, 3, f);
    }
    return fclose(f) == 0;
}

/* Loads a binary PPM (P6) or an uncompressed 24/32-bit BMP into a new canvas; 0 on failure. */
static int64_t gx_load_image(sl_str path) {
    FILE *f = fopen(sl_cstr(path), "rb");
    if (!f) return 0;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *b = malloc((size_t)n + 1);
    if (fread(b, 1, (size_t)n, f) != (size_t)n) n = 0;
    fclose(f);
    int64_t id = 0;
    if (n > 2 && b[0] == 'P' && b[1] == '6') {
        int vals[3], k = 0;
        long i = 2;
        while (k < 3 && i < n) {
            while (i < n && (b[i] == ' ' || b[i] == '\n' || b[i] == '\r' || b[i] == '\t' || b[i] == '#')) {
                if (b[i] == '#') while (i < n && b[i] != '\n') i++;
                else i++;
            }
            int v = 0;
            while (i < n && b[i] >= '0' && b[i] <= '9') v = v * 10 + (b[i++] - '0');
            vals[k++] = v;
        }
        i++;
        if (k == 3 && vals[2] == 255 && i + (long)vals[0] * vals[1] * 3 <= n) {
            id = gx_canvas_new(vals[0], vals[1]);
            gx_canvas *c = gx_get(id);
            for (int p = 0; p < vals[0] * vals[1]; p++, i += 3)
                c->px[p] = 0xFF000000u | (uint32_t)b[i] << 16 | (uint32_t)b[i + 1] << 8 | b[i + 2];
        }
    } else if (n > 54 && b[0] == 'B' && b[1] == 'M') {
        uint32_t off = b[10] | b[11] << 8 | b[12] << 16 | (uint32_t)b[13] << 24;
        int32_t w = (int32_t)(b[18] | b[19] << 8 | b[20] << 16 | (uint32_t)b[21] << 24);
        int32_t h = (int32_t)(b[22] | b[23] << 8 | b[24] << 16 | (uint32_t)b[25] << 24);
        int bpp = b[28] | b[29] << 8, comp = b[30];
        int flip = h > 0;
        if (h < 0) h = -h;
        int bytes = bpp / 8;
        long stride = ((long)w * bytes + 3) & ~3L;
        if ((bpp == 24 || bpp == 32) && (comp == 0 || comp == 3) && w > 0 && off + stride * h <= n) {
            id = gx_canvas_new(w, h);
            gx_canvas *c = gx_get(id);
            for (int y = 0; y < h; y++) {
                const uint8_t *r = b + off + stride * (flip ? h - 1 - y : y);
                for (int x = 0; x < w; x++) {
                    const uint8_t *q = r + x * bytes;
                    uint32_t a = bytes == 4 ? q[3] : 255;
                    c->px[y * w + x] = a << 24 | (uint32_t)q[2] << 16 | (uint32_t)q[1] << 8 | q[0];
                }
            }
        }
    }
    free(b);
    return id;
}

/* ---------------- windows ---------------- */

typedef struct { uint32_t type; uint8_t pad[52]; } gx_sdl_event;   /* SDL_Event is 56 bytes */
static struct {
    int (*Init)(uint32_t);
    void *(*CreateWindow)(const char *, int, int, int, int, uint32_t);
    void *(*CreateRenderer)(void *, int, uint32_t);
    void *(*CreateTexture)(void *, uint32_t, int, int, int);
    void (*DestroyTexture)(void *);
    int (*UpdateTexture)(void *, const void *, const void *, int);
    int (*RenderClear)(void *);
    int (*RenderCopy)(void *, void *, const void *, const void *);
    void (*RenderPresent)(void *);
    int (*PollEvent)(void *);
    int (*WaitEventTimeout)(void *, int);
    void (*GetWindowSize)(void *, int *, int *);
    void (*SetWindowTitle)(void *, const char *);
    void (*DestroyRenderer)(void *);
    void (*DestroyWindow)(void *);
    void (*Quit)(void);
    void (*StartTextInput)(void);
    void (*StopTextInput)(void);
    void *(*CreateSystemCursor)(int);
    void (*SetCursor)(void *);
    int (*SetClipboardText)(const char *);
    char *(*GetClipboardText)(void);
    void (*free)(void *);
    const char *(*GetError)(void);
    int (*SetHint)(const char *, const char *);
} sdl;

static struct {
    int open, headless, frames, max_frames, w, h, tex_w, tex_h, quit_sent;
    void *win, *ren, *tex, *cursors[12];
    int64_t ev[6];
    sl_str ev_text;
    char text[32];
    gx_sdl_event pending;
    int has_pending;
} gw;

static int gx_load_sdl(void) {
    const char *mode = getenv("SILLY_GFX");
    if (mode && !strcmp(mode, "headless")) return 0;
    if (!getenv("DISPLAY") && !getenv("WAYLAND_DISPLAY") && !(mode && !strcmp(mode, "sdl"))) return 0;
    void *h = dlopen("libSDL2-2.0.so.0", RTLD_NOW);
    if (!h) h = dlopen("libSDL2.so", RTLD_NOW);
    if (!h) h = dlopen("libSDL2-2.0.0.dylib", RTLD_NOW);
    if (!h) return 0;
#define GX_SYM(f) if (!(*(void **)&sdl.f = dlsym(h, "SDL_" #f))) return 0;
    GX_SYM(Init) GX_SYM(CreateWindow) GX_SYM(CreateRenderer) GX_SYM(CreateTexture) GX_SYM(DestroyTexture)
    GX_SYM(UpdateTexture) GX_SYM(RenderClear) GX_SYM(RenderCopy) GX_SYM(RenderPresent) GX_SYM(PollEvent)
    GX_SYM(WaitEventTimeout) GX_SYM(GetWindowSize) GX_SYM(SetWindowTitle) GX_SYM(DestroyRenderer)
    GX_SYM(DestroyWindow) GX_SYM(Quit) GX_SYM(StartTextInput) GX_SYM(StopTextInput) GX_SYM(CreateSystemCursor)
    GX_SYM(SetCursor) GX_SYM(SetClipboardText) GX_SYM(GetClipboardText) GX_SYM(free) GX_SYM(GetError)
    GX_SYM(SetHint)
#undef GX_SYM
    return 1;
}

static int64_t gx_now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static bool gx_open(sl_str title, int64_t w, int64_t h) {
    if (gw.open) sl_panic("gfx", "%s", "only one window can be open at a time");
    memset(&gw, 0, sizeof gw);
    gw.w = (int)w;
    gw.h = (int)h;
    const char *fr = getenv("SILLY_GFX_FRAMES");
    gw.max_frames = fr ? atoi(fr) : 3;
    if (gx_load_sdl()) {
        sdl.SetHint("SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR", "0");
        if (sdl.Init(0x20) == 0) {
            gw.win = sdl.CreateWindow(sl_cstr(title), 0x2FFF0000, 0x2FFF0000, (int)w, (int)h, 0x4 | 0x20);
            if (gw.win) gw.ren = sdl.CreateRenderer(gw.win, -1, 0x2 | 0x4);
            if (gw.win && !gw.ren) gw.ren = sdl.CreateRenderer(gw.win, -1, 0);
            if (gw.ren) {
                gw.open = 1;
                sdl.StartTextInput();
                return true;
            }
            if (gw.win) sdl.DestroyWindow(gw.win);
            sdl.Quit();
        }
    }
    gw.open = 1;
    gw.headless = 1;
    return true;
}

static sl_str gx_backend(void) {
    const char *s = !gw.open ? "none" : gw.headless ? "headless" : "sdl";
    return (sl_str){(const uint8_t *)s, (int64_t)strlen(s)};
}

static void gx_close(void) {
    if (!gw.open) return;
    if (!gw.headless) {
        if (gw.tex) sdl.DestroyTexture(gw.tex);
        sdl.DestroyRenderer(gw.ren);
        sdl.DestroyWindow(gw.win);
        sdl.Quit();
    }
    gw.open = 0;
}

static void gx_present(int64_t id) {
    gx_canvas *c = gx_get(id);
    if (!gw.open) sl_panic("gfx", "%s", "present() with no open window");
    gw.frames++;
    if (gw.headless) {
        const char *shot = getenv("SILLY_GFX_SHOT");
        if (shot && *shot) gx_save_png(id, (sl_str){(const uint8_t *)shot, (int64_t)strlen(shot)});
        return;
    }
    if (!gw.tex || gw.tex_w != c->w || gw.tex_h != c->h) {
        if (gw.tex) sdl.DestroyTexture(gw.tex);
        gw.tex = sdl.CreateTexture(gw.ren, 0x16362004, 1, c->w, c->h);
        gw.tex_w = c->w;
        gw.tex_h = c->h;
    }
    sdl.UpdateTexture(gw.tex, NULL, c->px, c->w * 4);
    sdl.RenderClear(gw.ren);
    sdl.RenderCopy(gw.ren, gw.tex, NULL, NULL);
    sdl.RenderPresent(gw.ren);
}

static int64_t gx_win_w(void) {
    if (gw.open && !gw.headless) sdl.GetWindowSize(gw.win, &gw.w, &gw.h);
    return gw.w;
}

static int64_t gx_win_h(void) {
    if (gw.open && !gw.headless) sdl.GetWindowSize(gw.win, &gw.w, &gw.h);
    return gw.h;
}

static void gx_set_title(sl_str s) {
    if (gw.open && !gw.headless) sdl.SetWindowTitle(gw.win, sl_cstr(s));
}

static int gx_mods(uint16_t m) {
    return (m & 0x3 ? 1 : 0) | (m & 0xC0 ? 2 : 0) | (m & 0x300 ? 4 : 0) | (m & 0xC00 ? 8 : 0);
}

#define GX_I32(e, o) (*(int32_t *)((uint8_t *)(e) + (o)))
#define GX_U8(e, o) (*((uint8_t *)(e) + (o)))

/* Decodes one SDL event into gw.ev; returns our event type, or -1 to skip it. */
static int gx_decode(gx_sdl_event *e) {
    int64_t *v = gw.ev;
    memset(v, 0, sizeof gw.ev);
    switch (e->type) {
    case 0x100: return 1;
    case 0x200:
        switch (GX_U8(e, 12)) {
        case 6: gw.w = GX_I32(e, 16); gw.h = GX_I32(e, 20); v[0] = gw.w; v[1] = gw.h; return 2;
        case 3: return 12;
        case 12: return 10;
        case 13: return 11;
        case 11: return 13;
        default: return -1;
        }
    case 0x400: v[0] = GX_I32(e, 20); v[1] = GX_I32(e, 24); return 3;
    case 0x401: case 0x402:
        v[0] = GX_I32(e, 20); v[1] = GX_I32(e, 24); v[2] = GX_U8(e, 16); v[3] = GX_U8(e, 18);
        return e->type == 0x401 ? 4 : 5;
    case 0x403: {
        int32_t dx = GX_I32(e, 16), dy = GX_I32(e, 20);
        if (*(uint32_t *)((uint8_t *)e + 24) == 1) { dx = -dx; dy = -dy; }
        v[0] = dx; v[1] = dy;
        return 6;
    }
    case 0x300: case 0x301:
        v[0] = GX_I32(e, 20); v[1] = gx_mods(*(uint16_t *)((uint8_t *)e + 24)); v[2] = GX_U8(e, 13);
        return e->type == 0x300 ? 7 : 8;
    case 0x303: {
        memcpy(gw.text, (uint8_t *)e + 12, 32);
        gw.text[31] = 0;
        gw.ev_text = (sl_str){(const uint8_t *)gw.text, (int64_t)strlen(gw.text)};
        return 9;
    }
    default: return -1;
    }
}

/* The next event's type, or 0 when there is none. Fields: gx_ev(0..3), gx_ev_text(). */
static int64_t gx_poll(void) {
    if (!gw.open) return 0;
    if (gw.headless) {
        if (gw.max_frames > 0 && gw.frames >= gw.max_frames && !gw.quit_sent) { gw.quit_sent = 1; return 1; }
        return 0;
    }
    gx_sdl_event e;
    for (;;) {
        if (gw.has_pending) { e = gw.pending; gw.has_pending = 0; }
        else if (!sdl.PollEvent(&e)) return 0;
        int t = gx_decode(&e);
        if (t > 0) return t;
    }
}

/* Sets how many frames a headless window shows before it sends Quit, unless
 * SILLY_GFX_FRAMES overrides it. 0 means never. */
static void gx_headless_frames(int64_t n) {
    if (!getenv("SILLY_GFX_FRAMES")) gw.max_frames = (int)n;
}

/* Waits up to `ms` milliseconds for an event; true if one is ready for gx_poll. */
static bool gx_wait(int64_t ms) {
    if (!gw.open) return false;
    if (gw.headless) return gw.max_frames > 0 && gw.frames >= gw.max_frames && !gw.quit_sent;
    if (gw.has_pending) return true;
    if (sdl.WaitEventTimeout(&gw.pending, (int)ms)) { gw.has_pending = 1; return true; }
    return false;
}

static int64_t gx_ev(int64_t i) { return i >= 0 && i < 6 ? gw.ev[i] : 0; }

static sl_str gx_ev_text(void) {
    uint8_t *p = sl_alloc((size_t)gw.ev_text.n + 1);
    memcpy(p, gw.ev_text.p, (size_t)gw.ev_text.n);
    return (sl_str){p, gw.ev_text.n};
}

static void gx_set_cursor(int64_t kind) {
    if (!gw.open || gw.headless || kind < 0 || kind >= 12) return;
    if (!gw.cursors[kind]) gw.cursors[kind] = sdl.CreateSystemCursor((int)kind);
    if (gw.cursors[kind]) sdl.SetCursor(gw.cursors[kind]);
}

static char *gx_clip_text;   /* headless clipboard */

static void gx_clipboard_set(sl_str s) {
    if (gw.open && !gw.headless) { sdl.SetClipboardText(sl_cstr(s)); return; }
    free(gx_clip_text);
    gx_clip_text = strndup((const char *)s.p, (size_t)s.n);
}

static sl_str gx_clipboard_get(void) {
    char *t = gw.open && !gw.headless ? sdl.GetClipboardText() : gx_clip_text;
    size_t n = t ? strlen(t) : 0;
    uint8_t *p = sl_alloc(n + 1);
    if (n) memcpy(p, t, n);
    if (t && gw.open && !gw.headless) sdl.free(t);
    return (sl_str){p, (int64_t)n};
}

static int64_t gx_ticks(void) {
    static int64_t start;
    if (!start) start = gx_now_ms();
    return gx_now_ms() - start;
}

static void gx_sleep(int64_t ms) {
    if (ms <= 0) return;
    struct timespec ts = {ms / 1000, (ms % 1000) * 1000000};
    nanosleep(&ts, NULL);
}
