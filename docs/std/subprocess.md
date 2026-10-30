# subprocess

Running other programs and capturing what they print.

```silly
import subprocess
fn main():
    let r = subprocess.run("ls -1 /")
    if r.ok():
        for line in r.stdout.lines():
            print(line)
    print(subprocess.output(["echo", "it's quoted"]))
```

Commands given as a string run through /bin/sh; the list forms quote each
argument, so spaces and special characters reach the program unchanged.

## Types

### `Completed`

What a finished command left behind.

- `code: int` — exit status; 128 + n if killed by signal n, -1 if it couldn't start
- `stdout: str`
- `stderr: str`

- `ok(self) -> bool`
- `check(self) -> Result[str, str]` — Ok(stdout) when the command succeeded, otherwise Err with its stderr.

## Functions

### `quote(s: &str) -> str`

Quotes a string for the shell: quote("it's") == "'it'\\''s'".

### `join(argv: &list[str]) -> str`

Joins arguments into one shell command, quoting each.

### `run(cmd: str) -> Completed`

Runs a shell command, capturing stdout and stderr.

### `run_input(cmd: str, input: str) -> Completed`

Runs a shell command with `input` on its standard input.

### `run_args(argv: &list[str]) -> Completed`

Runs a program with arguments (no shell parsing), capturing its output.

### `output(argv: &list[str]) -> Result[str, str]`

The stdout of a program with arguments, or Err if it failed.

### `call(cmd: str) -> int`

Runs a shell command on this program's terminal (output is not captured).
