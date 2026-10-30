# tempfile

Temporary files and directories, like Python's tempfile.

```silly
import tempfile
fn main():
    let f = tempfile.mkstemp("data-", ".csv").unwrap()     # /tmp/data-1f3a...csv
    let n = tempfile.with_tempdir("build-", fn(dir) => count_files(dir)).unwrap()
```

Names are random (64 bits from the OS), under gettempdir() ($TMPDIR or /tmp)
unless a directory is given. Files and directories made here are only readable
by you. Nothing is removed automatically, except by with_tempdir.

## Functions

### `gettempdir() -> str`

The directory temporary files go in.

### `mktemp(prefix: &str, suffix: &str, dir: &str) -> str`

A path under dir (or gettempdir() if dir is "") that doesn't exist yet. Nothing is created, so another program could take the name first; prefer mkstemp.

### `mkstemp(prefix: str, suffix: str) -> Result[str, str]`

Creates a new, empty file in gettempdir() and returns its path.

### `mkstemp_in(dir: &str, prefix: str, suffix: str) -> Result[str, str]`

Creates a new, empty file in dir and returns its path.

### `write_temp(prefix: str, suffix: str, data: str) -> Result[str, str]`

Like mkstemp, with the given contents.

### `mkdtemp(prefix: str) -> Result[str, str]`

Creates a new, empty directory in gettempdir() and returns its path.

### `mkdtemp_in(dir: &str, prefix: str) -> Result[str, str]`

Creates a new, empty directory in dir and returns its path.

### `with_tempdir[T](prefix: str, f: fn(str) -> T) -> Result[T, str]`

Makes a temporary directory, calls f with its path, then removes the directory and everything in it, and returns what f returned.
