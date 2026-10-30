# bisect

Binary search in sorted lists, like Python's bisect.

```silly
import bisect
fn main():
    var xs = [1, 3, 3, 7]
    print(bisect.left(&xs, &3), bisect.right(&xs, &3))   # 1 3
    bisect.insort(&mut xs, 5)                          # [1, 3, 3, 5, 7]
    print(bisect.index(&xs, &7))                       # Some(4)
```

## Functions

### `left[T: Ord](xs: &list[T], x: &T) -> int`

The first position where x could be inserted keeping the list sorted (before equal items).

### `right[T: Ord](xs: &list[T], x: &T) -> int`

The last such position (after equal items).

### `insort[T: Ord](xs: &mut list[T], x: T)`

Inserts x after any equal items.

### `insort_left[T: Ord](xs: &mut list[T], x: T)`

Inserts x into the sorted xs before any equal items.

### `index[T: Ord](xs: &list[T], x: &T) -> Option[int]`

The position of the first item equal to x.

### `count[T: Ord](xs: &list[T], x: &T) -> int`

How many items equal x.
