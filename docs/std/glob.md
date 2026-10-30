# glob

Shell-style wildcards: matching names (Python's fnmatch) and finding files
(Python's glob).

```silly
import glob
fn main():
    print(glob.fnmatch("main.silly", "*.silly"))       # true
    print(glob.filter(&["a.c", "b.h", "c.c"], "*.c"))  # ["a.c", "c.c"]
    for p in glob.glob("src/**/*.silly"):
        print(p)
```

Patterns: * matches any run of characters, ? any one, [abc] or [a-z] one of a
set, [!abc] one not in it. To match a wildcard literally, put it in brackets
([*]). Matching is case-sensitive. In glob(), wildcards never match "/", a
name starting with "." is only found by a pattern part starting with ".", and
a part that is just ** matches any number of directories (zero or more).

## Functions

### `fnmatch(name: &str, pattern: &str) -> bool`

Whether the whole name matches the pattern.

### `filter(names: &list[str], pattern: &str) -> list[str]`

The names that match.

### `has_magic(s: &str) -> bool`

Whether a string has any wildcard characters.

### `escape(s: &str) -> str`

The pattern that matches s literally.

### `translate(pattern: &str) -> str`

The pattern as an equivalent regular expression, for the re module.

### `glob(pattern: &str) -> list[str]`

The paths matching a pattern, sorted. A relative pattern is searched from the current directory and gives relative paths. A pattern with no wildcards gives itself if the path exists.

### `rglob(pattern: &str) -> list[str]`

Like glob, but every part of the pattern may also match below any directory: rglob("*.c") finds .c files at any depth.
