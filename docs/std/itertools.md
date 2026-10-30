# itertools

Combining and slicing lists, like Python's itertools. Every function returns a
new list rather than a lazy iterator.

```silly
import itertools as it
fn main():
    print(it.combinations(&[1, 2, 3], 2))     # [[1, 2], [1, 3], [2, 3]]
    print(it.product(&[[0, 1], [5, 6]]))      # [[0, 5], [0, 6], [1, 5], [1, 6]]
    print(it.accumulate(&[1, 2, 3, 4], fn(a, b) => a * b))   # [1, 2, 6, 24]
    print(it.pairwise(&["a", "b", "c"]))      # [("a", "b"), ("b", "c")]
```

## Functions

### `chain[T](lists: &list[list[T]]) -> list[T]`

The lists one after another.

### `repeat[T](x: &T, n: int) -> list[T]`

x, n times.

### `cycle[T](xs: &list[T], n: int) -> list[T]`

The list repeated n times over.

### `islice[T](xs: &list[T], start: int, stop: int, step: int) -> list[T]`

Items from start up to stop (exclusive), every step-th. Out-of-range bounds are clipped.

### `accumulate[T](xs: &list[T], f: fn(T, T) -> T) -> list[T]`

Running totals of f: [x0, f(x0, x1), f(f(x0, x1), x2), ...].

### `sums(xs: &list[int]) -> list[int]`

Running sums.

### `take_while[T](xs: &list[T], pred: fn(T) -> bool) -> list[T]`

The items while pred holds, stopping at the first that fails.

### `drop_while[T](xs: &list[T], pred: fn(T) -> bool) -> list[T]`

Everything from the first item where pred fails.

### `compress[T](xs: &list[T], selectors: &list[bool]) -> list[T]`

The items whose matching selector is true.

### `filter_false[T](xs: &list[T], pred: fn(T) -> bool) -> list[T]`

The items where pred is false (the opposite of filter).

### `pairwise[T](xs: &list[T]) -> list[(T, T)]`

Each item with the next one.

### `windows[T](xs: &list[T], n: int) -> list[list[T]]`

Every run of n consecutive items (sliding window).

### `batched[T](xs: &list[T], n: int) -> list[list[T]]`

Items in lists of n; the last may be shorter.

### `zip_longest[A, B](xs: &list[A], ys: &list[B], fill_a: &A, fill_b: &B) -> list[(A, B)]`

Pairs of items at the same index, padding the shorter list with fill.

### `unique[T: Eq](xs: &list[T]) -> list[T]`

The items with duplicates removed, keeping the first of each.

### `product[T](lists: &list[list[T]]) -> list[list[T]]`

The cartesian product: one item from each list, the last list varying fastest.

### `product_n[T](xs: &list[T], n: int) -> list[list[T]]`

The product of xs with itself, n times over.

### `permutations[T](xs: &list[T], k: int) -> list[list[T]]`

Every ordering of k items, in lexicographic order of position.

### `permutations_all[T](xs: &list[T]) -> list[list[T]]`

Every ordering of all the items.

### `combinations[T](xs: &list[T], k: int) -> list[list[T]]`

Every choice of k items, keeping their order.

### `combinations_with_replacement[T](xs: &list[T], k: int) -> list[list[T]]`

Every choice of k items where an item may be chosen more than once.

### `powerset[T](xs: &list[T]) -> list[list[T]]`

Every subset, from the empty one up, smaller ones first.
