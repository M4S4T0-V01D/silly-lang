# statistics

Averages and spread of lists of numbers, like Python's statistics.

```silly
import statistics as st
fn main():
    let xs = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    print(st.mean(&xs), st.median(&xs), st.pstdev(&xs))   # 5.0 4.5 2.0
    print(st.mode(&st.floats(&[1, 2, 2, 3])))              # 2.0
```

Every function takes list[f64]; floats() converts a list[int]. Functions that
need data panic on an empty list (variance and stdev need two items).

## Functions

### `floats(xs: &list[int]) -> list[f64]`

A list[int] as list[f64].

### `fsum(xs: &list[f64]) -> f64`

The sum, added with compensation (Neumaier) so rounding errors don't pile up.

### `mean(xs: &list[f64]) -> f64`

The arithmetic mean; panics on an empty list.

### `geometric_mean(xs: &list[f64]) -> f64`

The nth root of the product (all values must be positive).

### `harmonic_mean(xs: &list[f64]) -> f64`

n divided by the sum of reciprocals.

### `median(xs: &list[f64]) -> f64`

The middle value, or the mean of the two middle values.

### `median_low(xs: &list[f64]) -> f64`

The median; the lower middle value for even lengths.

### `median_high(xs: &list[f64]) -> f64`

The median; the higher middle value for even lengths.

### `mode(xs: &list[f64]) -> f64`

The most common value; the first one seen wins a tie.

### `multimode(xs: &list[f64]) -> list[f64]`

Every value that is most common, in the order first seen.

### `pvariance(xs: &list[f64]) -> f64`

Population variance: the mean squared distance from the mean.

### `variance(xs: &list[f64]) -> f64`

Sample variance, dividing by n - 1.

### `pstdev(xs: &list[f64]) -> f64`

The population standard deviation.

### `stdev(xs: &list[f64]) -> f64`

The sample standard deviation (needs at least two values).

### `quantiles(xs: &list[f64], n: int) -> list[f64]`

Cut points dividing the data into n groups of equal probability (Python's default "exclusive" method): quantiles(xs, 4) gives the quartiles.

### `covariance(xs: &list[f64], ys: &list[f64]) -> f64`

The covariance of two equally long samples.

### `correlation(xs: &list[f64], ys: &list[f64]) -> f64`

Pearson's correlation coefficient, from -1 to 1.

### `linear_regression(xs: &list[f64], ys: &list[f64]) -> (f64, f64)`

The least-squares line through the points: (slope, intercept).
