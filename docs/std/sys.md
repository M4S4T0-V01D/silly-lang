# sys

The running program: its arguments, standard streams, exit and platform.

```silly
import sys
fn main():
    let argv = sys.argv()
    if len(argv) < 2:
        sys.die("usage: tool FILE")
    sys.stderr("reading " + argv[1] + "\n")
```

## Constants

- `VERSION: str = "0.1.0"`
- `MAX_INT: int = 9223372036854775807`
- `MIN_INT: int = -9223372036854775807 - 1`
- `BYTEORDER: str = "little"`

## Functions

### `argv() -> list[str]`

The command line: argv()[0] is the program, the rest are its arguments.

### `platform() -> str`

"linux", "darwin", "freebsd", ... (the lowercased kernel name).

### `stdout(s: str)`

Writes to standard output without a newline.

### `stderr(s: str)`

Writes to standard error without a newline.

### `flush()`

Writes out anything buffered for stdout.

### `read_stdin() -> str`

Everything left on standard input.

### `stdin_lines() -> list[str]`

The remaining lines of standard input, without their line endings.

### `isatty(fd: int) -> bool`

Whether standard input/output/error (0, 1, 2) is a terminal.

### `exit(code: int)`

Ends the program with a status code.

### `die(msg: str)`

Prints a message to standard error and exits with status 1.
