// Binary trees, idiomatic Rust: one heap allocation per node (Box).
struct Node { kids: Option<(Box<Node>, Box<Node>)> }

fn build(d: u32) -> Box<Node> {
    Box::new(Node { kids: if d > 0 { Some((build(d - 1), build(d - 1))) } else { None } })
}

fn check(n: &Node) -> i64 {
    match &n.kids { Some((l, r)) => 1 + check(l) + check(r), None => 1 }
}

fn main() {
    let n: u32 = std::env::args().nth(1).map_or(10, |s| s.parse().unwrap());
    let maxd = n.max(6);
    println!("stretch tree of depth {}\t check: {}", maxd + 1, check(&build(maxd + 1)));
    let long_lived = build(maxd);
    let mut d = 4;
    while d <= maxd {
        let iters = 1i64 << (maxd - d + 4);
        let sum: i64 = (0..iters).map(|_| check(&build(d))).sum();
        println!("{}\t trees of depth {}\t check: {}", iters, d, sum);
        d += 2;
    }
    println!("long lived tree of depth {}\t check: {}", maxd, check(&long_lived));
}
