// Sieve of Eratosthenes, idiomatic Rust: Vec<bool>.
fn main() {
    let n: usize = std::env::args().nth(1).map_or(1000000, |s| s.parse().unwrap());
    let mut composite = vec![false; n + 1];
    let (mut count, mut last) = (0usize, 0usize);
    for i in 2..=n {
        if !composite[i] {
            count += 1; last = i;
            let mut j = i * i;
            while j <= n { composite[j] = true; j += i; }
        }
    }
    println!("{} {}", count, last);
}
