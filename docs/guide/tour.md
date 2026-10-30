# A tour of Silly

This tour walks through the language from the first line to threads. It
assumes you have programmed before, ideally in Python; Silly's syntax will look
familiar, and the differences are pointed out as they come. Every example with a
`main` is a complete program: save it as `example.silly`, run
`silly run example.silly`, and you get the output shown under it.

## Hello, world

```silly
fn main():
    print("Hello, world!")
```

```text
Hello, world!
```

A program starts at `main`. Blocks are opened by a line ending in `:` and set
by indentation, as in Python. `print` takes any number of values and separates
them with spaces.

## Values and variables

```silly
fn main():
    let name = "Ada"            # immutable
    var age = 36                # mutable
    age += 1
    let pi: f64 = 3.14159       # a type annotation
    let big = 1_000_000
    print(name, age, pi, big)
    print(7 / 2, 7 // 2, -7 // 2, -7 % 2, 2 ** 10)
    print(7.0 / 2.0, 3.9 as int, 65 as char, 'A' as u32)
```

```text
Ada 37 3.14159 1000000
3 3 -4 1 1024
3.5 3 A 65
```

`let` binds a name once, `var` makes a variable you can change. Types are
inferred; write them after a colon when you want to.

The number types are `int` (64-bit), `i8` to `i64`, `u8` to `u64`, and `f64`
and `f32`. Integers and floats never mix on their own: `as` converts. Integer
`/` truncates like C, while `//` and `%` floor like Python. Integer overflow
wraps around; it is never undefined.

Constants live at the top level. There are no mutable globals:

```silly
const MAX_USERS: int = 100

fn main():
    print(MAX_USERS * 2)
```

```text
200
```

## Functions

```silly
fn add(a: int, b: int) -> int:
    return a + b

fn greet(name: str):
    print(f"Hello, {name}!")

fn main():
    greet("world")
    print(add(2, 3))
```

```text
Hello, world!
5
```

Parameters and the return type are always written out; leave the return type
off when the function returns nothing. A function that returns a value must
`return` on every path, and the compiler checks that.

## Control flow

```silly
fn classify(n: int) -> str:
    if n < 0:
        return "negative"
    elif n == 0:
        return "zero"
    else:
        return "positive"

fn main():
    print(classify(-5), classify(0), classify(8))
    for i in 0..3:              # 0, 1, 2
        print("i =", i)
    var total = 0
    for i in 1..=100:           # 1 to 100 inclusive
        total += i
    print(total)
    var n = 27
    var steps = 0
    while n != 1:
        n = n // 2 if n % 2 == 0 else 3 * n + 1
        steps += 1
    print("steps:", steps)
    loop:
        steps -= 50
        if steps < 0:
            break
    print(steps)
```

```text
negative zero positive
i = 0
i = 1
i = 2
5050
steps: 111
-39
```

`for` walks ranges (`a..b` leaves `b` out, `a..=b` includes it), lists, the
characters of a string, and the keys of a map. `loop` runs until a `break`.
`a if cond else b` is the conditional expression.

## Strings

```silly
fn main():
    let lang = "Silly"
    let version = 1.5
    print(f"{lang} {version:.2f} | {lang:>8} | {lang:<8}|")
    let s = "  the quick brown fox  ".trim()
    print(s.upper(), len(s))
    let words = s.split(" ")
    print(words, words.len())
    print("-".join(words.clone()))
    print(s.replace("quick", "slow"), s.starts_with("the"), "fox" in s)
    print("42".parse_int().unwrap() + 1, s[4:9])
    for c in "hi!":
        print(c, c.is_alpha())
```

```text
Silly 1.50 |    Silly | Silly   |
THE QUICK BROWN FOX 19
["the", "quick", "brown", "fox"] 4
the-quick-brown-fox
the slow brown fox true true
43 quick
h true
i true
! false
```

Strings are immutable UTF-8. f-strings take Python's format specs. `len` and
slicing count bytes; `for c in s` gives characters. The `string` module adds
more, like `string.center` and `string.capitalize`.

## Lists, maps and tuples

```silly
fn main():
    var xs = [5, 3, 8, 1]
    xs.push(9)
    xs.sort()
    print(xs, xs[0], xs[-1], len(xs))
    print(xs[1:3], 8 in xs, sum(xs))
    print(xs.map(fn(x) => x * x), xs.filter(fn(x) => x % 2 == 1))

    var ages: map[str, int] = {"ada": 36, "alan": 41}
    ages["grace"] = 85
    print(ages["alan"], ages.get("bob"), len(ages))
    for name, age in ages.items():
        print(name, age)

    let point = (3, "three")
    let (n, word) = point
    print(point, n, word)

    let grid: [[int; 3]; 2] = [[0; 3]; 2]
    print(grid)
```

```text
[1, 3, 5, 8, 9] 1 9 5
[3, 5] true 26
[1, 9, 25, 64, 81] [1, 3, 5, 9]
41 None 3
ada 36
alan 41
grace 85
(3, "three") 3 three
[[0, 0, 0], [0, 0, 0]]
```

`list[T]` grows, `map[K, V]` keeps keys in insertion order, and `[T; N]` is a
fixed-size array. Indexing is always bounds-checked: a negative index counts
from the end, and going past either end stops the program with a clear message
instead of reading stray memory. `m[k]` stops the same way when the key is
missing, so use `m.get(k)` when it might be.

## Structs and methods

```silly
struct Rect:
    w: f64
    h: f64

    fn square(side: f64) -> Rect:       # no self: called as Rect.square(2.0)
        return Rect(side, side)

    fn area(self) -> f64:
        return self.w * self.h

    fn scale(mut self, k: f64):         # mut self changes the value in place
        self.w *= k
        self.h *= k

fn main():
    var r = Rect(3.0, 4.0)
    print(r.area())
    r.scale(2.0)
    print(r.w, r.h, r.area())
    print(Rect.square(2.0))
    print(r == Rect(6.0, 8.0))
```

```text
12.0
6.0 8.0 48.0
Rect(w=2.0, h=2.0)
true
```

A struct is built by calling its name with the fields in order. Methods are
written in the struct's body: `self` reads the value, `mut self` may change it,
and a method without `self` is a static function on the type. Structs print and
compare field by field without any extra code.

## Enums and pattern matching

```silly
enum Shape:
    Circle(f64)
    Rect(w: f64, h: f64)
    Dot

fn area(s: Shape) -> f64:
    match s:
        case Circle(r): return 3.14159 * r * r
        case Rect(w, h): return w * h
        case Dot: return 0.0

fn describe(n: int) -> str:
    match n:
        case 0: return "zero"
        case 1 | 2 | 3: return "a few"
        case 4..=9: return "several"
        case x if x < 0: return "negative"
        case _: return "many"

fn main():
    let shapes = [Shape.Circle(1.0), Shape.Rect(2.0, 3.0), Shape.Dot]
    for s in shapes:
        print(area(s))
    print(describe(2), describe(7), describe(-1), describe(50))
    let s = Shape.Rect(4.0, 1.0)
    if s is Rect(w, _) and w > 3.0:
        print("a wide rectangle")
```

```text
3.14159
6.0
0.0
a few several negative many
a wide rectangle
```

Each enum variant can carry its own data. `match` must cover every case, or the
compiler says which one is missing. `case` patterns can be literals,
alternatives with `|`, ranges, guards with `if`, nested variants and `_`. `x is
Pattern` tests one pattern and binds its names for the rest of the condition.

## Option, Result and `?`

Silly has no null and no exceptions. A value that might be missing is an
`Option[T]` (`Some(v)` or `None`), and an operation that might fail returns a
`Result[T, E]` (`Ok(v)` or `Err(e)`):

```silly
fn find(xs: &list[str], want: &str) -> Option[int]:
    for i, x in enumerate(xs):
        if x == want:
            return Some(i)
    return None

fn parse_pair(s: &str) -> Result[(int, int), str]:
    let parts = s.split(",")
    if len(parts) != 2:
        return Err(f"expected two numbers, got '{s}'")
    let a = parts[0].trim().parse_int().ok_or("bad first number")?
    let b = parts[1].trim().parse_int().ok_or("bad second number")?
    return Ok((a, b))

fn main():
    let names = ["ada", "alan", "grace"]
    print(find(&names, &"alan"), find(&names, &"bob"))
    match find(&names, &"grace"):
        case Some(i): print("found at", i)
        case None: print("missing")
    print(parse_pair(&"3, 4"))
    print(parse_pair(&"3; 4"))
    print(parse_pair(&"3, x"))
    print(parse_pair(&"1,2").unwrap_or((0, 0)))
```

```text
Some(1) None
found at 2
Ok((3, 4))
Err("expected two numbers, got '3; 4'")
Err("bad second number")
(1, 2)
```

`?` after an expression unwraps an `Ok` or `Some`, or returns the `Err` or
`None` from the current function straight away. `unwrap()` takes the value out
and stops the program if there is none; `unwrap_or`, `expect`, `map`, `ok_or`,
`is_some` and the rest are listed in the [reference](../spec.md#builtins).

## Ownership and borrowing

This is the one part of Silly that isn't Python. Strings, lists, maps and
anything that holds them have **one owner**. Assigning or passing such a value
**moves** it, and the old name can't be used any more:

```
let a = [1, 2, 3]
let b = a          # a moves into b
print(a)           # error: 'a' was moved at line 2 and can no longer be used
```

Numbers, `bool`, `char`, fixed arrays and structs made only of those are
**Copy**, and are copied instead. When you need a second, independent value,
call `.clone()`.

To let a function look at a value without taking it, pass a **reference**: `&x`
for reading, `&mut x` for changing:

```silly
fn total(xs: &list[int]) -> int:          # borrows xs to read it
    var t = 0
    for x in xs:
        t += x
    return t

fn add_tax(prices: &mut list[int], pct: int):   # borrows prices to change it
    for i in 0..len(prices):
        prices[i] = prices[i] * (100 + pct) // 100

fn consume(xs: list[int]) -> int:         # takes ownership
    return len(xs)

fn main():
    var prices = [100, 250, 40]
    print(total(&prices))
    add_tax(&mut prices, 10)
    print(prices)
    let copy = prices.clone()
    print(consume(prices), copy)
```

```text
390
[110, 275, 44]
3 [110, 275, 44]
```

References can **only be parameters**: you can't keep one in a variable, a
struct or a list, or return one. So every borrow ends when the call returns,
and no reference can outlive what it points to. That rule is why Silly needs no
lifetime annotations, and why it can manage memory without a heap or a garbage
collector. The [memory model](../memory-model.md) explains how values live on
a data stack that is freed scope by scope.

The compiler also refuses to let you change a list while looping over it, to
pass the same value as `&mut` twice in one call, or to use anything after it
has moved. Each of these is a compile error with the line it happened on.

## Closures

```silly
fn adder(n: int) -> fn(int) -> int:
    return fn(x) => x + n

fn apply_twice(f: fn(int) -> int, x: int) -> int:
    return f(f(x))

fn main():
    let add5 = adder(5)
    print(add5(1), apply_twice(add5, 0))
    let words = ["pear", "fig", "banana"]
    var sorted = words.clone()
    sorted.sort_by(fn(w) => len(w))
    print(sorted)
    let shout = fn(s: str) -> str:
        let loud = s.upper()
        return loud + "!"
    print(shout("hey"))
```

```text
6 10
["fig", "pear", "banana"]
HEY!
```

`fn(x) => expr` is a one-line closure; `fn(x) -> T:` with an indented block is
the long form. Closures capture outer variables **by value**, and a captured
variable can't be changed from inside. A function that needs to change state
takes it as a `&mut` parameter instead. Functions and closures have the same
type, `fn(A) -> R`, so either can be passed where the other is expected.

## Generics and traits

```silly
fn largest[T: Ord + Copy](xs: &list[T]) -> T:
    var best = xs[0]
    for x in xs:
        if x > best:
            best = x
    return best

trait Describe:
    fn describe(self) -> str
    fn shout(self) -> str:                    # a default method
        return self.describe().upper() + "!"

struct Dog:
    name: str

impl Describe for Dog:
    fn describe(self) -> str:
        return f"{self.name} the dog"

impl Describe for int:
    fn describe(self) -> str:
        return f"the number {self}"

fn introduce[T: Describe](x: T) -> str:
    return "Meet " + x.describe()

fn main():
    print(largest(&[3, 9, 2]), largest(&["pear", "apple"]))
    print(introduce(Dog("Rex")), introduce(42))
    print(Dog("Fido").shout())
```

```text
9 pear
Meet Rex the dog Meet the number 42
FIDO THE DOG!
```

Type parameters go in square brackets and are inferred at the call. A bound
like `T: Ord` says what the code needs from `T`; `Copy`, `Eq`, `Ord` and `Hash`
are built in. A `trait` is a set of methods, and `impl Trait for Type` provides
them, for your own types or for built-in ones like `int`. Generic code is
compiled separately for each type it's used with, so trait calls cost nothing at
run time.

## Modules

A file is a module. Put this in `geometry.silly`:

```
const UNIT: f64 = 1.0

fn circle_area(r: f64) -> f64:
    return 3.14159 * r * r
```

and use it from a file in the same directory:

```
import geometry
from geometry import circle_area

fn main():
    print(geometry.UNIT, circle_area(2.0))
```

The standard library is imported the same way:

```silly
import math
import random
from string import capitalize

fn main():
    print(math.sqrt(16.0), math.gcd(12, 18))
    random.seed(7)
    let roll = random.randint(1, 6)
    print(roll >= 1 and roll <= 6)
    print(capitalize(&"silly"))
```

```text
4.0 6
true
Silly
```

Names starting with `_` are private to their module. Bigger projects are
**packages**: see [Getting started](getting-started.md#packages).

## Threads

```silly
fn count_primes(lo: int, hi: int) -> int:
    var n = 0
    for x in lo..hi:
        if x < 2:
            continue
        var prime = true
        var d = 2
        while d * d <= x:
            if x % d == 0:
                prime = false
                break
            d += 1
        if prime:
            n += 1
    return n

fn main():
    var tasks: list[Task[int]] = []
    for i in 0..4:
        let lo = i * 25000
        tasks.push(spawn(fn() => count_primes(lo, lo + 25000)))
    print(sum(join_all(tasks)))
```

```text
9592
```

`spawn` runs a closure on a new operating-system thread and gives back a
`Task[T]`; `join` waits for its result. Threads **share nothing**: a task gets a
copy of what its closure captured and hands back a copy of its result. There
are no locks to take and no data races to have.

## Tests

Mark functions with `@test` and run them with `silly test`:

```
import testing

fn double(x: int) -> int:
    return x * 2

@test
fn doubles():
    assert double(2) == 4
    assert double(-3) == -6
```

```
$ silly test double.silly
test doubles ... ok

1 passed, 0 failed
```

For larger suites, the [`testing`](../std/testing.md) module adds named checks
with readable failure messages.

## When things go wrong

Mistakes that can be caught before the program runs are compile errors, with
the file, line and column:

```
fn main():
    let xs = [1, 2, 3]
    let ys = xs
    print(xs)
```

```
example.silly:4:11: error: 'xs' was moved at line 3 and can no longer be used
     4 |     print(xs)
       |           ^
  hint: use `xs.clone()` at line 3 if you need to keep it
```

Mistakes that can only show up while running, such as an index past the end, a
missing map key, division by zero or `unwrap()` on `None`, stop the program
with a **panic**: it prints where it happened and exits with status 101:

```
panic at example.silly:3:13: index 5 is out of range for length 1
```

 A
panic is always a clean stop, never undefined behaviour.

## Where next

- [Getting started](getting-started.md): installing, building, packages.
- [Building a GUI](gui.md): windows, drawing and widgets.
- [The standard library](../std/README.md): every module, function and type.
- [Language reference](../spec.md): the complete rules.
- [Memory model](../memory-model.md): how Silly manages memory without a heap.
