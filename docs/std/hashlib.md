# hashlib

Message digests and checksums, like Python's hashlib, hmac and zlib.crc32.

```silly
import hashlib
fn main():
    print(hashlib.sha256("abc"))         # ba7816bf8f01cfea...
    print(hashlib.md5(""))               # d41d8cd98f00b204e9800998ecf8427e
    print(hashlib.hmac_sha256("key", "message"))
    print(hashlib.crc32("hello"))        # 907060870
```

md5, sha1, sha256 and sha512 return lowercase hex; the *_bytes versions return
the raw digest as a str of bytes (use .bytes() to get at them). MD5 and SHA-1
are broken for security: use them only for checksums and old formats.

## Functions

### `hex(s: &str) -> str`

Each byte as two lowercase hex digits.

### `from_bytes(b: &list[u8]) -> str`

A str holding exactly these bytes.

### `md5_bytes(s: &str) -> str`

The raw 16-byte MD5 digest of s.

### `sha1_bytes(s: &str) -> str`

The raw 20-byte SHA-1 digest of s.

### `sha256_bytes(s: &str) -> str`

The raw 32-byte SHA-256 digest of s.

### `sha512_bytes(s: &str) -> str`

The raw 64-byte SHA-512 digest of s.

### `md5(s: &str) -> str`

The MD5 digest of s in hex.

### `sha1(s: &str) -> str`

The SHA-1 digest of s in hex.

### `sha256(s: &str) -> str`

The SHA-256 digest of s in hex.

### `sha512(s: &str) -> str`

The SHA-512 digest of s in hex.

### `hmac_md5(key: &str, msg: &str) -> str`

HMAC-MD5 of msg under key, in hex.

### `hmac_sha1(key: &str, msg: &str) -> str`

HMAC-SHA1 of msg under key, in hex.

### `hmac_sha256(key: &str, msg: &str) -> str`

HMAC-SHA256 of msg under key, in hex.

### `hmac_sha512(key: &str, msg: &str) -> str`

HMAC-SHA512 of msg under key, in hex.

### `crc32(s: &str) -> int`

The CRC-32 used by zip, gzip and PNG, as a non-negative int.

### `equal(a: &str, b: &str) -> bool`

Compares two digests in time that doesn't depend on where they differ.
