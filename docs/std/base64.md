# base64

Base64, Base32 and hex encodings of byte strings, like Python's base64 and binascii.

```silly
import base64
fn main():
    print(base64.encode("hello"))                    # aGVsbG8=
    match base64.decode("aGVsbG8="):
        case Ok(s): print(s)                         # hello
        case Err(e): print(e)
    print(base64.urlsafe_encode("\u{fb}\u{ff}"))     # w7vDvw==
    print(base64.hex_encode("hi"))                   # 6869
```

Decoding ignores whitespace and returns Err for anything else that doesn't fit.

## Functions

### `encode(s: &str) -> str`

Standard Base64 (RFC 4648) with = padding.

### `decode(s: &str) -> Result[str, str]`

Reverses encode; an error for text that isn't valid base64.

### `urlsafe_encode(s: &str) -> str`

The URL- and filename-safe alphabet, - and _ in place of + and /.

### `urlsafe_decode(s: &str) -> Result[str, str]`

Reverses urlsafe_encode.

### `urlsafe_encode_nopad(s: &str) -> str`

URL-safe without padding, as used in JWTs.

### `b32_encode(s: &str) -> str`

Base32 (RFC 4648) with = padding.

### `b32_decode(s: &str) -> Result[str, str]`

Reverses b32_encode.

### `hex_encode(s: &str) -> str`

Each byte as two lowercase hex digits.

### `hex_decode(s: &str) -> Result[str, str]`

Reverses hex_encode (either case); an error for odd lengths or non-hex digits.
