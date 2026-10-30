// N-body simulation (the Computer Language Benchmarks Game algorithm), plain idiomatic Rust.
const PI: f64 = 3.141592653589793;
const SOLAR_MASS: f64 = 4.0 * PI * PI;
const DAYS: f64 = 365.24;

#[derive(Clone, Copy)]
struct Body { x: f64, y: f64, z: f64, vx: f64, vy: f64, vz: f64, m: f64 }

fn body(x: f64, y: f64, z: f64, vx: f64, vy: f64, vz: f64, m: f64) -> Body {
    Body { x, y, z, vx: vx * DAYS, vy: vy * DAYS, vz: vz * DAYS, m: m * SOLAR_MASS }
}

fn planets() -> Vec<Body> {
    vec![
        Body { x: 0.0, y: 0.0, z: 0.0, vx: 0.0, vy: 0.0, vz: 0.0, m: SOLAR_MASS },
        body(4.84143144246472090e+00, -1.16032004402742839e+00, -1.03622044471123109e-01,
             1.66007664274403694e-03, 7.69901118419740425e-03, -6.90460016972063023e-05, 9.54791938424326609e-04),
        body(8.34336671824457987e+00, 4.12479856412430479e+00, -4.03523417114321381e-01,
             -2.76742510726862411e-03, 4.99852801234917238e-03, 2.30417297573763929e-05, 2.85885980666130812e-04),
        body(1.28943695621391310e+01, -1.51111514016986312e+01, -2.23307578892655734e-01,
             2.96460137564761618e-03, 2.37847173959480950e-03, -2.96589568540237556e-05, 4.36624404335156298e-05),
        body(1.53796971148509165e+01, -2.59193146099879641e+01, 1.79258772950371181e-01,
             2.68067772490389322e-03, 1.62824170038242295e-03, -9.51592254519715870e-05, 5.15138902046611451e-05),
    ]
}

fn offset(bs: &mut [Body]) {
    let (mut px, mut py, mut pz) = (0.0, 0.0, 0.0);
    for b in bs.iter() { px += b.vx * b.m; py += b.vy * b.m; pz += b.vz * b.m; }
    bs[0].vx = -px / SOLAR_MASS; bs[0].vy = -py / SOLAR_MASS; bs[0].vz = -pz / SOLAR_MASS;
}

fn energy(bs: &[Body]) -> f64 {
    let mut e = 0.0;
    for i in 0..bs.len() {
        let b = bs[i];
        e += 0.5 * b.m * (b.vx * b.vx + b.vy * b.vy + b.vz * b.vz);
        for c in &bs[i + 1..] {
            let (dx, dy, dz) = (b.x - c.x, b.y - c.y, b.z - c.z);
            e -= b.m * c.m / (dx * dx + dy * dy + dz * dz).sqrt();
        }
    }
    e
}

fn advance(bs: &mut [Body], dt: f64) {
    let n = bs.len();
    for i in 0..n {
        for j in i + 1..n {
            let dx = bs[i].x - bs[j].x;
            let dy = bs[i].y - bs[j].y;
            let dz = bs[i].z - bs[j].z;
            let d2 = dx * dx + dy * dy + dz * dz;
            let mag = dt / (d2 * d2.sqrt());
            let mi = bs[i].m * mag;
            let mj = bs[j].m * mag;
            bs[i].vx -= dx * mj; bs[i].vy -= dy * mj; bs[i].vz -= dz * mj;
            bs[j].vx += dx * mi; bs[j].vy += dy * mi; bs[j].vz += dz * mi;
        }
    }
    for b in bs.iter_mut() { b.x += dt * b.vx; b.y += dt * b.vy; b.z += dt * b.vz; }
}

fn main() {
    let n: usize = std::env::args().nth(1).map_or(1000, |s| s.parse().unwrap());
    let mut bs = planets();
    offset(&mut bs);
    println!("{:.9}", energy(&bs));
    for _ in 0..n { advance(&mut bs, 0.01); }
    println!("{:.9}", energy(&bs));
}
