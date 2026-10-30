# difflib

Comparing sequences of lines (or characters): unified diffs, similarity
ratios and close matches, like Python's difflib.

```silly
import difflib
fn main():
    let a = "one\ntwo\nthree".split("\n")
    let b = "one\n2\nthree\nfour".split("\n")
    for line in difflib.unified_diff(&a, &b, &"old.txt", &"new.txt", 3):
        print(line)
    print(difflib.ratio(&"kitten", &"sitting"))                    # 0.6153846153846154
    print(difflib.get_close_matches(&"appel", &["ape", "apple", "peach"], 3, 0.6))
    # ["apple", "ape"]
```

This is Python's SequenceMatcher (longest matching block first, then the
pieces either side) without its junk heuristics, so the results are Python's
for inputs under 200 items, and still good diffs above that.

## Types

### `Match`

A run of size equal items at a[a] and b[b].

- `a: int` — start in the first sequence
- `b: int` — start in the second
- `size: int`

### `Opcode`

One step turning a[i1:i2] into b[j1:j2]: "equal", "replace", "delete" or "insert".

- `tag: str`
- `i1: int`
- `i2: int`
- `j1: int`
- `j2: int`

- `str(self) -> str`

### `Matcher`

Compares two lists of strings, like Python's SequenceMatcher.

- `a: list[str]`
- `b: list[str]`
- `b2j: map[str, list[int]]` — where each item of b appears

- `longest_match(self, alo: int, ahi: int, blo: int, bhi: int) -> Match` — The longest block a[i:i+k] == b[j:j+k] inside the given ranges, leftmost in a and then in b on ties.
- `matching_blocks(self) -> list[Match]` — Every maximal matching block in order, ending with Match(len(a), len(b), 0).
- `opcodes(self) -> list[Opcode]` — The steps that turn a into b.
- `grouped_opcodes(self, n: int) -> list[list[Opcode]]` — The opcodes split into hunks, each with up to n equal items of context.
- `ratio(self) -> f64` — 2 * matches / total length, from 0.0 (nothing alike) to 1.0 (the same).
- `quick_ratio(self) -> f64` — An upper bound on ratio(), from counting shared items; cheaper.
- `real_quick_ratio(self) -> f64` — An upper bound on ratio() from the lengths alone; very cheap.

## Functions

### `matcher(a: &list[str], b: &list[str]) -> Matcher`

A matcher comparing two lists (usually lines).

### `char_matcher(a: &str, b: &str) -> Matcher`

A matcher comparing two strings character by character.

### `ratio(a: &str, b: &str) -> f64`

How alike two strings are, from 0.0 to 1.0.

### `unified_diff(a: &list[str], b: &list[str], from_file: &str, to_file: &str, n: int) -> list[str]`

The lines of a unified diff (as `diff -u` prints, without line endings), with n lines of context. Empty if the lists are equal.

### `diff_text(a: &str, b: &str, from_file: &str, to_file: &str) -> str`

The unified diff of two texts, as one string ("" if they're the same).

### `get_close_matches(word: &str, possibilities: &list[str], n: int, cutoff: f64) -> list[str]`

Up to n of the possibilities at least cutoff alike to word, best first.
