# sillyc: the self-hosted Silly compiler

`sillyc.silly` is a Silly compiler written in Silly. It compiles **Silly Core**, the
subset of Silly that it is itself written in, to C, and it compiles its own source
to the same C on every stage:

```sh
selfhost/bootstrap.sh            # stage 1 → stage 2 → stage 3, checks the fixpoint
selfhost/build/sillyc prog.silly prog.c
gcc -O2 -fwrapv -I selfhost prog.c -o prog
```

| file           | what it is |
|----------------|------------|
| `sillyc.silly` | the compiler, about 2,600 lines in one file (Silly Core has no modules) |
| `sillyc_rt.h`  | the C runtime that generated programs include: the data stack, strings, lists, panics, I/O |
| `bootstrap.sh` | builds the three stages and compares stage 2's C with stage 3's |

`tests/selfhost_test.py` (part of `tests/run_tests.py`) runs the bootstrap. It then
compiles every program in `tests/run` with stage 2. Programs inside Silly Core must
print exactly what the reference compiler's build prints, panic messages and source
locations included. `tests/run/core_*.silly` are written to stay inside Core.

## Silly Core

Included:

- **Items:** `fn`, `struct`, `enum` (unit and payload variants), `const`.
- **Types:** `int`, `u8`, `bool`, `char`, `str`, `list[T]`, `Option[T]` and
  `Result[T, E]`, nested in any combination.
- **Parameters:** by value, `&T` and `&mut T`.
- **Statements:** `let`, `var`, assignment and every compound assignment, `if`/`elif`/`else`,
  `while`, `loop`, `for` over ranges (`a..b`, `a..=b`, `range(n)`, `range(a, b)`), lists
  and strings, `break`, `continue`, `return`, `pass` and `assert`.
- **`match`:** wildcards, literals, ranges, `|` alternatives, constants, nested variant
  patterns, bindings and `if` guards.
- **Expressions:** every operator, `x if c else y`, `as` casts, slicing, and `?` on Option
  and Result.
- **Library:** the list, str, Option and Result methods (except the closure-taking ones),
  `print`, `eprint`, `str`, `len`, `ord`, `chr`, `input`, `read_file`, `write_file`,
  `args`, `exit` and `panic`.
- **`main`:** may return nothing, or an `int` exit status.

Left out: generics, closures and `fn` types, traits and `impl`, threads, floats,
tuples, maps and sets, modules and `use`, f-strings, decorators and `@test`, and
printing whole lists. Programs that use them are rejected with a "… is not part of
Silly Core" error at the first such use.

## How it works

One pass and no AST. The lexer produces tokens with Python-style `INDENT`/`DEDENT`.
A declaration pass records every struct, enum, const and function signature. Then
each function body is compiled directly from its tokens.

`expr(c, want)` returns a `Val`: its C code, Silly type, whether it is a place, and
whether that place is mutable. `want` is the type the context expects. It lets
`None`, `[]` and integer literals pick up their type, as in the reference compiler.

- **Evaluation order.** C leaves argument order unspecified, but Silly runs left to
  right. A counter, `c.fx`, records every generated call or mutation. When a later
  operand has effects, the earlier operands are pinned into temporaries.
- **Types in C.** Each struct and enum gets a C struct; enums use a tag plus a union
  of payloads. Every list type is an `sl_list` (pointer, length, capacity) with typed
  `push_`/`at_`/`pop_` helpers. Helpers such as `clone_`, `sort_` and `idx_` are
  generated on first use.
- **Memory.** It follows the reference compiler's model: one data stack, with no heap.
  A function whose result holds no storage, and that has no `&mut` parameter that
  holds storage, saves the stack top on entry and restores it on every return. So
  everything it pushed is freed at once.
- **Checking.** sillyc reports syntax and type errors with the reference compiler's
  `file:line:col: error:` format. It does not repeat the full ownership and borrow
  checks. Run `silly check` for those; sillyc assumes a program it is given passes
  them.

## Numbers

On its own 2,600-line source, a stage 2 sillyc writes 4,500 lines of C in about
14 ms, at 43 MB peak RSS. The Python reference front end takes about 330 ms to do
the same.

The memory figure is high because sillyc resets the data stack only at function
boundaries, never inside a loop body. The reference compiler also resets per loop
iteration.

## Known gaps

- Loop bodies don't reset the data stack, as above. This affects memory use only.
- `None == x`, with no other type information, can't infer the Option's type.
  Write `x == None` or `x.is_none()`.
- Diagnostics are a subset: mostly syntax, types and mutability.
