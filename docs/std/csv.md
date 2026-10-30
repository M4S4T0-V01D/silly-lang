# csv

Reading and writing CSV, like Python's csv module.

```silly
import csv
fn main():
    let rows = csv.parse("name,qty\r\npen,\"1,5\"\r\n")
    print(rows)                                  # [["name", "qty"], ["pen", "1,5"]]
    for r in csv.parse_dicts("name,qty\npen,3\n"):
        print(r["name"], r["qty"])               # pen 3
    print(csv.format(&[["a", "b c"], ["x,y", "say \"hi\""]]))
    # a,b c
    # "x,y","say ""hi"""
```

Parsing follows Python's default (excel) dialect and is just as forgiving: a
quote inside an unquoted field is kept, text after a closing quote is
appended, and an unterminated quoted field runs to the end. Rows may end in
\r\n, \n or \r; a blank line is an empty row. Writing quotes a field only when
it has to (it holds the delimiter, a quote, \r or \n), doubling inner quotes.

## Types

### `Dialect`

How fields are separated and quoted (see excel()).

- `delimiter: char`
- `quote: char`
- `line_end: str`
- `quote_all: bool` — quote every field when writing

## Functions

### `excel() -> Dialect`

Comma-separated, \r\n line ends (Python's default).

### `tsv() -> Dialect`

Tab-separated.

### `unix() -> Dialect`

Comma-separated with \n line ends and every field quoted (Python's unix dialect).

### `parse(text: &str) -> list[list[str]]`

The rows of comma-separated text.

### `parse_with(text: &str, d: &Dialect) -> list[list[str]]`

The rows of text written in dialect d.

### `parse_dicts(text: &str) -> list[map[str, str]]`

Rows as maps keyed by the first row's names. A short row leaves the missing keys as ""; fields beyond the header are dropped. Empty rows are skipped.

### `parse_dicts_with(text: &str, d: &Dialect) -> list[map[str, str]]`

Like parse_dicts, in dialect d.

### `format_row(fields: &list[str], d: &Dialect) -> str`

One row with its line ending.

### `format(rows: &list[list[str]]) -> str`

rows as comma-separated text, quoting fields that need it.

### `format_with(rows: &list[list[str]], d: &Dialect) -> str`

rows as text in dialect d.

### `format_dicts(header: &list[str], rows: &list[map[str, str]]) -> str`

A header row, then each map's values in header order ("" when a key is missing).

### `format_dicts_with(header: &list[str], rows: &list[map[str, str]], d: &Dialect) -> str`

Like format_dicts, in dialect d.
