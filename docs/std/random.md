# random

Pseudo-random numbers, like Python's random module.

```silly
import random
fn main():
    print(random.randint(1, 6), random.random())
    var deck = ["A", "K", "Q", "J"]
    random.shuffle(&mut deck)
    print(random.choice(&deck))
    var rng = random.Rng.new(42)     # a reproducible stream of its own
    print(rng.randint(1, 100))
```

The module-level functions share one generator per thread, seeded from the OS;
random.seed(n) makes them repeatable. Both use xoshiro256**, which is fast and
good for simulations and games but not for secrets: use token_hex/os_bytes for those.

## Types

### `Rng`

A seedable generator with its own state.

- `s0: u64`
- `s1: u64`
- `s2: u64`
- `s3: u64`

- `new(seed: int) -> Rng`
- `from_os() -> Rng` — A generator seeded from the operating system.
- `random(mut self) -> f64`
- `uniform(mut self, a: f64, b: f64) -> f64`
- `randint(mut self, a: int, b: int) -> int`
- `randrange(mut self, a: int, b: int) -> int`
- `chance(mut self, p: f64) -> bool`
- `gauss(mut self, mu: f64, sigma: f64) -> f64`
- `expovariate(mut self, lambd: f64) -> f64`
- `weighted(mut self, weights: &list[f64]) -> int`
- `choice[T](mut self, xs: &list[T]) -> T`
- `shuffle[T](mut self, xs: &mut list[T])`
- `sample[T](mut self, xs: &list[T], k: int) -> list[T]`

## Functions

### `seed(n: int)`

Restarts the shared generator from a seed, making later calls repeatable.

### `random() -> f64`

A float in [0, 1).

### `uniform(a: f64, b: f64) -> f64`

A float between a and b.

### `randint(a: int, b: int) -> int`

An int in a..=b (both ends included).

### `randrange(a: int, b: int) -> int`

An int in a..b (b excluded).

### `chance(p: f64) -> bool`

True with probability p.

### `gauss(mu: f64, sigma: f64) -> f64`

A normally distributed float.

### `expovariate(lambd: f64) -> f64`

An exponentially distributed number with rate lambd (mean 1/lambd).

### `weighted(weights: &list[f64]) -> int`

An index into `weights`, chosen in proportion to them.

### `choice[T](xs: &list[T]) -> T`

A random element (a copy of it).

### `shuffle[T](xs: &mut list[T])`

Shuffles a list in place.

### `sample[T](xs: &list[T], k: int) -> list[T]`

k distinct elements, in random order.

### `os_u64() -> int`

A random 64-bit value straight from the operating system (suitable for secrets).

### `token_hex(n: int) -> str`

2n hex digits from the operating system's randomness, for tokens and secrets.
