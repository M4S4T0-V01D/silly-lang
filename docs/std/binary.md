# binary

Packing numbers into bytes and back, like Python's struct (which is a keyword
here), plus typed Writer and Reader for building and walking binary data.

```silly
import binary
from binary import Value
fn main():
    let b = binary.pack(&"<HId", &[Value.Int(1), Value.Int(2), Value.Float(0.5)]).unwrap()
    print(len(b), binary.calcsize(&"<HId").unwrap())          # 14 14
    let v = binary.unpack(&"<HId", &b).unwrap()
    var w = binary.writer()
    w.u32_be(0xCAFEBABE)
    w.str(&"hi")
    var r = binary.reader(&w.bytes())
    print(r.u32_be().unwrap(), r.take(2).unwrap())
```

Formats: the first character picks the byte order: "<" little-endian, ">" or
"!" big-endian, "=" this machine's order, "@" (the default) this machine's
order, sizes and alignment. Then: x pad byte, c char (1 byte), b/B 8-bit,
?  bool, h/H 16-bit, i/I and l/L 32-bit (l/L are 64-bit with "@"), q/Q 64-bit,
n/N 64-bit ("@" only), f float, d double, s bytes. A count before a letter
repeats it ("3h"); before "s" it's the length ("10s", padded with zeros).

Silly's int is 64-bit and signed, so Q and N values of 2**63 and up come back
negative (the same bits); pack takes any int for them.

## Types

### `Value`

One packed value.

- `Int(int)`
- `Float(f64)`
- `Bool(bool)`
- `Bytes(list[u8])` — for "s" and "c"

- `str(self) -> str`
- `int(self) -> int`
- `float(self) -> f64`
- `bytes(self) -> list[u8]`

### `Writer`

Builds a byte string from packed integers, floats and strings.

- `data: list[u8]`

- `bytes(self) -> list[u8]`
- `len(self) -> int`
- `u8(mut self, v: int)`
- `u16_le(mut self, v: int)`
- `u16_be(mut self, v: int)`
- `u32_le(mut self, v: int)`
- `u32_be(mut self, v: int)`
- `u64_le(mut self, v: int)`
- `u64_be(mut self, v: int)`
- `f32_le(mut self, x: f64)`
- `f32_be(mut self, x: f64)`
- `f64_le(mut self, x: f64)`
- `f64_be(mut self, x: f64)`
- `uvarint(mut self, v: int)` — A LEB128 varint (unsigned; as in protobuf and WebAssembly).
- `put(mut self, b: &list[u8])`
- `str(mut self, s: &str)` — The string's UTF-8 bytes (no length, no terminator).
- `align(mut self, n: int)` — Zero bytes up to a multiple of n.

### `Reader`

Reads packed values back from bytes, front to back.

- `data: list[u8]`
- `pos: int`

- `remaining(self) -> int`
- `at_end(self) -> bool`
- `u8(mut self) -> Result[int, str]`
- `i8(mut self) -> Result[int, str]`
- `u16_le(mut self) -> Result[int, str]`
- `u16_be(mut self) -> Result[int, str]`
- `i16_le(mut self) -> Result[int, str]`
- `i16_be(mut self) -> Result[int, str]`
- `u32_le(mut self) -> Result[int, str]`
- `u32_be(mut self) -> Result[int, str]`
- `i32_le(mut self) -> Result[int, str]`
- `i32_be(mut self) -> Result[int, str]`
- `u64_le(mut self) -> Result[int, str]`
- `u64_be(mut self) -> Result[int, str]`
- `f32_le(mut self) -> Result[f64, str]`
- `f32_be(mut self) -> Result[f64, str]`
- `f64_le(mut self) -> Result[f64, str]`
- `f64_be(mut self) -> Result[f64, str]`
- `uvarint(mut self) -> Result[int, str]`
- `take(mut self, n: int) -> Result[list[u8], str]` — The next n bytes.
- `skip(mut self, n: int) -> Result[bool, str]`

## Functions

### `f64_bits(x: f64) -> int`

The 64 bits of a double, as an int.

### `f64_from_bits(b: int) -> f64`

The f64 whose IEEE 754 bits are b.

### `f32_bits(x: f64) -> int`

The 32 bits of x rounded to a float.

### `f32_from_bits(b: int) -> f64`

The f32 whose IEEE 754 bits are the low 32 of b, widened to f64.

### `calcsize(fmt: &str) -> Result[int, str]`

The number of bytes a format packs to.

### `pack(fmt: &str, values: &list[Value]) -> Result[list[u8], str]`

The bytes for values packed by the format.

### `unpack(fmt: &str, data: &list[u8]) -> Result[list[Value], str]`

The values in bytes packed by the format; the length must match exactly.

### `unpack_from(fmt: &str, data: &list[u8], offset: int) -> Result[list[Value], str]`

Like unpack, reading from offset on and ignoring any bytes after.

### `unpack_all(fmt: &str, data: &list[u8]) -> Result[list[list[Value]], str]`

Every record in data, one format's worth at a time (iter_unpack).

### `writer() -> Writer`

An empty Writer.

### `reader(data: &list[u8]) -> Reader`

A Reader at the start of data.
