# json

Reading and writing JSON.

```silly
import json
fn main():
    let v = json.parse("{\"name\": \"silly\", \"tags\": [1, 2.5, true]}").unwrap()
    print(v.get("name").unwrap().as_str())        # Some("silly")
    print(v.find("tags.1").unwrap().as_float())    # Some(2.5)
    var o = json.object()
    o.set("ok", json.Value.Bool(true))
    o.set("list", json.array_of_ints(&[1, 2, 3]))
    print(json.dump(&o))                          # {"ok":true,"list":[1,2,3]}
    print(json.pretty(&o, 2))
```

Numbers without a fraction or exponent become Int when they fit in 64 bits,
the rest Float. Objects keep their keys in the order they appeared.

## Types

### `Value`

A JSON value: null, a bool, a number, a string, an array or an object.

- `Null`
- `Bool(bool)`
- `Int(int)`
- `Float(f64)`
- `Str(str)`
- `Arr(list[Value])`
- `Obj(map[str, Value])`

- `type_name(self) -> str` — "null", "bool", "int", "float", "string", "array" or "object".
- `is_null(self) -> bool`
- `as_bool(self) -> Option[bool]`
- `as_int(self) -> Option[int]` — Int values, and Floats with no fractional part.
- `as_float(self) -> Option[f64]` — Float and Int values as a float.
- `as_str(self) -> Option[str]`
- `as_list(self) -> Option[list[Value]]`
- `as_map(self) -> Option[map[str, Value]]`
- `get(self, key: &str) -> Option[Value]` — The member `key` of an object (a copy); None for a missing key or a non-object.
- `at(self, i: int) -> Option[Value]` — Element i of an array (a copy).
- `find(self, path: &str) -> Option[Value]` — Follows a dotted path of keys and indexes: v.find("users.0.name").
- `has(self, key: &str) -> bool`
- `len(self) -> int` — The number of elements of an array or members of an object; 0 otherwise.
- `keys(self) -> list[str]`
- `set(mut self, key: str, v: Value)` — Sets an object member (panics on a non-object).
- `push(mut self, v: Value)` — Appends to an array (panics on a non-array).
- `remove(mut self, key: &str) -> Option[Value]`
- `to_str(self) -> str`

## Functions

### `object() -> Value`

An empty object.

### `array() -> Value`

An empty array.

### `string(s: &str) -> Value`

A string value.

### `array_of_ints(xs: &list[int]) -> Value`

An array of the numbers in xs.

### `array_of_floats(xs: &list[f64]) -> Value`

An array of the numbers in xs.

### `array_of_strs(xs: &list[str]) -> Value`

An array of the strings in xs.

### `dump(v: &Value) -> str`

Compact JSON text: no spaces or newlines.

### `pretty(v: &Value, indent: int) -> str`

Indented JSON text, `indent` spaces per level.

### `quote(s: &str) -> str`

A string as a JSON string literal, with quotes and escapes.

### `parse(text: &str) -> Result[Value, str]`

Parses JSON text. Errors say what was wrong and where ("line 3 column 7").
