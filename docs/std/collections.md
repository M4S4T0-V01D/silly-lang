# collections

Container types beyond list and map, like Python's collections.

```silly
import collections
fn main():
    var c = collections.counter(&"mississippi".chars())
    print(c.most_common(2))                  # [('i', 4), ('s', 4)]
    var d: collections.Deque[int] = collections.Deque.new()
    d.push_back(1)
    d.push_front(0)
    print(d.pop_back(), d.pop_front())       # Some(1) Some(0)
```

Counter counts hashable items; Deque adds and removes at both ends in O(1)
(amortized); group_by and chunks group a list's items.

## Types

### `Counter`

`struct Counter[K]`

Counts how many times each key was added, like Python's Counter.

- `counts: map[K, int]`

- `new() -> Counter[K]`
- `add(mut self, k: K, n: int)` — Adds n to k's count.
- `add_all(mut self, xs: &list[K])`
- `get(self, k: K) -> int` — k's count, 0 when it was never added.
- `len(self) -> int`
- `total(self) -> int` — The sum of every count.
- `most_common(self, n: int) -> list[(K, int)]` — The n highest counts, highest first; ties keep the order items were first seen.
- `elements(self) -> list[K]` — Every item repeated as many times as its count.
- `to_map(self) -> map[K, int]`

### `Deque`

`struct Deque[T]`

Two stacks back to back: `front` holds the front items reversed.

- `front: list[T]`
- `back: list[T]`

- `new() -> Deque[T]`
- `from_list(xs: list[T]) -> Deque[T]`
- `len(self) -> int`
- `is_empty(self) -> bool`
- `push_back(mut self, x: T)`
- `push_front(mut self, x: T)`
- `pop_back(mut self) -> Option[T]`
- `pop_front(mut self) -> Option[T]`
- `at(self, i: int) -> T` — The item at position i from the front.
- `to_list(self) -> list[T]`
- `clear(mut self)`

## Functions

### `counter[K](xs: &list[K]) -> Counter[K]`

A Counter of the items in a list.

### `group_by[T, K: Eq](xs: &list[T], key: fn(T) -> K) -> list[(K, list[T])]`

Runs of consecutive items with the same key, like itertools.groupby.

### `chunks[T](xs: &list[T], n: int) -> list[list[T]]`

Items in lists of n (the last may be shorter).
