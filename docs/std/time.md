# time

Clocks, sleeping, and calendar dates and times.

```silly
import time
fn main():
    let t0 = time.perf_counter()
    time.sleep(0.25)
    print(f"took {time.perf_counter() - t0:.2f}s")
    let now = time.now()
    print(now.format("%Y-%m-%d %H:%M"), now.weekday_name())
    let d = time.date(2024, 2, 28).add_days(2)
    print(d.iso())      # 2024-03-01T00:00:00
```

## Types

### `DateTime`

A calendar date and time to the second, in local time or UTC.

- `year: int`
- `month: int`
- `day: int`
- `hour: int`
- `minute: int`
- `second: int`
- `weekday: int` — 0 = Monday ... 6 = Sunday
- `yearday: int` — 1 ... 366
- `offset: int` — seconds east of UTC
- `local: bool`
- `stamp: int` — the Unix timestamp this is

- `timestamp(self) -> int` — The Unix timestamp in seconds.
- `format(self, fmt: str) -> str` — Formats with strftime codes: %Y %m %d %H %M %S %A %a %B %b %j %Z %z %%...
- `iso(self) -> str` — "2024-03-01T12:30:00"
- `date_str(self) -> str`
- `time_str(self) -> str`
- `weekday_name(self) -> str`
- `month_name(self) -> str`
- `add_seconds(self, s: int) -> DateTime`
- `add_minutes(self, m: int) -> DateTime`
- `add_hours(self, h: int) -> DateTime`
- `add_days(self, d: int) -> DateTime` — Moves by whole calendar days, keeping the wall-clock time in local time.
- `since(self, other: DateTime) -> int` — Seconds from `other` to this one.
- `to_utc(self) -> DateTime`
- `to_local(self) -> DateTime`
- `is_before(self, other: DateTime) -> bool`

## Functions

### `time() -> f64`

Seconds since the Unix epoch, as a float.

### `time_ns() -> int`

Nanoseconds since the Unix epoch.

### `monotonic() -> f64`

A clock that never goes backwards, for measuring intervals (seconds).

### `monotonic_ns() -> int`

Nanoseconds on a clock that never goes back (for intervals).

### `perf_counter() -> f64`

Seconds on the monotonic clock, as f64, for timing code.

### `sleep(seconds: f64)`

Pauses this thread for seconds.

### `weekday_names() -> list[str]`

Monday to Sunday.

### `month_names() -> list[str]`

January to December.

### `now() -> DateTime`

The current local date and time.

### `utcnow() -> DateTime`

The current date and time in UTC.

### `from_timestamp(t: int) -> DateTime`

A local DateTime for a Unix timestamp.

### `utc_from_timestamp(t: int) -> DateTime`

The UTC date and time t seconds after the epoch.

### `date(year: int, month: int, day: int) -> DateTime`

Local midnight at the start of a date. Out-of-range days roll over (Jan 32 = Feb 1).

### `datetime(year: int, month: int, day: int, hour: int, minute: int, second: int) -> DateTime`

A DateTime from its parts (UTC).

### `utc(year: int, month: int, day: int, hour: int, minute: int, second: int) -> DateTime`

The same, in UTC.

### `parse_iso(s: &str) -> Option[DateTime]`

Parses "YYYY-MM-DD", "YYYY-MM-DD HH:MM[:SS]" or the same with a "T" (as local time).

### `is_leap(year: int) -> bool`

Whether year has a February 29th.

### `days_in_month(year: int, month: int) -> int`

28 to 31.
