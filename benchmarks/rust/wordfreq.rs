// Word frequencies, idiomatic Rust (String, std HashMap with its default hasher).
use std::collections::HashMap;

fn main() {
    let n: usize = std::env::args().nth(1).map_or(100000, |s| s.parse().unwrap());
    let mut words = Vec::new();
    let mut s: u64 = 42;
    for _ in 0..n {
        s = s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        words.push(format!("w{}", (s >> 33) % 50000));
    }
    let text = words.join(" ");
    let mut counts: HashMap<&str, i64> = HashMap::new();
    for w in text.split(' ') {
        *counts.entry(w).or_insert(0) += 1;
    }
    let mut ranked: Vec<(i64, &str)> = counts.iter().map(|(w, c)| (-c, *w)).collect();
    ranked.sort();
    println!("{}", counts.len());
    for &(c, w) in &ranked[..5] {
        println!("{} {}", w, -c);
    }
}
