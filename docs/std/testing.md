# testing

Unit tests, like Python's unittest.

```silly
import testing

fn test_add() -> Result[bool, str]:
    testing.eq(1 + 1, 2)?
    testing.check(len("ab") == 2, "len")?
    return testing.ok()

fn main():
    var s = testing.suite("math")
    s.run("test_add", test_add)
    s.skip("test_slow", "takes a minute")
    s.exit()                 # prints the report, exits 1 if anything failed
```

A test returns Ok to pass or Err(message) to fail; each assertion returns a
Result, so `?` stops the test at the first failed one. A panic stops the whole
program, not just the test.

The program's arguments pick what runs: -v lists each test by name, -q prints
only failures, and any other argument runs just the tests whose names contain
it (like unittest -k). Progress and the report go to stderr.

## Types

### `Suite`

A named group of tests (see suite()); run each with run(), then exit().

- `name: str`
- `verbosity: int` — 0 quiet, 1 dots, 2 names
- `pattern: str` — run only names containing this
- `ran: int`
- `skipped: int`
- `failures: list[(str, str)]` — (test name, message)
- `started: f64`

- `selected(self, name: &str) -> bool` — Whether a test with this name would run.
- `run(mut self, name: str, f: fn() -> Result[bool, str])`
- `skip(mut self, name: str, reason: str)`
- `passed(self) -> bool`
- `report(self, timed: bool) -> str` — The text printed at the end. With timed false, "Ran N tests" has no time, so the report is the same every run.
- `finish(self) -> int` — Prints the report to stderr and returns the exit code (0 or 1).
- `exit(self)` — finish, then exit with its code.

## Functions

### `repr[X](x: &X) -> str`

The way a value looks inside a list: strings in quotes, so "1" and 1 differ.

### `ok() -> Result[bool, str]`

Passes.

### `fail(msg: str) -> Result[bool, str]`

Always fails.

### `check(cond: bool, msg: str) -> Result[bool, str]`

Fails with msg unless cond holds.

### `is_true(cond: bool) -> Result[bool, str]`

Fails unless cond holds.

### `is_false(cond: bool) -> Result[bool, str]`

Fails if cond holds.

### `eq[X: Eq](a: X, b: X) -> Result[bool, str]`

Fails unless a == b, showing both.

### `ne[X: Eq](a: X, b: X) -> Result[bool, str]`

Fails if a == b.

### `eq_msg[X: Eq](a: X, b: X, note: str) -> Result[bool, str]`

eq with a note added to the failure message.

### `lt[X: Ord](a: X, b: X) -> Result[bool, str]`

Fails unless a < b.

### `le[X: Ord](a: X, b: X) -> Result[bool, str]`

Fails unless a <= b.

### `gt[X: Ord](a: X, b: X) -> Result[bool, str]`

Fails unless a > b.

### `ge[X: Ord](a: X, b: X) -> Result[bool, str]`

Fails unless a >= b.

### `near(a: f64, b: f64, tol: f64) -> Result[bool, str]`

Whether two floats agree to within tol.

### `contains[X: Eq](xs: &list[X], x: X) -> Result[bool, str]`

Fails unless x is in xs.

### `not_contains[X: Eq](xs: &list[X], x: X) -> Result[bool, str]`

Fails if x is in xs.

### `str_contains(s: &str, part: &str) -> Result[bool, str]`

Fails unless part occurs in s.

### `is_ok[X, E](r: &Result[X, E]) -> Result[bool, str]`

Fails unless r is Ok.

### `is_err[X, E](r: &Result[X, E]) -> Result[bool, str]`

Fails unless r is Err.

### `is_some[X](o: &Option[X]) -> Result[bool, str]`

Fails unless o is Some.

### `is_none[X](o: &Option[X]) -> Result[bool, str]`

Fails unless o is None.

### `suite(name: str) -> Suite`

A suite set up from the program's arguments (-v, -q, a name filter).

### `suite_with(name: str, args: &list[str]) -> Suite`

A suite set up from these arguments instead.
