# string

String constants and the helpers that str's built-in methods leave out.

```silly
import string
fn main():
    print(string.pad_left("7", 3, '0'), string.center("hi", 6, '*'))   # 007 **hi**
    print(string.capwords("hello   silly world"))                        # Hello Silly World
    print(string.partition("key=value=x", "="))                         # ("key", "=", "value=x")
    print(string.distance("kitten", "sitting"))                         # 3
```

## Constants

- `ASCII_LOWERCASE: str = "abcdefghijklmnopqrstuvwxyz"`
- `ASCII_UPPERCASE: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"`
- `ASCII_LETTERS: str = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"`
- `DIGITS: str = "0123456789"`
- `HEXDIGITS: str = "0123456789abcdefABCDEF"`
- `OCTDIGITS: str = "01234567"`
- `PUNCTUATION: str = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"`
- `WHITESPACE: str = " \t\n\r\u{b}\u{c}"`
- `PRINTABLE: str = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~ \t\n\r\u{b}\u{c}"`

## Functions

### `width(s: &str) -> int`

The number of characters (code points), where len(s) counts bytes.

### `repeat(s: &str, n: int) -> str`

s, n times over.

### `pad_left(s: &str, w: int, fill: char) -> str`

Pads on the left to `w` characters: pad_left("7", 3, '0') == "007".

### `pad_right(s: &str, w: int, fill: char) -> str`

s padded with fill on the right to w characters.

### `center(s: &str, w: int, fill: char) -> str`

Centers in `w` characters, placing an odd leftover exactly as Python does.

### `zfill(s: &str, w: int) -> str`

Zero-pads a number string, keeping its sign in front: zfill("-42", 5) == "-0042".

### `capitalize(s: &str) -> str`

The first character upper case and the rest lower case.

### `capwords(s: &str) -> str`

Every word capitalized, with runs of whitespace collapsed to one space.

### `title(s: &str) -> str`

Upper case after every non-letter, like Python's str.title().

### `swapcase(s: &str) -> str`

s with ASCII upper and lower case swapped.

### `rfind(s: &str, sub: &str) -> Option[int]`

The byte index of the last occurrence of `sub`.

### `find_from(s: &str, sub: &str, start: int) -> Option[int]`

The first occurrence of `sub` at or after byte index `start`.

### `find_all(s: &str, sub: &str) -> list[int]`

Every byte index where `sub` starts (non-overlapping).

### `partition(s: &str, sep: &str) -> (str, str, str)`

(before, sep, after) around the first `sep`; (s, "", "") if it isn't there.

### `rpartition(s: &str, sep: &str) -> (str, str, str)`

The same around the last `sep`; ("", "", s) if it isn't there.

### `split_whitespace(s: &str) -> list[str]`

Splits on runs of whitespace, dropping empty pieces.

### `splitn(s: &str, sep: &str, n: int) -> list[str]`

At most `n` splits, the rest left in the last piece.

### `remove_prefix(s: &str, prefix: &str) -> str`

s without prefix, if it starts with it.

### `remove_suffix(s: &str, suffix: &str) -> str`

s without suffix, if it ends with it.

### `strip_chars(s: &str, chars: &str) -> str`

Strips any of the characters in `chars` from both ends.

### `is_digits(s: &str) -> bool`

Whether s is non-empty and all ASCII digits.

### `is_alpha(s: &str) -> bool`

Whether s is non-empty and all ASCII letters.

### `is_alnum(s: &str) -> bool`

Whether s is non-empty and all ASCII letters or digits.

### `is_space(s: &str) -> bool`

Whether s is non-empty and all whitespace.

### `is_identifier(s: &str) -> bool`

A valid name: a letter or _ followed by letters, digits and _.

### `reverse(s: &str) -> str`

The characters in reverse order.

### `translate(s: &str, src: &str, dst: &str) -> str`

Replaces each character found in `src` with the one at the same place in `dst`; characters past the end of `dst` are deleted: translate("hello", "lo", "L") == "heLL".

### `substitute(template: &str, values: &map[str, str]) -> str`

Replaces {name} placeholders from a map; {{ and }} are literal braces. Unknown names are left as they are.

### `distance(a: &str, b: &str) -> int`

The Levenshtein edit distance, in characters.
