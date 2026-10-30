# The Silly language

Silly reads like Python and compiles like C. Blocks are set by indentation,
declarations are typed the way Rust types them, and the compiler turns each
program into a single C file that gcc builds into a native binary. There is no
heap and no garbage collector. See [memory-model.md](memory-model.md) for how
that works.

```python
struct Point:
    x: f64
    y: f64

    fn norm(self) -> f64:
        return (self.x * self.x + self.y * self.y).sqrt()

fn main():
    let ps = [Point(3.0, 4.0), Point(1.0, 1.0)]
    for p in ps:
        print(f"{p.norm():.3f}")
```

## Lexical structure

- **Indentation** opens and closes blocks, as in Python. A line ending in `:`
  starts a block. Inside `()`, `[]` and `{}`, newlines are ignored.
- **Comments** start with `#` and run to the end of the line.
- **Integers**: `42`, `1_000_000`, `0xff`, `0b1010`, `0o17`. Out-of-range
  literals are compile errors.
- **Floats**: `3.14`, `1e-9`, `6.02e+23`.
- **Strings**: `"..."` with escapes `\n \t \r \0 \\ \" \' \u{1F600}`.
  f-strings are `f"x = {x}, {y:.3f}, {name:<10}"`.
- **Characters**: `'a'`, `'\n'` (a Unicode scalar value).
- **Keywords**: `fn let var const struct enum match case if elif else while
  for in loop break continue return and or not true false as import from pass
  mut extern is`.

## Types

| type | meaning |
|---|---|
| `i8 i16 i32 i64`, `u8 u16 u32 u64` | fixed-width integers. `int` = `i64`, `uint`/`usize` = `u64`, `byte` = `u8` |
| `f32 f64` | IEEE floats. `float` = `f64` |
| `bool`, `char` | `true`/`false`; a Unicode scalar value |
| `str` | an immutable UTF-8 string |
| `list[T]` | a growable sequence |
| `map[K, V]` | an insertion-ordered hash map. `K` must be hashable: integers, `bool`, `char`, `str`, or tuples, structs and enums of these |
| `[T; N]` | a fixed-size array (`T` must be Copy); `[0; 16]` repeats a value |
| `(A, B, ...)` | a tuple; `()` is the unit type |
| `Option[T]`, `Result[T, E]` | from the prelude: `Some(v)`/`None`, `Ok(v)`/`Err(e)` |
| `fn(A, B) -> R` | a function value: a top-level function or a closure |
| `Task[T]` | a running thread that will produce a `T` (see [Threads](#threads)) |
| `&T`, `&mut T` | a borrowed reference. **Only allowed as a parameter type** |

**Copy types** are integers, floats, `bool`, `char`, fixed arrays, `fn` values (closures included),
and tuples, structs and enums made only of Copy types. Everything else (`str`,
`list`, `map`, `Task`, and anything containing them) **moves** when assigned, passed
or returned.

Integer arithmetic wraps on overflow, exactly like two's complement. Division
or `%` by zero panics. Conversions are explicit with `as`: `x as int`,
`3.9 as int` (truncates), `65 as char`, `c as u32`. Integers and floats never
mix implicitly.

## Declarations

```python
const LIMIT: int = 100          # compile-time constant; there are no mutable globals

fn add(a: int, b: int) -> int:  # the return type is omitted for ()
    return a + b

fn first[T](xs: &list[T]) -> Option[T]: ...   # generic; T inferred at the call

struct Pair[A, B]:              # generic struct
    a: A
    b: B

    fn swapped(self) -> Pair[B, A]:   # method: self by value (a view for non-Copy types)
        return Pair(self.b, self.a)

    fn bump(mut self):                # method that mutates its receiver in place
        ...

enum Shape:
    Circle(f64)
    Rect(w: f64, h: f64)            # named payload fields
    Empty

extern fn hypot(x: f64, y: f64) -> f64   # a C function, linked directly

import math                     # math.sqrt(...), math.PI
from math import gcd, clamp
```

Structs are built by calling the type name: `Pair(1, "one")`. Enum variants are
built qualified: `Shape.Rect(2.0, 3.0)`. The prelude's `Some`, `None`, `Ok` and
`Err` need no qualifier.

### Decorators

| decorator | effect |
|---|---|
| `@compact` | move the result down over the function's scratch allocations before returning |
| `@inline`, `@cold` | hints passed through to the C compiler |
| `@test` | a unit test, run by `silly test file.silly` |
| `@extern_name("c_name")` | link an `extern fn` to a C symbol with a different name |
| `@consuming` | a method that takes `self` by move (e.g. `Option.unwrap`) |

## Variables and statements

```python
let x = 5              # immutable binding
var y: int = 0         # mutable binding, optional type
y += x                 # += -= *= /= //= %= &= |= ^= <<= >>=
(a, b) = (b, a)        # tuple assignment
let (q, r) = (7 // 2, 7 % 2)

if c: ... elif d: ... else: ...
while cond: ...
loop: ...              # infinite; leave with break
for i in 0..10: ...    # half-open range; 0..=10 is inclusive
for x in xs: ...       # a list, array, str (chars) or map (keys)
for k, v in m.items(): ...
for i, x in enumerate(xs): ...
break / continue / return / pass
assert cond, "message"
```

A function whose return type isn't `()` must return on every path; the compiler
checks this.

## Expressions

- Arithmetic: `+ - * / // % **`. On integers `/` truncates toward zero as in
  C, while `//` and `%` floor as in Python (`-7 // 2 == -4`, `-7 % 2 == 1`). On
  floats `/` is true division.
- Bitwise: `& | ^ ~ << >>`. Comparison: `== != < <= > >=`, which also work on
  strings, lists, tuples, structs and enums (structurally). Logic:
  `and or not`. Membership: `x in xs`, `k in m`, `"ab" in s`.
- Conditional: `a if cond else b`.
- Indexing `xs[i]` is bounds-checked; a negative index counts from the end, as
  in Python (`xs[-1]`).
  `m[k]` panics if the key is missing. Slices `xs[a:b]`, `s[a:]` and `s[:b]`
  work on lists and strings.
- `x is Pattern` tests a pattern and binds its names in the `if`/`and` that
  follows: `if o is Some(v) and v > 3:`.
- `expr?` propagates an `Err` or `None` out of a function that returns
  `Result` or `Option`.
- List, map and tuple literals: `[1, 2]`, `{"a": 1}`, `(1, "x")`. An empty
  `[]` or `{}` needs a type from its context.

## Pattern matching

```python
match shape:
    case Circle(r): return 3.14159 * r * r
    case Rect(w, h): return w * h
    case Empty: return 0.0

match n:
    case 0: ...
    case 1 | 2 | 3: ...          # alternatives
    case 4..=9: ...              # ranges
    case x if x < 0: ...         # guards
    case _: ...                  # wildcard
```

Matches must be exhaustive. Patterns inside `case` are unqualified (`Circle`,
not `Shape.Circle`). Tuples, literals, string literals and nested patterns all
work.

## Closures

`fn(params) => expr` is a one-line anonymous function. `fn(params) -> R:`
followed by an indented block is the long form. Parameter and return types can
be left out wherever the expected `fn` type gives them; otherwise the compiler
asks for an annotation.

```
fn adder(n: int) -> fn(int) -> int:
    return fn(x) => x + n           # captures n

let name = "silly"
let greet = fn(who: str) -> str:
    return f"{name} says hi to {who}"

print([3, 1, 2].map(fn(x) => x * 10))       # [30, 10, 20]
```

A closure **captures by value**. The first use of an outer variable creates the
capture: Copy values are copied in, and anything else is moved in, so the
enclosing function can't use it afterwards (use `.clone()` to keep a copy).
Inside the closure a capture is read-only. Modifying it is an error, and so is
moving a non-Copy capture out, since copies of one closure share one
environment. A `&T` or `&mut T` parameter can't be captured, because it is only
borrowed.

Closures and top-level functions have the same type, `fn(A) -> R`. They are
Copy, compare with `==` by identity, and can be stored in lists and structs and
returned. The environment lives on the data stack like any other value. It
escapes and is compacted by the same rules (see the memory model).

List methods that take a closure: `map filter any all count_by position each
fold sort_by` (`sort_by` is stable and takes a key function).

## Traits

```
trait Show:
    fn show(self) -> str
    fn shout(self) -> str:                  # a default method
        return self.show().upper() + "!"

trait Shape(Show):                          # a supertrait: every Shape is a Show
    fn area(self) -> f64
    fn new_unit() -> Self                   # no self: a static method

impl Show for Circle:
    fn show(self) -> str:
        return f"circle r={self.r}"

impl Show for int:                          # primitives can implement traits
    fn show(self) -> str:
        return f"#{self}"

fn show_all[T: Show](xs: &list[T]) -> str:  # a bound; join several with +
    ...
```

- **Implementations.** An `impl` must define every method without a default,
  with the trait's exact signature, and nothing else. Implementing a trait
  requires an impl of each supertrait. Methods take `self` (a view) or
  `mut self`. `Self` names the implementing type.
- **Generic types.** `impl Show for Pair:` covers every `Pair[T]`.
- **Calls.** `x.show()` calls a trait method. `Show.show(x)` names the trait
  explicitly; that's needed when two traits give a type methods of the same name.
  In a generic function, `T.new_unit()` calls a static method.
- **Built-in traits.** `Copy`, `Eq`, `Ord` and `Hash` are satisfied
  automatically by the types that support them (`[T: Ord + Copy]`).
- **Resolution.** Traits are bounds, not types. There is no `dyn Show`; every
  generic call is monomorphised, so trait calls are direct calls.

Methods that belong to one type and no trait are written in the type's own body:

```
struct Wrap:
    v: int
    fn make(v: int) -> Wrap:                # static: Wrap.make(3)
        return Wrap(v)
    fn doubled(self) -> int:
        return self.v * 2
```

## Threads

```
var tasks: list[Task[int]] = []
for i in 0..4:
    let lo = i * 25000
    tasks.push(spawn(fn() => count_primes(lo, lo + 25000)))
print(sum(join_all(tasks)))
```

- `spawn(f) -> Task[T]` runs a closure of no arguments on a new OS thread.
- `t.join() -> T` waits for it and returns its result.
- `join_all(tasks) -> list[T]` joins a list of tasks in order.
- `cpu_count()` is the number of CPUs.

**Nothing is shared.** Each task has its own data stack. Spawning deep-copies
the closure's captures into the new stack. Joining deep-copies the result back
into the joiner's stack and releases the task's stacks. So there are no locks
and no data races, and the ownership rules need no extra checks for threads.
Captures follow the closure rules, which is why a borrowed `&T` can't be sent
to a task.

A `Task` is a unique handle. It can be moved, stored and returned, but not
copied, cloned or printed. `join` consumes it, so a task is joined at most once.
The program ends when `main` returns, even if tasks are still running. Join a
task to wait for it.

Each task reserves `SILLY_TASK_STACK_MB` of address space (default 4096, capped
at `SILLY_STACK_MB`). The memory is committed lazily, like the main stack. A panic
in any task ends the whole program with status 101.

## Packages and modules

A file is a module. `import util` loads `util.silly` from the main file's
directory, or from the standard library (`import math`); `import a.b` loads
`a/b.silly`. Names in a module are used qualified (`util.f()`), and
`from util import f, g` imports names directly.

A **package** is a directory with a `silly.toml` and a `src/` folder:

```toml
[package]
name = "shapes"
version = "0.1.0"
entry = "src/main.silly"       # optional; this is the default

[dependencies]
vec2 = { path = "../vec2" }
color = { git = "https://example.com/color.git", rev = "v1.2" }
```

`import vec2` loads the dependency's `src/lib.silly`. `import vec2.ops` loads its
`src/ops.silly`, which you then use as `ops.f()`. A package reaches its own
modules through its own name. Dependencies are resolved transitively into one
flat set; if two packages ask for the same name from different sources,
resolution fails. Git dependencies are checked out into `.silly/deps/<name>`, and
`silly.lock` records the exact commit of each one, so every build sees the same
code. Package names are lowercase identifiers. `std`, `main` and `prelude` are
reserved.

### The standard library

`import name` looks in packages and the main file's directory first, then here;
`import std.name` always means the standard library's. Each module is documented in [docs/std](std/README.md), which is generated from the modules'
comments by `tools/stddoc.py`.

| Area | Modules |
|---|---|
| Text | `string`, `re`, `textwrap`, `difflib`, `json`, `csv`, `html`, `base64`, `url` |
| Numbers | `math`, `random`, `statistics`, `bisect`, `heapq` |
| Data | `collections`, `itertools`, `binary`, `hashlib`, `uuid` |
| Time | `time`, `datetime` |
| System | `sys`, `os`, `path`, `glob`, `shutil`, `tempfile`, `subprocess`, `argparse`, `logging` |
| Network | `socket`, `http` |
| Graphics | `gfx` (windows, drawing, input), `ui` (widgets on top of gfx) |
| Testing | `testing` |

### Native code

A module can carry C of its own. `extern "file.c"` pastes that file (looked up
next to the module, included once however many modules name it) into the
program's C, and `link "-lfoo"` adds linker flags. Its functions are then
declared with `extern fn`:

```silly
extern "fast.c"
extern fn fast_sum(n: int) -> int
```

`int` is `int64_t`, `f64` is `double` and `bool` is `bool`; a `str` is
`sl_str`, `{const uint8_t *p; int64_t n;}`, which isn't NUL-terminated
(`sl_cstr(s)` makes a C string). Memory for a returned string comes from
`sl_alloc(n)`. The standard library's `*.c` files are examples.

## Memory and ownership rules

The full model is in [memory-model.md](memory-model.md). In short:

- `&x` and `&mut x` are written at the call site and only there:
  `total(&xs)`, `bump(&mut xs)`. A reference never outlives the call.
- A moved variable can't be used again. Moving something inside a loop that
  the next iteration would need is an error.
- While a value is being iterated or matched on, it can't be modified or moved.
- The same variable can't be passed as `&mut` and also borrowed or moved in one
  call.

## Builtins

**Functions:** `print(...)`, `eprint(...)`, `len(x)`, `str(x)`, `abs`, `min`,
`max`, `sum(xs)`, `range`, `enumerate`, `panic(msg)`, `exit(code)`,
`input() -> Option[str]`, `read_file(path) -> Result[str, str]`,
`write_file(path, s) -> bool`, `args() -> list[str]`,
`clock() -> f64` (seconds), `take(&mut x)` (move out and leave a default),
`swap(&mut a, &mut b)`, `ord(c)`, `chr(i)`.
**Threads:** `spawn(f) -> Task[T]`, `t.join()`, `join_all(tasks)`, `cpu_count()`.

**`list[T]`:** `push pop insert remove swap reverse clear sort extend truncate
len is_empty contains index_of clone get last first`.
Taking a closure: `map filter any all count_by position each fold sort_by`.

**`map[K, V]`:** `m[k]`, `m[k] = v`, `get(k) -> Option[V]`, `get_or(k, d)`,
`contains`, `insert(k, v) -> Option[V]` (the old value), `remove(k) ->
Option[V]`, `clear len is_empty keys values items clone`. Iteration follows
insertion order. Mutating a map while iterating it is a compile error.

**`str`:** `len is_empty contains starts_with ends_with find split trim
trim_start trim_end upper lower replace join chars bytes parse_int parse_float
lines count clone`. `len(s)` counts bytes.

**`char`:** `is_digit is_alpha is_alnum is_space is_upper is_lower upper lower`.

**Floats:** `sqrt floor ceil abs round trunc is_nan`. **Integers:** `abs min max`.

**`Option` / `Result`:** `is_some is_none unwrap expect unwrap_or map ok_or`,
`is_ok is_err`, and `?`.

**`math` module:** `PI TAU E`, `sqrt cbrt sin cos tan asin acos atan atan2 exp
log log2 log10 pow hypot floor ceil fabs`, `inf gcd clamp`.

## Panics

Out-of-bounds indexing, a missing map key, division by zero, `unwrap()` on
`None`/`Err`, a failed `assert`, data stack overflow and an explicit `panic(...)`
all print `panic at file:line:col: message` and exit with status 101. A panic is
never undefined behaviour.

## Tooling

```
python3 -m silly run   file.silly [args]   # build (debug) and run
python3 -m silly build file.silly -o out --opt {debug,release,fast}
python3 -m silly check file.silly          # type-check only
python3 -m silly emit-c file.silly         # print the generated C
python3 -m silly test  file.silly          # run @test functions

python3 -m silly new   path [--lib]        # start a package (src/main.silly or src/lib.silly)
python3 -m silly add   name --path P       # add a dependency; or --git URL [--rev R]
python3 -m silly remove name
python3 -m silly fetch                     # check out git dependencies, write silly.lock
python3 -m silly update                    # re-resolve git dependencies to the newest commit of their rev
```

`debug` is `-O0 -g` with poisoning of reclaimed memory, `release` is `-O2`, and
`fast` is `-O3 -march=native`. All builds keep bounds checks. Inside a package, `run`, `build`, `check`
and `test` default to the package's entry point when no file is given.
