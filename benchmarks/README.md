# Benchmarks

Six small programs, each written three times: in Silly, in idiomatic C++, and in
idiomatic Rust. Each version uses the same algorithm and data, and prints the
same output. `run.py` refuses to report numbers if any output differs.

```
python3 benchmarks/run.py              # all, best of 5, plain table
python3 benchmarks/run.py -n 7 --markdown
python3 benchmarks/run.py trees        # just one
python3 benchmarks/run.py --opt fast   # -O3 -march=native / target-cpu=native everywhere
```

Flags: Silly `--opt release` (gcc `-O2`), C++ `g++ -O2 -std=c++20`, Rust
`rustc -C opt-level=3`. Time is the best wall-clock time over N runs. Memory is
peak RSS from `wait4()`, measured through the tiny `memtime.c` helper. A
process's peak RSS carries over across `exec`, so forking straight from Python
would put a 16 MiB floor under every number. Peak RSS includes each runtime's
own baseline, which is why Rust programs sit near 2 MiB and the C ones near 4 MiB.

## Results

AMD Ryzen 5 5600, gcc 16.2.1, rustc 1.98.1, Linux 7.2. Best of 7.

| benchmark | language | time (ms) | peak RSS (MiB) |
|---|---|---:|---:|
| nbody 5000000 | Silly | 270.7 | 4.5 |
| nbody 5000000 | C++ | 269.7 | 4.2 |
| nbody 5000000 | Rust | 166.6 | 2.2 |
| trees 18 | Silly | 258.2 | 12.2 |
| trees 18 | C++ | 1610.1 | 36.2 |
| trees 18 | Rust | 1993.0 | 34.1 |
| trees 18 | C++ (arena) | 219.3 | 16.1 |
| trees 18 | Rust (arena) | 235.4 | 12.1 |
| wordfreq 2000000 | Silly | 205.2 | 134.1 |
| wordfreq 2000000 | C++ | 176.9 | 96.8 |
| wordfreq 2000000 | Rust | 273.4 | 127.9 |
| collatz 1000000 | Silly | 198.1 | 4.2 |
| collatz 1000000 | C++ | 316.7 | 4.1 |
| collatz 1000000 | Rust | 250.2 | 2.4 |
| strings 2000000 | Silly | 101.0 | 4.1 |
| strings 2000000 | C++ | 286.4 | 4.2 |
| strings 2000000 | Rust | 227.4 | 2.3 |
| sieve 50000000 | Silly | 359.1 | 52.2 |
| sieve 50000000 | C++ | 341.1 | 51.6 |
| sieve 50000000 | Rust | 350.9 | 49.9 |

## What the numbers say

**Silly wins where allocation dominates.** `trees` (binary trees),
`collatz` (one short-lived list per iteration) and `strings` (format,
split, parse) spend most of their time in `malloc`/`free` when written
idiomatically in C++ and Rust. In Silly the same code bumps a pointer and resets
it at the end of the scope.
On `trees`, Silly is 6–8× faster and uses about a third of the memory. On
`strings` it is about 2.5× faster.

**Hand-written arenas close the gap.** `trees_arena.cpp` and
`trees_arena.rs` use a flat node pool indexed by integers, the way you would
write it in C++ or Rust to make it fast. They match or beat Silly slightly. The
point of Silly is that its *ordinary* code already behaves like the arena
version. It does not beat a carefully tuned C++ program.

**Pure computation is a tie, except nbody vs Rust.** `nbody` and `sieve` do no
allocation in their hot loops, so all three compile to essentially the same
machine code. Silly and C++ are within noise of each other. Rust's nbody lead
comes from LLVM inlining `advance` into `main` and noticing the body list
always has length 5, so it fully unrolls the pair loop. With
`#[inline(never)]` on `advance`, Rust takes 272 ms, the same as the
other two. Compiling Silly's generated C with clang instead of gcc does not
change this. Bounds checks, `restrict` and strict aliasing made no measurable
difference either; that was checked by hand-editing the generated C.

**Silly loses wordfreq memory, and here is why.** `wordfreq` keeps 2 million
freshly formatted words alive in one list. Each `f"..."` string lands on the
data stack above the list's buffer, so the list can't grow in place. Every
time the list doubles, the old buffer stays dead on the stack until `main`
returns. That's the cost of a model with no `free`. Growth interleaved with
other long-lived allocations wastes up to the size of the final buffer. C++ also
hashes `string_view`s with a cheaper hash than Rust's default SipHash,
which is most of Rust's time gap here.

## The programs

| name | what it stresses | Silly | C++ | Rust |
|---|---|---|---|---|
| nbody | float math on a small array of structs | `list[Body]` | `std::vector<Body>` | `Vec<Body>` |
| trees | allocate and walk millions of tiny trees | list-backed node pool | `unique_ptr` nodes | `Box` nodes |
| wordfreq | strings + hash map | `map[str,int]` | `unordered_map<string_view,long>` | `HashMap<&str,i64>` |
| collatz | one short-lived list per iteration | `list[int]` | `std::vector` | `Vec` |
| strings | format, split, parse small strings | f-strings, `.split` | `std::to_string`, `substr` | `format!`, `split` |
| sieve | one large flat buffer | `list[bool]` | `std::vector<char>` | `Vec<bool>` |

Silly has no pointers, so a tree in Silly *is* an index-based pool by
construction. That is a fair comparison of what each language makes natural, but
it's also why the arena variants exist: read them before concluding anything.
