# uuid

Universally unique identifiers (RFC 9562), like Python's uuid.

```silly
import uuid
fn main():
    print(uuid.uuid4().str())                    # e.g. 5b0c4c6e-8f0a-4d5e-9a1b-...
    print(uuid.uuid5(&uuid.namespace_dns(), &"python.org").str())
    # 886313e1-3b8a-5372-9b90-0c9aee199e5d
    let u = uuid.parse(&"{12345678-1234-5678-1234-567812345678}").unwrap()
    print(u.hex(), u.version())
```

uuid4 is random, uuid7 is ordered by time and random after that (a good
database key), uuid1 is time plus a random node, and uuid3/uuid5 are names
hashed into a namespace (MD5 and SHA-1) so the same name always gives the same UUID.

## Types

### `UUID`

A 128-bit UUID.

- `bytes: list[u8]` — 16 bytes, most significant first

- `str(self) -> str` — "12345678-1234-5678-1234-567812345678"
- `hex(self) -> str` — 32 hex digits, no hyphens.
- `urn(self) -> str` — "urn:uuid:12345678-..."
- `version(self) -> int` — The version number (1 to 8) from the version bits; only meaningful for RFC UUIDs.
- `variant(self) -> str` — "rfc4122" for standard UUIDs, else "ncs", "microsoft" or "future".
- `time(self) -> f64` — For uuid1 and uuid7: the creation time as a Unix timestamp in seconds.
- `compare(self, o: &UUID) -> int` — -1, 0 or 1, comparing byte by byte (the same order as the strings).
- `is_nil(self) -> bool`

## Functions

### `uuid4() -> UUID`

A random UUID.

### `uuid7() -> UUID`

A UUID that starts with the current Unix time in milliseconds, so ones made later sort after earlier ones.

### `uuid1() -> UUID`

A UUID from the current time and a random node (the 48-bit host part).

### `uuid3(ns: &UUID, name: &str) -> UUID`

The UUID for a name in a namespace, by MD5.

### `uuid5(ns: &UUID, name: &str) -> UUID`

The UUID for a name in a namespace, by SHA-1 (prefer this over uuid3).

### `parse(s: &str) -> Result[UUID, str]`

Parses 32 hex digits, with or without hyphens, braces or a "urn:uuid:" prefix.

### `from_bytes(b: &list[u8]) -> UUID`

A UUID holding exactly these 16 bytes.

### `nil() -> UUID`

00000000-0000-0000-0000-000000000000

### `max_uuid() -> UUID`

ffffffff-ffff-ffff-ffff-ffffffffffff

### `namespace_dns() -> UUID`

The namespaces from RFC 9562, for uuid3 and uuid5.

### `namespace_url() -> UUID`

The RFC 4122 namespace for URLs, for uuid3 and uuid5.

### `namespace_oid() -> UUID`

The RFC 4122 namespace for ISO OIDs.

### `namespace_x500() -> UUID`

The RFC 4122 namespace for X.500 names.
