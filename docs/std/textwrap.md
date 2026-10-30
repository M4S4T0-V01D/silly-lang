# textwrap

Wrapping and indenting paragraphs of text.

```silly
import textwrap
fn main():
    for line in textwrap.wrap("The quick brown fox jumps over the lazy dog", 15):
        print(line)
    print(textwrap.indent("a\nb", "> "))
    print(textwrap.shorten("Hello  world, this is long", 15))    # Hello [...]
```

## Functions

### `wrap(text: &str, width: int) -> list[str]`

Breaks text into lines of at most `width` characters, at whitespace. Words longer than the width are split.

### `fill(text: &str, width: int) -> str`

wrap() joined with newlines.

### `dedent(text: &str) -> str`

Removes the indentation that every non-blank line shares.

### `indent(text: &str, prefix: &str) -> str`

Puts `prefix` in front of every non-blank line.

### `shorten(text: &str, width: int) -> str`

Collapses whitespace and cuts at a word boundary to fit `width`, ending in " [...]".
