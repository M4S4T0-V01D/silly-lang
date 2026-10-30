# argparse

Command-line parsing, like Python's argparse.

```silly
import argparse
fn main():
    var p = argparse.Parser.new("wc", "Count lines in files.")
    p.flag("verbose", "v", "say what is happening")
    p.int_option("width", "w", 80, "column width")
    p.choice("mode", "", ["lines", "words"], "lines", "what to count")
    p.rest("files", "files to read")
    let a = p.parse_args()                  # -h prints help; errors exit with 2
    if a.flag("verbose"):
        print("width", a.int("width"), "mode", a.get("mode"), a.list("files"))
```

Long options are --name, --name=value or any unique prefix of the name; short
ones are -n, -nVALUE, -n VALUE, and short flags combine (-vq). "--" ends the
options. Values are looked up by the long name (positionals by their name).

## Types

### `Args`

The parsed command line: look options and positionals up by name.

- `values: map[str, list[str]]`
- `given: map[str, bool]`
- `help_wanted: bool`

- `flag(self, name: str) -> bool` — Whether a flag was given (at least once).
- `count(self, name: str) -> int` — How many times a flag or counted option was given.
- `get(self, name: str) -> str` — The value of an option or positional; "" when it has none.
- `int(self, name: str) -> int`
- `float(self, name: str) -> f64`
- `list(self, name: str) -> list[str]` — Every value: of a rest positional, or of an append option in order given.
- `has(self, name: str) -> bool` — Whether the argument was on the command line (not just defaulted).

### `Parser`

Describes the options and positionals a program takes (start with Parser.new).

- `prog: str`
- `about: str`
- `opts: list[_Opt]`
- `pos: list[_Pos]`

- `new(prog: str, about: str) -> Parser`
- `flag(mut self, name: str, short: str, help: str)` — A switch: --name or -s.
- `count(mut self, name: str, short: str, help: str)` — A switch that may repeat, like -vvv; read it with count().
- `option(mut self, name: str, short: str, default: str, help: str)` — An option taking a string. An empty default means none.
- `int_option(mut self, name: str, short: str, default: int, help: str)`
- `float_option(mut self, name: str, short: str, default: f64, help: str)`
- `required(mut self, name: str, short: str, help: str)` — A string option that must be given.
- `append(mut self, name: str, short: str, help: str)` — An option that may repeat, collecting every value; read it with list().
- `choice(mut self, name: str, short: str, choices: list[str], default: str, help: str)` — An option whose value must be one of choices.
- `positional(mut self, name: str, help: str)` — A positional argument that must be given.
- `optional(mut self, name: str, default: str, help: str)` — A positional that may be left out.
- `rest(mut self, name: str, help: str)` — Every remaining positional (zero or more); it must come last.
- `usage(self) -> str`
- `help(self) -> str`
- `parse(self, argv: &list[str]) -> Result[Args, str]` — Parses arguments (without the program name). Asking for help (-h, --help) gives Ok with help_wanted set and nothing else checked.
- `parse_args(self) -> Args` — Parses the program's own arguments. Prints help and exits with 0 on -h; prints usage and the error to stderr and exits with 2 on a bad command line.
