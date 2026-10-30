# The Silly memory model

Silly has no heap allocator, no garbage collector and no lifetime annotations.
Every value is either a fixed-size value held in a local variable, or a dynamic
value (list, string, map) whose contents live on the **data stack**. This
document explains how that works, why it is safe, and what it costs.

## The data stack

At startup the runtime reserves one large range of virtual address space: 32 GiB
by default, set `SILLY_STACK_MB` to change it. It is mapped with
`MAP_NORESERVE`, so untouched pages cost nothing. Allocation moves a single
pointer, `top`, upward. Nothing is ever freed one value at a time.

The compiler saves `top` when a scope starts and restores it when the scope
ends. Everything the scope allocated disappears in one store. The scopes that
reset this way are:

- **function bodies**, for values that aren't returned (see *Returning values*);
- **loop iterations**, where each pass of `for`, `while` or `loop` starts from
  the same `top`. A loop that runs a million times and builds a list every pass
  uses the memory of one list.

Running out of data stack is a clean panic
(`panic: data stack overflow (set SILLY_STACK_MB to reserve more)`), never
undefined behaviour.

## Growth

A list, string or map is a small header (pointer, length, capacity) plus a
buffer on the data stack. When a value needs more room:

- if its buffer is the **topmost thing on the stack**, it grows in place: `top`
  moves forward and nothing is copied. This is the common case when you build
  one thing at a time;
- otherwise a new buffer twice as large is bumped at the top and the contents
  are copied. The old buffer becomes dead space, and it is reclaimed when the
  enclosing scope resets.

Strings are immutable views, `(pointer, length)`. Concatenation and f-strings
write new bytes at the top. Appending to a string that ends exactly at `top`
extends it in place, so `s = s + x` in a loop is linear rather than quadratic.

## Returning values

A function allocates in its caller's region. When it returns a list, the buffer
it built is simply left where it is, and the caller's scope owns it from then on.
No copy, no move and no annotation are needed.

The downside is that any *scratch* values the function made also stay until the
caller's scope ends. Mark the function `@compact` and the compiler will slide the
result down over the scratch space before returning:

```python
@compact
fn labels(n: int) -> list[str]:
    var out: list[str] = []
    for i in 0..n:
        let tmp = f"<{i}>"          # scratch
        out.push(tmp.upper())       # result
    return out                      # only `out` and its strings survive
```

`@compact` costs one copy of the result, which is the same price as returning a
`std::vector` that has to be moved into an arena.

## Escapes from loops

If a loop body assigns a dynamic value to a variable declared *outside* the
loop, or changes one through `&mut`, a plain reset would destroy that value.
Such a variable is **carried** by the loop. Instead of a plain reset, the loop
compacts:

```python
var keep: list[str] = []
for frame in 0..1_000_000:
    let tmp = f"frame {frame}"     # garbage
    if frame % 1000 == 0:
        keep.push(tmp)             # keep is carried
```

At the top of each iteration the loop checks how much the region has grown since
the loop began. When the growth passes a threshold, the carried values are copied
to the exchange arena, the region is reset, and they are copied back. Everything
else the iterations allocated is gone. After each compaction the threshold becomes
twice the surviving size plus 256 KB, so a value that keeps growing is copied
O(log n) times. The total copying cost stays linear, and a loop that keeps little
runs in constant memory. A game or GUI frame loop therefore does not leak.

One case falls back to the old behaviour, where nothing is reset until the
enclosing scope ends: a carried variable that is also *moved* inside the body.
The loop can't relocate a value it may no longer own. If that matters, move the
work into a function marked `@compact`.

## Closures and threads

A closure is two words: a code pointer and a pointer to its **environment**,
the captured values laid out like a struct. The environment is written to the
data stack when the closure is created, so it follows the same rules as a list
buffer. It belongs to the scope that made it, it can be returned, `@compact`
relocates it with the result, and a loop that lets a closure escape carries
and compacts it like any other value. Captures are by value and can't be changed afterwards. Copying a
closure therefore copies only the two words, and the copies share one environment
that no one can modify.

A **task** (`spawn`) runs on its own OS thread with its own data stack. That is
a separate reserved mapping, committed lazily like the main one. The two never
share memory:

- `spawn` deep-copies the closure's environment into the task's stack, so the
  task holds no pointer into its parent's stack.
- `join` deep-copies the result into the joiner's stack at its current top, and
  then unmaps the task's stack.

Each thread bumps its own `top`, so allocation needs no locks or atomics. And
because no memory is shared, no data race is possible. The cost is the two
copies, which is proportional to the size of the captures and of the result. Pass
work in and send results out, as you would between processes.

## Why it is safe

Freeing by resetting a pointer is only safe if nothing can point into the
memory being freed. Silly guarantees that with three rules, all checked at
compile time:

1. **References are second class.** `&T` and `&mut T` exist only as function
   parameters. You can't store a reference in a variable, a struct field, a
   list or a return value. A reference therefore never outlives the call it
   was passed to, and the call always ends before its caller's scope does. This
   is why Silly needs no lifetime annotations: every lifetime is "this call".

2. **Values move.** Assigning or passing a non-`Copy` value (a list, a string, a
   struct containing either) moves it. Using the old name afterwards is an
   error, and so is moving something inside a loop that the next iteration would
   use again. `Copy` types (integers, floats, bools, chars, fixed arrays, `fn`
   values, and structs or tuples made only of these) copy freely. A closure
   moves its non-Copy captures in, so a captured list has exactly one owner.

3. **Views freeze what they view.** Iterating a list, matching on a value, or
   taking a string slice creates a *view* of the original. While a view is
   alive, the original can't be modified or moved, and the view can't be moved
   out on its own.

```python
for n in names:
    names.push(n)   # error: cannot modify 'names' while it is being iterated
```

Together these rules mean that every pointer into the data stack is either
owned by a variable in a live scope or borrowed for the length of a call. When
a scope ends, nothing that could still be used points into what it freed.
Bounds checks on indexing and checked `map[key]` lookups cover the rest: a bad
index or a missing key panics with the file and line instead of reading
garbage.

Debug builds (`--opt debug`) also fill reclaimed memory with `0xA5`. A
compiler bug that leaves a dangling pointer then shows up loudly, instead of
silently reading stale data. The test suite runs every program in both debug
and release modes. Every test and example program also runs clean under ASan
and UBSan. ASan can't see inside the data stack, which is one mapping as far as
it knows, so poisoning and the test suite carry that part.

## What it costs

The model is fast because freeing is free. It isn't free in every case:

- **Interleaved growth wastes space.** If a long-lived list grows while other
  long-lived values are being allocated above it, each doubling leaves the old
  buffer dead until the scope ends. In the worst case that's about as much
  again as the final buffer. The `wordfreq` benchmark shows this: 134 MiB
  against 97 MiB for C++.
- **No individual `free`.** Removing elements from a list or entries from a map
  doesn't give memory back until the owning scope ends. A long-running loop
  that keeps one ever-changing collection outside the loop holds the memory of
  its largest size, plus dead buffers from growth.
- **No shared ownership or cyclic graphs through pointers.** Build graphs and
  trees in a `list` and refer to nodes by index (see `examples/calc.silly` and
  `benchmarks/silly/trees.silly`). This is how fast C++ and Rust code does it
  too, and here it's the only option.

In exchange, allocation-heavy code is often several times faster than the
idiomatic `malloc`-based equivalent, and memory use is predictable from the
shape of the program. See `benchmarks/README.md` for measurements.
