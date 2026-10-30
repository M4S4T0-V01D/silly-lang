# Getting started

## Install

Silly needs **Python 3.11 or newer** and **gcc**. Git is only needed for git
dependencies. Clone the repository and put its `bin/` directory on your `PATH`:

```sh
git clone https://github.com/M4S4T0-V01D/silly-lang.git
cd silly-lang
export PATH="$PWD/bin:$PATH"      # add this line to ~/.bashrc or ~/.zshrc to keep it
silly --version
```

```
silly 0.1.0
```

There is nothing to build: the compiler is a Python package, and `bin/silly`
runs it. Without the launcher, `python3 -m silly ...` from the repository works
too.

## Your first program

Save this as `hello.silly`:

```silly
fn main():
    let name = "world"
    for i in 1..=3:
        print(f"{i}: hello, {name}!")
```

```text
1: hello, world!
2: hello, world!
3: hello, world!
```

Run it:

```sh
silly run hello.silly
```

`silly run` compiles the program to C, builds it with gcc and runs it, passing
along any extra arguments (read them with `sys.argv()`). The program is checked
completely before anything runs, so a type or ownership mistake is reported
with its line and a hint, not met halfway through a run.

## The commands

| command | what it does |
|---|---|
| `silly run file.silly [args]` | build a debug binary and run it |
| `silly build file.silly -o out --opt release` | build a native executable |
| `silly check file.silly` | type-check and ownership-check only; fast |
| `silly test file.silly` | run the `@test` functions in a file |
| `silly emit-c file.silly` | print the generated C |
| `silly new name [--lib]` | start a package |
| `silly add name --path P` / `--git URL [--rev R]` | add a dependency |
| `silly remove name` | remove a dependency |
| `silly fetch` | check out git dependencies and write `silly.lock` |
| `silly update` | move git dependencies to the newest commit of their `rev` |

`--opt` picks the build mode:

- **`debug`** (the default): `-O0 -g`. Freed memory is filled with garbage, so a
  bug in the compiler's memory management shows up straight away.
- **`release`**: `-O2`.
- **`fast`**: `-O3 -march=native`. The binary is tuned for this machine's CPU.

Every mode keeps bounds checks and other safety checks on.

## Tests

Any function marked `@test` is a test. `silly test` runs each one and reports
it:

```
fn double(x: int) -> int:
    return x * 2

@test
fn doubles():
    assert double(2) == 4
```

```
$ silly test double.silly
test doubles ... ok

1 passed, 0 failed
```

A failed `assert` (or any panic) fails that test, and the others still run.

## Packages

For anything bigger than one file, make a package:

```sh
silly new hello_app
cd hello_app
silly run
```

```
hello from hello_app
```

`silly new` writes this layout:

```
hello_app/
  silly.toml        # name, version, dependencies
  src/main.silly    # the entry point
  tests/
```

Inside a package, `run`, `build`, `check` and `test` use `src/main.silly` when
no file is given. Other files in `src/` are modules: `src/shapes.silly` is
imported with `import hello_app.shapes`.

### Libraries and dependencies

A library package has `src/lib.silly` in place of `main.silly`:

```sh
cd ..
silly new --lib geometry
```

Give it a function, in `geometry/src/lib.silly`:

```
fn circle_area(r: f64) -> f64:
    return 3.14159 * r * r
```

then add it to the program and use it:

```sh
cd hello_app
silly add geometry --path ../geometry
```

```
import geometry

fn main():
    print(geometry.circle_area(2.0))
```

```
$ silly run
12.56636
```

`silly.toml` now lists the dependency:

```toml
[package]
name = "hello_app"
version = "0.1.0"

[dependencies]
geometry = { path = "../geometry" }
```

A dependency can also come from git:

```sh
silly add color --git https://example.com/color.git --rev v1.2
silly fetch
```

Git dependencies are checked out into `.silly/deps/`, and `silly.lock` records
the exact commit of each one. Commit the lock file, and everyone who builds the
project gets the same code. `silly update` moves them forward when you want it
to.

## Editor setup

Silly's syntax is close enough to Python that Python highlighting works well in
any editor. Use 4-space indentation; tabs are an error.

## Next

- [A tour of Silly](tour.md): the whole language, one example at a time.
- [Building a GUI](gui.md): windows, drawing and widgets.
- [The standard library](../std/README.md).
