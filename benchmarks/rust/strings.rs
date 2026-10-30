// Small strings, idiomatic Rust: format!, split into a Vec, parse.
fn main() {
    let n: i64 = std::env::args().nth(1).map_or(100000, |s| s.parse().unwrap());
    let (mut total, mut chars) = (0i64, 0usize);
    for i in 0..n {
        let rec = format!("id{}:{}:{}", i, i * 7 % 1000, i % 13);
        chars += rec.len();
        let parts: Vec<&str> = rec.split(':').collect();
        total += parts[1].parse::<i64>().unwrap() * parts[2].parse::<i64>().unwrap();
        if parts[0].ends_with("99") { total += 1; }
    }
    println!("{} {}", total, chars);
}
