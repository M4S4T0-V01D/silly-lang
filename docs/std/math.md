# math

Math functions backed by the C math library.

## Constants

- `PI: f64 = 3.141592653589793`
- `TAU: f64 = 6.283185307179586`
- `E: f64 = 2.718281828459045`

## Functions

### `sqrt(x: f64) -> f64`

The square root of x.

### `cbrt(x: f64) -> f64`

The cube root of x.

### `sin(x: f64) -> f64`

Sine of x radians.

### `cos(x: f64) -> f64`

Cosine of x radians.

### `tan(x: f64) -> f64`

Tangent of x radians.

### `asin(x: f64) -> f64`

Arc sine, in radians.

### `acos(x: f64) -> f64`

Arc cosine, in radians.

### `atan(x: f64) -> f64`

Arc tangent, in radians.

### `atan2(y: f64, x: f64) -> f64`

The angle of the point (x, y), from -PI to PI.

### `exp(x: f64) -> f64`

e to the power x.

### `log(x: f64) -> f64`

The natural logarithm of x.

### `log2(x: f64) -> f64`

The base-2 logarithm of x.

### `log10(x: f64) -> f64`

The base-10 logarithm of x.

### `pow(x: f64, y: f64) -> f64`

x to the power y.

### `hypot(x: f64, y: f64) -> f64`

sqrt(x*x + y*y), without overflow.

### `floor(x: f64) -> f64`

The largest whole number <= x.

### `ceil(x: f64) -> f64`

The smallest whole number >= x.

### `fabs(x: f64) -> f64`

The absolute value of x.

### `inf() -> f64`

Positive infinity.

### `gcd(a: int, b: int) -> int`

The greatest common divisor of a and b (never negative).

### `clamp(x: f64, lo: f64, hi: f64) -> f64`

x, limited to lo..hi.
