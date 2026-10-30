// N-body simulation (the Computer Language Benchmarks Game algorithm), plain idiomatic C++.
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

constexpr double PI = 3.141592653589793;
constexpr double SOLAR_MASS = 4.0 * PI * PI;
constexpr double DAYS = 365.24;

struct Body { double x, y, z, vx, vy, vz, m; };

static std::vector<Body> planets() {
    return {
        {0, 0, 0, 0, 0, 0, SOLAR_MASS},
        {4.84143144246472090e+00, -1.16032004402742839e+00, -1.03622044471123109e-01,
         1.66007664274403694e-03 * DAYS, 7.69901118419740425e-03 * DAYS, -6.90460016972063023e-05 * DAYS,
         9.54791938424326609e-04 * SOLAR_MASS},
        {8.34336671824457987e+00, 4.12479856412430479e+00, -4.03523417114321381e-01,
         -2.76742510726862411e-03 * DAYS, 4.99852801234917238e-03 * DAYS, 2.30417297573763929e-05 * DAYS,
         2.85885980666130812e-04 * SOLAR_MASS},
        {1.28943695621391310e+01, -1.51111514016986312e+01, -2.23307578892655734e-01,
         2.96460137564761618e-03 * DAYS, 2.37847173959480950e-03 * DAYS, -2.96589568540237556e-05 * DAYS,
         4.36624404335156298e-05 * SOLAR_MASS},
        {1.53796971148509165e+01, -2.59193146099879641e+01, 1.79258772950371181e-01,
         2.68067772490389322e-03 * DAYS, 1.62824170038242295e-03 * DAYS, -9.51592254519715870e-05 * DAYS,
         5.15138902046611451e-05 * SOLAR_MASS},
    };
}

static void offset(std::vector<Body> &bs) {
    double px = 0, py = 0, pz = 0;
    for (const Body &b : bs) { px += b.vx * b.m; py += b.vy * b.m; pz += b.vz * b.m; }
    bs[0].vx = -px / SOLAR_MASS; bs[0].vy = -py / SOLAR_MASS; bs[0].vz = -pz / SOLAR_MASS;
}

static double energy(const std::vector<Body> &bs) {
    double e = 0;
    size_t n = bs.size();
    for (size_t i = 0; i < n; i++) {
        const Body &b = bs[i];
        e += 0.5 * b.m * (b.vx * b.vx + b.vy * b.vy + b.vz * b.vz);
        for (size_t j = i + 1; j < n; j++) {
            const Body &c = bs[j];
            double dx = b.x - c.x, dy = b.y - c.y, dz = b.z - c.z;
            e -= b.m * c.m / std::sqrt(dx * dx + dy * dy + dz * dz);
        }
    }
    return e;
}

static void advance(std::vector<Body> &bs, double dt) {
    size_t n = bs.size();
    for (size_t i = 0; i < n; i++)
        for (size_t j = i + 1; j < n; j++) {
            double dx = bs[i].x - bs[j].x, dy = bs[i].y - bs[j].y, dz = bs[i].z - bs[j].z;
            double d2 = dx * dx + dy * dy + dz * dz;
            double mag = dt / (d2 * std::sqrt(d2));
            double mi = bs[i].m * mag, mj = bs[j].m * mag;
            bs[i].vx -= dx * mj; bs[i].vy -= dy * mj; bs[i].vz -= dz * mj;
            bs[j].vx += dx * mi; bs[j].vy += dy * mi; bs[j].vz += dz * mi;
        }
    for (Body &b : bs) { b.x += dt * b.vx; b.y += dt * b.vy; b.z += dt * b.vz; }
}

int main(int argc, char **argv) {
    long n = argc > 1 ? std::atol(argv[1]) : 1000;
    auto bs = planets();
    offset(bs);
    std::printf("%.9f\n", energy(bs));
    for (long i = 0; i < n; i++) advance(bs, 0.01);
    std::printf("%.9f\n", energy(bs));
}
