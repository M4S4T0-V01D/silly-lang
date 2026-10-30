# re

Regular expressions, like Python's re.

```silly
import re
fn main():
    let date = re.compile("(?P<y>\\d{4})-(\\d\\d)-(\\d\\d)").unwrap()
    match date.search("due 2026-10-30!"):
        case Some(m): print(m.group(0), m.named("y"), m.group(2))   # 2026-10-30 2026 10
        case None: print("no date")
    print(re.sub("\\s+", " ", "a   b \t c"))                       # a b c
    print(re.find_all("[a-z]+", "one 2 three"))                     # ["one", "three"]
    print(re.split(",\\s*", "a, b,c"))                              # ["a", "b", "c"]
```

The syntax is Python's: . ^ $ * + ? {m,n} (lazy with a trailing ?), [...] sets,
\d \w \s \D \W \S \b \B \A \Z, (...) groups, (?:...), (?P<name>...) or (?<name>...),
\1 and (?P=name) backreferences, (?=...) (?!...) (?<=...) (?<!...) lookaround
(lookbehind must have a fixed width), and the flags (?i) (?m) (?s), also scoped
as (?i:...). Matching works on characters, positions are byte offsets.
The engine backtracks, so a pattern like (a*)*b can take exponential time.

## Constants

- `IGNORECASE: int = 1`
- `MULTILINE: int = 2`
- `DOTALL: int = 4`

## Types

### `Match`

The result of a successful match. Positions are byte offsets into the text.

- `spans: list[int]` — start and end of each group, -1 when it didn't take part
- `texts: list[str]`
- `names: map[str, int]`

- `group(self, i: int) -> str` — Group i's text; "" when the group didn't take part. Group 0 is the whole match.
- `get(self, i: int) -> Option[str]` — Group i's text, None when it didn't take part.
- `named(self, name: str) -> str` — A named group's text; "" when it didn't take part.
- `start(self, i: int) -> int`
- `end(self, i: int) -> int`
- `span(self) -> (int, int)`
- `groups(self) -> list[str]` — Groups 1 and up.
- `group_map(self) -> map[str, str]` — The named groups that took part, by name.
- `len(self) -> int`
- `expand(self, template: &str) -> str` — Expands \1, \g<1>, \g<name> and \\ in a replacement template.

### `Regex`

A compiled pattern.

- `pattern: str`
- `prog: list[_Op]`
- `sets: list[_Set]`
- `ngroups: int`
- `nslots: int`
- `names: map[str, int]`
- `anchored: bool`

- `group_count(self) -> int`
- `group_index(self, name: str) -> Option[int]`
- `exec(self, b: &list[u8], pc0: int, sp0: int, slots: &mut list[int], nonempty: bool) -> int` — Runs the program from pc at byte sp. Returns the end position, or -1. With `nonempty`, a match that ends where it started doesn't count.
- `make_match(self, s: &str, slots: &list[int]) -> Match`
- `search_at(self, s: &str, b: &list[u8], at: int, nonempty: bool) -> Option[Match]` — The first match starting at byte `at` or later; with `nonempty`, an empty match exactly at `at` is skipped.
- `search(self, s: &str) -> Option[Match]` — The first match anywhere in s.
- `search_from(self, s: &str, pos: int) -> Option[Match]` — The first match at or after byte offset pos.
- `match_start(self, s: &str) -> Option[Match]` — A match that starts at the beginning of s (Python's re.match).
- `fullmatch(self, s: &str) -> Option[Match]` — A match of the whole of s.
- `is_match(self, s: &str) -> bool`
- `find_iter(self, s: &str) -> list[Match]` — Every non-overlapping match, left to right.
- `find_all(self, s: &str) -> list[str]` — The text of every match.
- `sub_n(self, s: &str, repl: &str, count: int) -> str` — Replaces every match with the template (\1, \g<name>), at most `count` when count > 0.
- `sub(self, s: &str, repl: &str) -> str`
- `sub_fn(self, s: &str, f: fn(Match) -> str) -> str` — Replaces every match with what f returns for it.
- `split_n(self, s: &str, count: int) -> list[str]` — Splits around matches, at most `count` times when count > 0. Captured groups are included between the pieces, as in Python.
- `split(self, s: &str) -> list[str]`

## Functions

### `compile_flags(pattern: &str, flags: int) -> Result[Regex, str]`

Like compile, with IGNORECASE, MULTILINE or DOTALL or-ed together.

### `compile(pattern: &str) -> Result[Regex, str]`

A Regex for pattern, or what's wrong with it.

### `search(pattern: &str, s: &str) -> Option[Match]`

The first match of pattern anywhere in s.

### `match_start(pattern: &str, s: &str) -> Option[Match]`

A match of pattern at the start of s (Python's re.match).

### `fullmatch(pattern: &str, s: &str) -> Option[Match]`

A match of pattern covering all of s.

### `is_match(pattern: &str, s: &str) -> bool`

Whether pattern matches anywhere in s.

### `find_all(pattern: &str, s: &str) -> list[str]`

The text of every non-overlapping match in s.

### `find_iter(pattern: &str, s: &str) -> list[Match]`

Every non-overlapping match in s, as Match values.

### `sub(pattern: &str, repl: &str, s: &str) -> str`

s with every match replaced by repl (\1 or \g<name> insert groups).

### `split(pattern: &str, s: &str) -> list[str]`

The parts of s between matches.

### `escape(s: &str) -> str`

The text with every regex metacharacter backslash-escaped.
