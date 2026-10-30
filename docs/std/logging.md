# logging

Leveled log messages, like Python's logging.

```silly
import logging
fn main():
    logging.warning("disk almost full")          # WARNING:root:disk almost full
    var log = logging.get_logger("app")
    log.set_level(logging.DEBUG)
    log.set_format("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    log.to_file("app.log")                       # also append to a file
    log.info("started")
```

Messages below a logger's level are dropped. New loggers start at WARNING, or
at the level named in $SILLY_LOG (e.g. SILLY_LOG=debug), which also sets the
level of the module-level functions. Output goes to stderr unless to_stderr(false).

Format fields: %(message)s %(levelname)s %(levelno)d %(name)s %(asctime)s
%(created)f %(process)d, with an optional width like %(levelname)-8s or %(levelname)8s.

## Constants

- `NOTSET: int = 0`
- `DEBUG: int = 10`
- `INFO: int = 20`
- `WARNING: int = 30`
- `ERROR: int = 40`
- `CRITICAL: int = 50`
- `DEFAULT_FORMAT: str = "%(levelname)s:%(name)s:%(message)s"`

## Types

### `Logger`

A named logger with its own level, format and output.

- `name: str`
- `level: int`
- `format: str`
- `stderr: bool`
- `files: list[str]`

- `set_level(mut self, level: int)`
- `set_format(mut self, fmt: str)`
- `to_file(mut self, path: str)` — Also append each message to a file.
- `to_stderr(mut self, on: bool)`
- `enabled(self, level: int) -> bool` — Whether a message at this level would be written.
- `child(self, suffix: str) -> Logger` — A logger named "<name>.<suffix>" with these settings.
- `render(self, level: int, msg: &str) -> str` — The line a message would be written as (without the newline).
- `log(self, level: int, msg: str)`
- `debug(self, msg: str)`
- `info(self, msg: str)`
- `warning(self, msg: str)`
- `error(self, msg: str)`
- `critical(self, msg: str)`

## Functions

### `level_name(level: int) -> str`

"DEBUG", "INFO", ...; other numbers give "Level N".

### `parse_level(s: &str) -> Option[int]`

A level from its name (any case, "warn" and "fatal" too) or a number.

### `get_logger(name: str) -> Logger`

A new Logger called name, at the level SILLY_LOG names (WARNING if unset).

### `format_record(fmt: &str, name: &str, level: int, msg: &str) -> str`

Fills in a format string's %(field)s placeholders.

### `root() -> Logger`

A Logger called "root"; log(), debug() and the rest use one like it.

### `log(level: int, msg: str)`

Logs msg at level to the root logger.

### `debug(msg: str)`

Logs msg at DEBUG.

### `info(msg: str)`

Logs msg at INFO.

### `warning(msg: str)`

Logs msg at WARNING.

### `error(msg: str)`

Logs msg at ERROR.

### `critical(msg: str)`

Logs msg at CRITICAL.
