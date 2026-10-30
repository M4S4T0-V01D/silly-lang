# heapq

Binary min-heaps kept in a plain list, like Python's heapq.

```silly
import heapq
fn main():
    var h: list[int] = []
    for x in [5, 1, 4, 2]:
        heapq.push(&mut h, x)
    print(heapq.pop(&mut h), heapq.pop(&mut h))     # Some(1) Some(2)
    print(heapq.nsmallest(&[9, 3, 7, 1], 2))         # [1, 3]
```

h[0] is always the smallest item. For a max-heap push negated numbers, or
tuples (priority, item) to order items by priority.

## Functions

### `push[T: Ord](h: &mut list[T], x: T)`

Adds x to the heap h.

### `pop[T: Ord](h: &mut list[T]) -> Option[T]`

Removes and returns the smallest item.

### `pushpop[T: Ord](h: &mut list[T], x: T) -> T`

Pushes x, then pops the smallest; faster than push followed by pop.

### `replace[T: Ord](h: &mut list[T], x: T) -> Option[T]`

Pops the smallest, then pushes x.

### `peek[T: Ord + Copy](h: &list[T]) -> Option[T]`

The smallest item without removing it.

### `heapify[T: Ord](h: &mut list[T])`

Rearranges a list into heap order in linear time.

### `nsmallest[T: Ord](xs: &list[T], n: int) -> list[T]`

The n smallest items, smallest first.

### `nlargest[T: Ord](xs: &list[T], n: int) -> list[T]`

The n largest items, largest first.

### `merge[T: Ord](lists: &list[list[T]]) -> list[T]`

Merges lists that are each already sorted into one sorted list.
