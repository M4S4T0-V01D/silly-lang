// Short-lived lists, idiomatic Rust: a Vec per start value.
fn path(start: i64) -> Vec<i64> {
    let mut out = Vec::new();
    let mut x = start;
    while x != 1 { out.push(x); x = if x % 2 == 0 { x / 2 } else { 3 * x + 1 }; }
    out.push(1);
    out
}

fn main() {
    let n: i64 = std::env::args().nth(1).map_or(100000, |s| s.parse().unwrap());
    let (mut longest, mut arg, mut peak_sum) = (0usize, 0i64, 0i64);
    for i in 1..n {
        let p = path(i);
        peak_sum += *p.iter().max().unwrap();
        if p.len() > longest { longest = p.len(); arg = i; }
    }
    println!("{} {} {}", arg, longest, peak_sum);
}
