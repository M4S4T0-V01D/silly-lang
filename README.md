# Silly

**A memory-safe systems language with no heap.** Silly has no allocator, no
garbage collector and no lifetime annotations. Every list, string and map lives
on a data stack that the compiler manages. Growing a value bumps a pointer, and
leaving a scope frees everything it made in one store. The type and ownership
rules make that safe. The syntax is Python's, the types are Rust-shaped, and the
output is native code by way of C.

```python
enum Shape:
    Circle(f64)
    Rect(w: f64, h: f64)

fn area(s: Shape) -> f64:
    match s:
        case Circle(r): return 3.14159 * r * r
        case Rect(w, h): return w * h

fn main():
    var total = 0.0
    for i in 0..1_000_000:
        let shapes = [Shape.Circle(1.0), Shape.Rect(2.0, i as f64)]   # freed every iteration
        for s in shapes:
            total += area(s)
    print(f"{total:.1f}")
```

## Why

Most allocations in real programs follow a stack discipline: a value is built,
used, and dropped at the end of the scope that built it. Silly makes that the
*only* discipline, and gets three things in return:

- **Allocation is a pointer bump and freeing is free.** Allocation-heavy code
  written the obvious way runs like hand-written arena code. On the binary-trees
  benchmark it is 6–8× faster than idiomatic C++ and Rust and uses a third of
  the memory.
- **No lifetimes to write.** References can only be function parameters, so
  every borrow ends when its call returns. The compiler needs no annotations to
  prove that nothing dangles.
- **Predictable memory.** Memory use follows from the shape of the program:
  loops don't accumulate, scopes give back what they took, and there are no GC
  pauses.

The trade-offs are real and documented in
[docs/memory-model.md](docs/memory-model.md). There is no shared ownership, and
graphs are built from indices into a list. A collection that grows while other
long-lived values are allocated above it wastes some space until its scope ends.

## Quick start

Requirements: Python 3.11+ and gcc (and git, for git dependencies).

```sh
export PATH="$PWD/bin:$PATH"
silly run examples/hello.silly
silly run examples/calc.silly "2 * (3 + 4) - 10 / 4"
silly build --opt release examples/wordfreq.silly -o wordfreq
silly test tests/unit/prelude.silly
```

Without the launcher, use `python3 -m silly ...` from this directory.

## A tour

```python
import math

struct Account:
    owner: str
    history: list[int]

    fn balance(self) -> int:
        return sum(self.history)

fn deposit(a: &mut Account, amount: int) -> Result[int, str]:
    if amount <= 0:
        return Err(f"invalid amount {amount}")
    a.history.push(amount)
    return Ok(a.balance())

fn parse_all(xs: &list[str]) -> Result[list[int], str]:
    var out: list[int] = []
    for x in xs:
        out.push(x.parse_int().ok_or(f"not a number: {x}")?)
    return Ok(out)

fn main():
    var acct = Account("ada", [])
    for amt in parse_all(&["10", "25", "7"]).expect("bad input"):
        deposit(&mut acct, amt).unwrap()
    print(acct.owner, acct.balance())            # ada 42

    var seen: map[str, int] = {}
    for w in "the cat saw the dog".split(" "):
        seen[w] = seen.get_or(w, 0) + 1
    print(seen)                                  # {"the": 2, "cat": 1, "saw": 1, "dog": 1}

    let grid: [[u8; 3]; 2] = [[0; 3]; 2]         # fixed arrays are Copy
    print(len(grid), math.gcd(84, 36))           # 2 12
```

Closures, traits and threads:

```python
trait Show:
    fn show(self) -> str
    fn shout(self) -> str:                       # default method
        return self.show().upper() + "!"

impl Show for int:
    fn show(self) -> str:
        return f"#{self}"

fn adder(n: int) -> fn(int) -> int:
    return fn(x) => x + n                        # captures n by value

fn main():
    print(adder(2)(3), [3, 1, 2].map(fn(x) => x * 10), 7.shout())   # 5 [30, 10, 20] #7!
    var tasks: list[Task[int]] = []
    for i in 0..4:
        let lo = i * 25000
        tasks.push(spawn(fn() => count_primes(lo, lo + 25000)))   # own thread, own stack
    print(sum(join_all(tasks)))                  # 9592
```

Packages are directories with a `silly.toml`. `silly new`, `silly add` (path or
git dependencies) and `silly fetch` manage them, and `silly.lock` pins git
revisions.

The standard library has 36 modules in the spirit of Python's: `sys`, `os`,
`path`, `subprocess`, `random`, `math`, `re`, `json`, `csv`, `datetime`,
`logging`, `argparse`, `socket`, `http` and more, plus `gfx` for windows and
drawing and `ui`, a widget toolkit built on it. Each has a page in
[docs/std](docs/std/README.md).

The full language reference is [docs/spec.md](docs/spec.md).

## Safety

Safe Silly can't read freed memory, index out of bounds, or race a mutation
against iteration. These are checked:

| at compile time | at run time (panic, exit 101) |
|---|---|
| use after move, move out of a borrow | out-of-bounds index |
| mutating a list/map while iterating or matching it | missing map key |
| `&mut` aliasing within one call | division by zero |
| references stored, returned or kept in variables | `unwrap` on `None`/`Err`, failed `assert` |
| non-exhaustive `match`, missing `return` | data stack overflow |
| implicit numeric conversions, literal overflow | |

Integer overflow wraps (two's complement) and is never undefined behaviour.
`extern fn` calls into C are the one escape hatch.

## Performance

Measured with `benchmarks/run.py` against idiomatic C++ (`g++ -O2`) and Rust
(`rustc -C opt-level=3`). All three versions print identical output.

| benchmark | Silly | C++ | Rust |
|---|---:|---:|---:|
| trees (alloc-heavy) | **258 ms / 12 MiB** | 1610 ms / 36 MiB | 1993 ms / 34 MiB |
| strings (format/split/parse) | **101 ms** | 286 ms | 227 ms |
| collatz (short-lived lists) | **198 ms** | 317 ms | 250 ms |
| wordfreq (strings + hash map) | 205 ms / 134 MiB | **177 ms / 97 MiB** | 273 ms / 128 MiB |
| nbody (float math) | 271 ms | 270 ms | **167 ms** |
| sieve (one flat buffer) | 359 ms | **341 ms** | 351 ms |

Silly wins where allocation dominates and ties on pure computation. Rust's nbody
lead comes from LLVM inlining away the loop bounds. Silly also loses wordfreq
memory, for a reason explained in the memory-model doc. Hand-written arena
versions of trees in C++ and Rust match Silly; Silly's point is that you get that
behaviour without writing the arena. Full table, method and caveats:
[benchmarks/README.md](benchmarks/README.md).

## How it works

```
source ─▶ lexer ─▶ parser ─▶ checker (types, moves, borrows, escapes) ─▶ C codegen ─▶ gcc
```

The compiler (`silly/`, about 8,000 lines of Python) checks the whole program,
monomorphises generics, and emits one C11 file with the runtime
(`silly/runtime/silly_rt.h`) inlined. For each loop and function it works out
which allocations can be reset at scope exit and which escape, and where results
need compacting. `silly emit-c` shows the output.

`selfhost/sillyc.silly` is a second compiler written in Silly. It compiles Silly
Core, the generics-free subset it is written in, and reproduces its own C
byte for byte (`selfhost/bootstrap.sh`). See [selfhost/README.md](selfhost/README.md).

## Layout

```
silly/            compiler; runtime/silly_rt.h is the whole runtime; std/ is the stdlib; pkg.py is packages
selfhost/         sillyc, the self-hosted compiler for Silly Core, and its bootstrap
docs/             spec.md (language reference), memory-model.md, std/ (one page per module)
examples/         hello, calc (parser + AST), wordfreq, life, memory, ui_demo
tests/            run/ (expected output), fail/ (expected errors), unit/ (@test),
                  pkg_test.py (packages), selfhost_test.py (bootstrap + Core programs)
benchmarks/       Silly / C++ / Rust programs and run.py
tools/            stddoc.py (writes docs/std), genfont.py (gfx's built-in fonts)
bin/silly         launcher
```

Run the test suite with `python3 tests/run_tests.py --both` (debug and release).

## Status

Silly is a young language, but every piece of it is now in place: the type system
(generics, enums with payloads, pattern matching, `Option`/`Result` with `?`,
methods, maps, fixed arrays), closures, traits with bounds and default methods,
threads with share-nothing tasks, packages with path and git dependencies, C FFI,
unit tests, three build modes, and a self-hosted compiler.

Known limits:

- There are no trait objects (`dyn`). Generic code is monomorphised, so a list
  can't hold values of different types that implement one trait. Use an enum.
- Tasks share nothing and have no channels. A task gets its inputs when it is
  spawned and hands back one result when it is joined.
- Closures can't modify what they capture. A function that changes state takes
  it as a `&mut` parameter.
- There is no package registry. Dependencies come from paths or git.
- sillyc compiles only Silly Core, and it relies on `silly check` for ownership
  errors. The Python compiler is the reference.

The fonts built into `gfx` are rasterized from DejaVu; their licence is in
[docs/licenses/dejavu.txt](docs/licenses/dejavu.txt).
