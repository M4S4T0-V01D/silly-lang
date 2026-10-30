# datetime

Calendar dates, times of day and durations, like Python's datetime (naive
values: no time zones). For timestamps and the clock in local time, see time.

```silly
import datetime as dt
fn main():
    let d = dt.date(2024, 2, 28)
    print(d.add_days(2).isoformat(), d.weekday_name())   # 2024-03-01 Wednesday
    let a = dt.datetime(2024, 3, 1, 9, 30, 0)
    let b = a.add(dt.hours(36))
    print(b.isoformat(), b.sub(a).str())                 # 2024-03-02T21:30:00 1 day, 12:00:00
    print(b.strftime("%a %d %b %Y, %I:%M %p"))           # Sat 02 Mar 2024, 09:30 PM
    print(dt.parse_datetime("2024-03-01 12:00").unwrap().isoformat())
```

Years run from 1 to 9999 on the proleptic Gregorian calendar. Building an
invalid date panics; the parse_ functions return Err instead.

## Constants

- `MIN_YEAR: int = 1`
- `MAX_YEAR: int = 9999`

## Types

### `Duration`

A length of time, kept in microseconds. It may be negative.

- `us: int`

- `days(self) -> int` — The whole days, rounded down like Python's timedelta.days.
- `seconds(self) -> int` — Seconds after the whole days (0 to 86399).
- `microseconds(self) -> int` — Microseconds after the whole seconds (0 to 999999).
- `total_seconds(self) -> f64`
- `total_microseconds(self) -> int`
- `add(self, o: Duration) -> Duration`
- `sub(self, o: Duration) -> Duration`
- `neg(self) -> Duration`
- `abs(self) -> Duration`
- `mul(self, n: int) -> Duration`
- `div(self, n: int) -> Duration` — Divided by n, rounded down to the microsecond.
- `ratio(self, o: Duration) -> int` — How many times o fits in this one, rounded down.
- `compare(self, o: Duration) -> int`
- `is_zero(self) -> bool`
- `str(self) -> str` — Like Python's str(timedelta): "-1 day, 23:59:59", "2 days, 1:00:00.500000".

### `Date`

A calendar day (proleptic Gregorian, years 1 to 9999).

- `year: int`
- `month: int`
- `day: int`

- `ordinal(self) -> int` — Days since 0001-01-01, which is day 1.
- `weekday(self) -> int` — 0 = Monday ... 6 = Sunday.
- `isoweekday(self) -> int` — 1 = Monday ... 7 = Sunday.
- `yearday(self) -> int` — The day of the year, from 1.
- `weekday_name(self) -> str`
- `month_name(self) -> str`
- `isocalendar(self) -> (int, int, int)` — (ISO year, ISO week 1-53, ISO weekday 1-7).
- `isoformat(self) -> str` — "2024-03-01"
- `strftime(self, fmt: &str) -> str`
- `ctime(self) -> str` — "Fri Mar  1 00:00:00 2024"
- `add_days(self, n: int) -> Date`
- `add(self, d: Duration) -> Date`
- `add_months(self, n: int) -> Date` — Moves by calendar months, clamping the day (Jan 31 + 1 month = Feb 29 in 2024).
- `add_years(self, n: int) -> Date`
- `sub(self, o: Date) -> Duration` — The time from o to this date.
- `days_since(self, o: Date) -> int`
- `replace(self, year: int, month: int, day: int) -> Date`
- `with_day(self, day: int) -> Date`
- `first_of_month(self) -> Date`
- `last_of_month(self) -> Date`
- `compare(self, o: Date) -> int`
- `before(self, o: Date) -> bool`
- `after(self, o: Date) -> bool`
- `at(self, t: Time) -> DateTime`

### `Time`

A time of day, to the microsecond.

- `hour: int`
- `minute: int`
- `second: int`
- `microsecond: int`

- `isoformat(self) -> str` — "09:30:00", or "09:30:00.250000" with microseconds.
- `strftime(self, fmt: &str) -> str`
- `compare(self, o: Time) -> int`
- `before(self, o: Time) -> bool`

### `DateTime`

A Date and a Time together (naive: no time zone).

- `year: int`
- `month: int`
- `day: int`
- `hour: int`
- `minute: int`
- `second: int`
- `microsecond: int`

- `date(self) -> Date`
- `time(self) -> Time`
- `weekday(self) -> int`
- `isoweekday(self) -> int`
- `weekday_name(self) -> str`
- `month_name(self) -> str`
- `yearday(self) -> int`
- `isocalendar(self) -> (int, int, int)`
- `isoformat(self) -> str` — "2024-03-01T09:30:00", with sep between date and time ("T" or " ").
- `isoformat_sep(self, sep: str) -> str`
- `strftime(self, fmt: &str) -> str`
- `ctime(self) -> str`
- `add(self, d: Duration) -> DateTime`
- `sub(self, o: DateTime) -> Duration` — The time from o to this one.
- `add_days(self, n: int) -> DateTime`
- `add_months(self, n: int) -> DateTime`
- `add_years(self, n: int) -> DateTime`
- `compare(self, o: DateTime) -> int`
- `before(self, o: DateTime) -> bool`
- `after(self, o: DateTime) -> bool`
- `timestamp_utc(self) -> f64` — Seconds since 1970-01-01T00:00, reading this as UTC.
- `floor(self, d: Duration) -> DateTime` — Rounded down to a multiple of d (e.g. hours(1) starts the hour).

## Functions

### `is_leap(year: int) -> bool`

Whether year has a February 29th.

### `days_in_month(year: int, month: int) -> int`

28 to 31.

### `days_in_year(year: int) -> int`

365 or 366.

### `weekday_names() -> list[str]`

Monday to Sunday.

### `month_names() -> list[str]`

January to December.

### `timedelta(days: int, seconds: int, microseconds: int) -> Duration`

A Duration of days, seconds and microseconds (any of them may be negative).

### `weeks(n: int) -> Duration`

A Duration of n weeks.

### `days(n: int) -> Duration`

A Duration of n days.

### `hours(n: int) -> Duration`

A Duration of n hours.

### `minutes(n: int) -> Duration`

A Duration of n minutes.

### `seconds(n: int) -> Duration`

A Duration of n seconds.

### `milliseconds(n: int) -> Duration`

A Duration of n milliseconds.

### `microseconds(n: int) -> Duration`

A Duration of n microseconds.

### `date(year: int, month: int, day: int) -> Date`

The Date year-month-day; panics if there is no such day.

### `from_ordinal(n: int) -> Date`

The date for an ordinal (1 = 0001-01-01).

### `from_isocalendar(year: int, week: int, weekday: int) -> Date`

The date for an ISO year, week and weekday (1 = Monday).

### `today() -> Date`

Today's date in local time.

### `time_of_day(hour: int, minute: int, second: int) -> Time`

hour:minute:second.

### `time_us(hour: int, minute: int, second: int, microsecond: int) -> Time`

hour:minute:second.microsecond.

### `datetime(year: int, month: int, day: int, hour: int, minute: int, second: int) -> DateTime`

The DateTime year-month-day hour:minute:second.

### `datetime_us(year: int, month: int, day: int, hour: int, minute: int, second: int, microsecond: int) -> DateTime`

Like datetime, with microseconds.

### `combine(d: Date, t: Time) -> DateTime`

The DateTime of day d at time t.

### `now() -> DateTime`

The local date and time now.

### `utcnow() -> DateTime`

The date and time now in UTC.

### `utc_from_timestamp(t: f64) -> DateTime`

The UTC date and time of a Unix timestamp.

### `parse_date(s: &str) -> Result[Date, str]`

"YYYY-MM-DD" or "YYYYMMDD".

### `parse_time(s: &str) -> Result[Time, str]`

"HH", "HH:MM", "HH:MM:SS" or "HH:MM:SS.ffffff" (1 to 6 fraction digits), or the same without colons ("HHMMSS").

### `parse_datetime(s: &str) -> Result[DateTime, str]`

A date, optionally followed by "T" or " " and a time.
