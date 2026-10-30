// Binary trees, Rust with the same layout as the Silly version: each tree is a
// Vec of (left, right) index pairs.
fn build(ns: &mut Vec<(i32, i32)>, d: u32) -> i32 {
    if d == 0 { ns.push((-1, -1)); } else { let l = build(ns, d - 1); let r = build(ns, d - 1); ns.push((l, r)); }
    ns.len() as i32 - 1
}

fn check(ns: &[(i32, i32)], i: i32) -> i64 {
    let (l, r) = ns[i as usize];
    if l < 0 { 1 } else { 1 + check(ns, l) + check(ns, r) }
}

fn tree_check(d: u32) -> i64 { let mut t = Vec::new(); build(&mut t, d); check(&t, t.len() as i32 - 1) }

fn main() {
    let n: u32 = std::env::args().nth(1).map_or(10, |s| s.parse().unwrap());
    let maxd = n.max(6);
    println!("stretch tree of depth {}\t check: {}", maxd + 1, tree_check(maxd + 1));
    let mut long_lived = Vec::new();
    build(&mut long_lived, maxd);
    let mut d = 4;
    while d <= maxd {
        let iters = 1i64 << (maxd - d + 4);
        let sum: i64 = (0..iters).map(|_| tree_check(d)).sum();
        println!("{}\t trees of depth {}\t check: {}", iters, d, sum);
        d += 2;
    }
    println!("long lived tree of depth {}\t check: {}", maxd, check(&long_lived, long_lived.len() as i32 - 1));
}
